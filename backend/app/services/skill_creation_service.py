"""
backend/app/services/skill_creation_service.py

Skill 创建编排服务。

职责：
    - 根据结构化需求（RequirementSpec）协调 AI 模型调用和内核适配
    - 通过 KernelAdapter 获取创建指南和 Prompt 模板
    - 调用 AI 模型生成 SKILL.md 内容
    - 对生成内容执行内核校验（validate_skill_structure）
    - 将通过校验的 Skill 文件写入工作区
    - 更新任务状态并记录全程事件日志

业务流程（由 Celery 任务 create_skill_task 调用）：
    1. 加载 skill-creator 内核，获取创建指南和 Prompt 模板
    2. 构建 AI 调用 Prompt（注入需求 JSON + 创建指南）
    3. 调用 AI 模型生成 SKILL.md 内容
    4. 解析并校验生成的 SKILL.md 格式
    5. 如校验失败，最多自动修正 2 次（将错误反馈给 AI 重新生成）
    6. 将通过校验的 Skill 文件写入工作区
    7. 如需要脚本，调用 AI 生成 scripts/ 内容
    8. 更新任务状态为 CREATED，写入事件日志

注意：
    - 本服务是纯业务逻辑层，不直接访问内核目录（通过 KernelAdapter）
    - 生成失败时更新任务状态为 CREATION_FAILED，并记录详细错误信息
"""

import json
import os
import re
import traceback
from pathlib import Path
from typing import Optional

from ..exceptions import SkillGenerationError, SkillValidationError
from ..extensions import db
from ..kernel.registry import KernelRegistry
from ..model.provider import Message, ModelProviderFactory
from ..models.skill_creation_task import SkillCreationTask
from ..models.task_event_log import TaskEventLog


