"""
backend/app/services/sandbox_service.py

沙盒测试服务。

职责：
    - 协调沙盒测试的完整流程（生成测试用例 → 执行测试 → 处理结果）
    - 调用 AI 模型基于需求生成触发精度测试用例（evals.json）
    - 触发 Docker 沙盒执行器（SandboxRunner）运行 eval_description.py
    - 解析测试结果并更新任务状态（PASSED / FAILED / TEST_ERROR）
    - 将测试结果持久化到 SandboxTest 表

沙盒测试的两个核心验证：
    1. Skill 目录结构校验（通过 KernelAdapter.validate_skill_structure）
    2. 描述触发精度测试（通过 skill-creator 内核的 eval_description.py）

安全保障：
    - 所有测试在 Docker 容器内执行，与宿主环境隔离
    - 容器无网络访问（--network none）
    - 内存和 CPU 限制防止资源滥用
    - Skill 文件以只读方式挂载，容器无写权限
    - 执行超时后强制 kill 容器
"""

import json
import traceback
import uuid
from pathlib import Path

from ..exceptions import TaskNotFoundError
from ..extensions import db
from ..kernel.registry import KernelRegistry
from ..model.provider import Message, ModelProviderFactory
from ..models.sandbox_test import SandboxTest
from ..models.skill_creation_task import SkillCreationTask
from ..models.task_event_log import TaskEventLog
from ..sandbox.docker_runner import SandboxRunner