class SkillCreationService:
    """
    Skill 创建编排服务类。

    封装从"结构化需求"到"工作区 Skill 文件"的完整创建流程。
    通常由 Celery 异步任务调用，不在 HTTP 请求生命周期内同步执行。
    """

    # AI 生成 SKILL.md 时，最多允许自动修正的次数
    MAX_AUTO_FIX_ATTEMPTS = 2

    def create_skill(self, task_id: str) -> str:
        """
        执行完整的 Skill 创建流程，返回工作区路径。

        Args:
            task_id: SkillCreationTask 的 ID

        Returns:
            创建的 Skill 在工作区中的目录路径。

        Raises:
            SkillGenerationError: 当 AI 生成内容不合规且无法自动修正时
            Exception: 其他未预期错误（会被 Celery 任务捕获并记录）
        """
        task = SkillCreationTask.query.get(task_id)
        if task is None:
            raise ValueError(f"任务不存在: {task_id}")

        # 更新任务状态为"创建中"
        task.transition_to(SkillCreationTask.STATUS_CREATING)
        self._log_event(task_id, TaskEventLog.ET_STATUS_CHANGE, {
            "from": SkillCreationTask.STATUS_PENDING,
            "to": SkillCreationTask.STATUS_CREATING,
        })
        db.session.commit()

        try:
            # Step 1: 加载内核和需求
            kernel = KernelRegistry.get_instance().get_kernel("skill-creator")
            spec = task.requirement_spec or {}
            skill_name = task.skill_name or spec.get("skill_name", "unnamed-skill")

            # Step 2: 生成 SKILL.md（含自动修正）
            skill_md_content = self._generate_skill_md_with_retry(
                kernel, spec, skill_name, task_id
            )

            # Step 3: 写入工作区
            workspace_path = self._write_to_workspace(task_id, skill_name, skill_md_content)

            # Step 4: 如需要脚本，生成 scripts/ 内容
            if spec.get("needs_scripts") and spec.get("script_requirements"):
                self._generate_scripts(
                    kernel, spec, skill_name, workspace_path, task_id
                )

            # Step 5: 更新任务状态为 CREATED
            task.status = SkillCreationTask.STATUS_CREATED
            task.workspace_path = workspace_path
            task.skill_name = skill_name
            task.error_message = None
            self._log_event(task_id, TaskEventLog.ET_STATUS_CHANGE, {
                "from": SkillCreationTask.STATUS_CREATING,
                "to": SkillCreationTask.STATUS_CREATED,
                "workspace_path": workspace_path,
            })
            db.session.commit()

            return workspace_path

        except Exception as e:
            # 记录失败状态和错误信息
            task.transition_to(SkillCreationTask.STATUS_CREATION_FAILED)
            task.error_message = f"Skill 创建失败: {str(e)[:500]}"
            task.error_detail = traceback.format_exc()
            self._log_event(task_id, TaskEventLog.ET_ERROR, {
                "error": str(e),
                "traceback": traceback.format_exc()[:2000],
            })
            db.session.commit()
            raise

    def _generate_skill_md_with_retry(
        self,
        kernel,
        spec: dict,
        skill_name: str,
        task_id: str,
    ) -> str:
        """
        调用 AI 生成 SKILL.md，支持校验失败后自动修正（最多 MAX_AUTO_FIX_ATTEMPTS 次）。

        自动修正流程：
        - 第一次生成失败 → 将校验错误反馈给 AI，请求修正
        - 第二次修正后再次校验
        - 仍失败则抛出 SkillValidationError

        Args:
            kernel: KernelAdapter 实例
            spec: 结构化需求字典
            skill_name: Skill 名称
            task_id: 任务 ID（用于日志记录）

        Returns:
            通过校验的 SKILL.md 内容字符串。
        """
        guide = kernel.get_skill_creation_guide()
        template = kernel.get_creation_prompt_template()
        provider = ModelProviderFactory.create_from_active_config()

        skill_md = None
        validation_errors = []

        for attempt in range(1 + self.MAX_AUTO_FIX_ATTEMPTS):
            # 构建 Prompt
            if attempt == 0:
                # 首次生成
                prompt = template.format(
                    skill_creation_guide=guide,
                    skill_name=skill_name,
                    requirement_spec_json=json.dumps(spec, ensure_ascii=False, indent=2),
                )
                messages = [Message(role="user", content=prompt)]
            else:
                # 自动修正：将上次的输出和校验错误反馈给 AI
                fix_prompt = (
                    f"上次生成的 SKILL.md 未通过校验，存在以下问题：\n"
                    + "\n".join(f"- {e}" for e in validation_errors)
                    + f"\n\n上次生成的内容：\n```\n{skill_md}\n```\n\n"
                    "请修正上述问题，重新生成完整的 SKILL.md 文件（只输出文件内容）："
                )
                messages = [
                    Message(role="user", content=messages[0].content),
                    Message(role="assistant", content=skill_md or ""),
                    Message(role="user", content=fix_prompt),
                ]

            # 调用 AI
            raw_output = provider.chat(messages)
            skill_md = self._extract_skill_md_content(raw_output)

            # 记录模型调用日志
            self._log_event(task_id, TaskEventLog.ET_MODEL_CALL, {
                "attempt": attempt + 1,
                "output_length": len(skill_md),
            })

            # 校验生成的 Skill 结构
            validation = self._validate_skill_md_content(kernel, skill_name, skill_md)

            if validation.valid:
                return skill_md
            else:
                validation_errors = validation.errors
                self._log_event(task_id, TaskEventLog.ET_KERNEL_CALL, {
                    "method": "validate_skill_structure",
                    "valid": False,
                    "errors": validation_errors,
                })

        # 超过最大修正次数，仍然失败
        raise SkillValidationError(
            f"Skill 内容经过 {1 + self.MAX_AUTO_FIX_ATTEMPTS} 次生成仍未通过校验，"
            f"错误：{'; '.join(validation_errors)}"
        )

    def _validate_skill_md_content(self, kernel, skill_name: str, content: str) -> object:
        """
        在临时目录中校验 SKILL.md 内容。

        将生成内容写入临时文件，调用 kernel.validate_skill_structure() 校验，
        然后清理临时文件。

        Args:
            kernel: KernelAdapter 实例
            skill_name: Skill 名称（用于创建临时目录名）
            content: SKILL.md 文件内容

        Returns:
            ValidationResult 对象。
        """
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            skill_dir = Path(tmp_dir) / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
            return kernel.validate_skill_structure(str(skill_dir))

    def _write_to_workspace(
        self, task_id: str, skill_name: str, skill_md_content: str
    ) -> str:
        """
        将生成的 SKILL.md 写入用户工作区。

        工作区路径规范：
            WORKSPACE_BASE_PATH/{task_id}/{skill_name}/SKILL.md

        Args:
            task_id: 任务 ID（作为工作区子目录名）
            skill_name: Skill 名称（作为 Skill 目录名）
            skill_md_content: SKILL.md 文件内容

        Returns:
            Skill 目录的绝对路径字符串。
        """
        from flask import current_app

        workspace_base = current_app.config.get("WORKSPACE_BASE_PATH", "/app/workspace")
        skill_dir = Path(workspace_base) / task_id / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        skill_md_path = skill_dir / "SKILL.md"
        skill_md_path.write_text(skill_md_content, encoding="utf-8")

        return str(skill_dir)

    def _generate_scripts(
        self, kernel, spec: dict, skill_name: str, workspace_path: str, task_id: str
    ) -> None:
        """
        根据需求生成 scripts/ 目录中的脚本文件。

        只有当 spec.needs_scripts 为 True 且 spec.script_requirements 有内容时才执行。

        Args:
            kernel: KernelAdapter 实例
            spec: 结构化需求字典
            skill_name: Skill 名称
            workspace_path: Skill 工作区目录路径
            task_id: 任务 ID（用于日志记录）
        """
        provider = ModelProviderFactory.create_from_active_config()
        script_requirements = spec.get("script_requirements", "")

        prompt = (
            f"请根据以下脚本需求，为 '{skill_name}' Skill 编写 Python 脚本。\n\n"
            f"脚本需求：{script_requirements}\n\n"
            "要求：\n"
            "1. 使用 Python 3 编写\n"
            "2. 脚本文件放在 scripts/ 目录下\n"
            "3. 每个脚本用以下格式输出：\n"
            "   文件名: scripts/xxx.py\n"
            "   ```python\n"
            "   [脚本内容]\n"
            "   ```\n"
            "4. 只输出脚本内容，不要额外解释"
        )

        scripts_output = provider.chat([Message(role="user", content=prompt)])
        self._log_event(task_id, TaskEventLog.ET_MODEL_CALL, {
            "purpose": "generate_scripts",
            "output_length": len(scripts_output),
        })

        # 解析并写入脚本文件
        self._write_scripts_from_output(workspace_path, scripts_output)

    def _write_scripts_from_output(self, workspace_path: str, scripts_output: str) -> None:
        """
        解析 AI 输出的脚本内容并写入 scripts/ 目录。

        Args:
            workspace_path: Skill 工作区目录路径
            scripts_output: AI 生成的脚本内容文本
        """
        # 匹配 "文件名: scripts/xxx.py" 后面的 ```python ... ``` 代码块
        pattern = r"文件名:\s*(scripts/[\w./]+\.py)\s*```python\s*(.*?)```"
        matches = re.findall(pattern, scripts_output, re.DOTALL)

        scripts_dir = Path(workspace_path) / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in matches:
            # 安全校验：只允许写入 scripts/ 目录下的 .py 文件
            safe_name = Path(filename).name
            if not safe_name.endswith(".py"):
                continue
            script_path = scripts_dir / safe_name
            script_path.write_text(content.strip(), encoding="utf-8")

    @staticmethod
    def _extract_skill_md_content(raw_output: str) -> str:
        """
        从 AI 输出中提取 SKILL.md 内容。

        如果 AI 输出包含 ```markdown 代码块，提取代码块内容；
        否则直接使用整个输出（AI 可能直接输出文件内容而不加代码块）。

        Args:
            raw_output: AI 的原始输出文本

        Returns:
            SKILL.md 文件内容字符串。
        """
        # 尝试提取 markdown 代码块
        pattern = r"```(?:markdown|yaml|md)?\s*(---.*?)```"
        match = re.search(pattern, raw_output, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 如果没有代码块，查找以 --- 开头的 frontmatter
        if raw_output.strip().startswith("---"):
            return raw_output.strip()

        # 最后回退：返回整个输出
        return raw_output.strip()

    @staticmethod
    def _log_event(task_id: str, event_type: str, event_data: dict = None) -> None:
        """
        记录任务事件日志（不提交事务，由调用方统一提交）。

        Args:
            task_id: 任务 ID
            event_type: 事件类型（使用 TaskEventLog 枚举常量）
            event_data: 事件附加数据
        """
        log = TaskEventLog.log(task_id, event_type, event_data)
        db.session.add(log)