class SandboxService:
    """
    沙盒测试服务类。

    封装从"触发测试请求"到"测试结果持久化"的完整流程。
    通常由 Celery 异步任务调用（sandbox_test_task）。
    """

    def run_test(self, task_id: str, test_id: str) -> SandboxTest:
        """
        执行沙盒测试的完整流程。

        Args:
            task_id: SkillCreationTask ID
            test_id: SandboxTest ID（已预先创建，状态为 running）

        Returns:
            更新后的 SandboxTest 实例。
        """
        task = SkillCreationTask.query.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"任务不存在: {task_id}")

        test = SandboxTest.query.get(test_id)
        if test is None:
            raise TaskNotFoundError(f"测试记录不存在: {test_id}")

        # 记录测试开始
        self._log_event(task_id, TaskEventLog.ET_SANDBOX_START, {
            "test_id": test_id,
        })
        db.session.commit()

        try:
            # Step 1: 校验 Skill 目录结构
            kernel = KernelRegistry.get_instance().get_kernel("skill-creator")
            skill_path = self._find_skill_path(task)
            validation = kernel.validate_skill_structure(skill_path)

            test.structure_valid = validation.valid
            test.structure_errors = validation.errors

            if not validation.valid:
                # 结构校验失败，直接标记为 FAILED（无需运行 eval）
                test.status = SandboxTest.STATUS_FAILED
                self._update_task_status(task, SkillCreationTask.STATUS_FAILED)
                db.session.commit()
                return test

            # Step 2: 生成测试用例（evals.json）
            spec = task.requirement_spec or {}
            evals = self._generate_evals(spec)
            test.evals_used = evals

            # Step 3: 运行 Docker 沙盒测试
            eval_script_path = kernel.get_eval_script_path()
            runner = SandboxRunner()

            # 如果需求中指定使用 LLM 裁判，从 Flask 配置中读取 LLM 凭据传入容器
            env_vars = None
            if spec.get("use_llm_eval"):
                from flask import current_app
                llm_api_key = current_app.config.get("LLM_API_KEY", "")
                llm_base_url = current_app.config.get("LLM_BASE_URL", "")
                llm_model = current_app.config.get("LLM_MODEL", "")
                if llm_api_key:
                    env_vars = {"LLM_API_KEY": llm_api_key}
                    if llm_base_url:
                        env_vars["LLM_BASE_URL"] = llm_base_url
                    if llm_model:
                        env_vars["LLM_MODEL"] = llm_model

            result = runner.run_eval(
                skill_path=skill_path,
                eval_script_path=eval_script_path,
                evals=evals,
                test_id=test_id,
                env_vars=env_vars,
            )

            # Step 4: 处理测试结果
            import time
            test.raw_output = result.get("raw_output", "")
            test.duration_seconds = result.get("duration_seconds", 0)

            report = result.get("report", {})
            if report:
                test.trigger_accuracy = report.get("trigger_accuracy", 0.0)
                test.total_cases = report.get("total_cases", 0)
                test.passed_cases = report.get("passed_cases", 0)
                test.test_results = report

            # 根据触发精度判断测试结果
            if result.get("timed_out"):
                test.status = SandboxTest.STATUS_TIMEOUT
                self._update_task_status(task, SkillCreationTask.STATUS_TEST_ERROR)
            elif result.get("error"):
                test.status = SandboxTest.STATUS_ERROR
                self._update_task_status(task, SkillCreationTask.STATUS_TEST_ERROR)
            elif report.get("passed", False):
                test.status = SandboxTest.STATUS_PASSED
                self._update_task_status(task, SkillCreationTask.STATUS_PASSED)
            else:
                test.status = SandboxTest.STATUS_FAILED
                self._update_task_status(task, SkillCreationTask.STATUS_FAILED)

            # 记录测试完成日志
            self._log_event(task_id, TaskEventLog.ET_SANDBOX_DONE, {
                "test_id": test_id,
                "status": test.status,
                "trigger_accuracy": test.trigger_accuracy,
            })
            db.session.commit()

        except Exception as e:
            test.status = SandboxTest.STATUS_ERROR
            test.raw_output = traceback.format_exc()
            self._update_task_status(task, SkillCreationTask.STATUS_TEST_ERROR)
            self._log_event(task_id, TaskEventLog.ET_ERROR, {
                "test_id": test_id,
                "error": str(e),
            })
            db.session.commit()

        return test

    def create_test_record(self, task_id: str) -> SandboxTest:
        """
        创建沙盒测试记录（状态为 running），并更新任务状态为 TESTING。

        这是触发测试的第一步，在 HTTP 请求阶段同步执行，
        返回 test_id 后立即提交 Celery 任务进行异步测试。

        Args:
            task_id: SkillCreationTask ID

        Returns:
            新创建的 SandboxTest 实例（状态为 running）。

        Raises:
            TaskNotFoundError: 当任务不存在或状态不允许测试时
        """
        from ..exceptions import InvalidTaskStateError

        task = SkillCreationTask.query.get(task_id)
        if task is None:
            raise TaskNotFoundError(f"任务不存在: {task_id}")

        if task.status not in SkillCreationTask.TESTABLE_STATUSES:
            raise InvalidTaskStateError(
                f"当前任务状态 '{task.status}' 不允许触发测试，"
                f"只有 {SkillCreationTask.TESTABLE_STATUSES} 状态下才能测试"
            )

        test = SandboxTest(
            id=str(uuid.uuid4()),
            task_id=task_id,
            status=SandboxTest.STATUS_RUNNING,
        )
        db.session.add(test)
        task.transition_to(SkillCreationTask.STATUS_TESTING)
        db.session.commit()

        return test

    def _generate_evals(self, spec: dict) -> list:
        """
        调用 AI 模型基于结构化需求生成触发精度测试用例。

        生成的测试用例格式：
        [
          {"prompt": "用户输入示例", "should_trigger": true},
          {"prompt": "不相关的输入", "should_trigger": false}
        ]

        数量：5-8 个应触发 + 3-5 个不应触发，共 8-13 个用例

        Args:
            spec: 结构化需求字典

        Returns:
            测试用例列表，如 AI 调用失败则返回默认用例集。
        """
        try:
            provider = ModelProviderFactory.create_from_active_config()
            prompt = (
                "请根据以下 Skill 需求，生成用于测试 Skill 描述触发精度的测试用例。\n\n"
                f"Skill 需求：\n{json.dumps(spec, ensure_ascii=False, indent=2)}\n\n"
                "要求：\n"
                "1. 生成 5-8 个应该触发该 Skill 的用户输入（should_trigger: true）\n"
                "2. 生成 3-5 个不应触发该 Skill 的用户输入（should_trigger: false）\n"
                "3. 触发用例应包含中文和英文各种表达方式\n"
                "4. 只输出 JSON 数组，格式为：\n"
                '[{"prompt": "用户输入", "should_trigger": true/false}]\n'
                "不要输出其他任何内容。"
            )
            response = provider.chat([Message(role="user", content=prompt)])

            # 提取 JSON 数组
            json_match = re.search(r"\[.*?\]", response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass  # AI 调用失败时使用默认用例

        # 默认用例（基于 skill_name）
        skill_name = spec.get("skill_name", "skill")
        core_function = spec.get("core_function", "执行相关任务")
        return [
            {"prompt": f"使用 {skill_name}", "should_trigger": True},
            {"prompt": core_function[:50], "should_trigger": True},
            {"prompt": "今天天气怎么样", "should_trigger": False},
            {"prompt": "帮我发一封邮件", "should_trigger": False},
        ]

    @staticmethod
    def _find_skill_path(task: SkillCreationTask) -> str:
        """
        从任务工作区中找到 Skill 目录路径。

        Args:
            task: SkillCreationTask 实例

        Returns:
            Skill 目录的绝对路径字符串。

        Raises:
            TaskNotFoundError: 当工作区不存在时
        """
        if not task.workspace_path:
            raise TaskNotFoundError(f"任务 {task.id} 工作区未初始化")

        skill_path = Path(task.workspace_path)
        if not skill_path.exists():
            raise TaskNotFoundError(f"工作区目录不存在: {task.workspace_path}")

        return str(skill_path)

    @staticmethod
    def _update_task_status(task: SkillCreationTask, new_status: str) -> None:
        """更新任务状态（不提交事务）。"""
        task.transition_to(new_status)

    @staticmethod
    def _log_event(task_id: str, event_type: str, event_data: dict = None) -> None:
        """记录任务事件日志（不提交事务）。"""
        log = TaskEventLog.log(task_id, event_type, event_data)
        db.session.add(log)


# 在模块内导入 re（用于 _generate_evals）
import re
