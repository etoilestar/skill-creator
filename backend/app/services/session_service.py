"""
backend/app/services/session_service.py

多轮会话与需求采集服务。

职责：
    - 创建和管理用户与系统之间的对话会话
    - 维护多轮对话历史（消息存储与读取）
    - 调用 AI 模型进行需求采集与引导
    - 将 AI 的结构化输出解析并更新到 RequirementSpec
    - 计算并更新需求完整度评分

业务流程：
    用户发送消息
      → 将消息追加到会话历史
      → 构建 AI 调用上下文（含 skill-creator 创建指南 + 当前需求 + 对话历史）
      → 调用模型获取 AI 回复
      → 解析 AI 回复中的结构化需求更新（JSON 格式）
      → 更新 requirement_spec 和 completeness_score
      → 返回 AI 回复文本给用户

注意：
    - AI 的回复格式约定：文本部分面向用户展示，JSON 代码块包含需求更新
    - completeness_score 由 AI 在每轮对话后评估并更新
    - 只有在 completeness_score >= 80 且用户确认后，才能触发 Skill 创建
"""

import json
import re
import uuid
from datetime import datetime
from typing import Dict, Optional, Tuple

from ..exceptions import SessionNotFoundError
from ..extensions import db
from ..kernel.registry import KernelRegistry
from ..model.provider import Message, ModelProviderFactory
from ..models.session import ConversationSession
from ..models.skill_creation_task import SkillCreationTask


class SessionService:
    """
    多轮会话与需求采集服务类。

    封装会话的创建、消息收发、需求沉淀和状态管理等全部逻辑。
    每次操作都操作数据库持久化，确保会话数据不丢失。
    """

    # AI System Prompt 的基础框架（{skill_creation_guide} 占位符将被替换）
    _SYSTEM_PROMPT_TEMPLATE = """你是 Skill 制造工厂的需求顾问助手，专门帮助用户设计和创建 OpenClaw Skill。

你的核心任务是通过友好的中文多轮对话，帮助用户逐步明确他们想要创建的 Skill 的各个关键要素。

以下是 skill-creator 的完整创建指南，你必须参考这份指南来引导用户：

=== skill-creator 创建指南 ===
{skill_creation_guide}
=== 创建指南结束 ===

在每次回复中，你必须：
1. 用自然的中文与用户对话，解答疑问，引导用户思考
2. 每次只问 1-2 个问题，不要一次性列出所有问题
3. 在回复末尾，用如下格式输出当前已收集到的结构化需求（JSON 格式）：

```requirement_spec
{{
  "skill_name": "xxx",
  "display_name": "xxx（中文显示名）",
  "core_function": "这个 Skill 能做什么",
  "trigger_contexts": ["场景1", "场景2"],
  "not_for": ["不适用场景1"],
  "expected_output": "预期输出描述",
  "needs_scripts": false,
  "script_requirements": null,
  "edge_cases": [],
  "dependencies": [],
  "completeness_score": 0
}}
```

completeness_score 的评分标准（0-100）：
- skill_name 填写：+10
- core_function 填写：+15
- trigger_contexts 有 3 条以上：+20
- not_for 填写：+15
- expected_output 填写：+15
- edge_cases 有内容：+10
- needs_scripts 明确：+10
- 整体需求清晰完整：+5

只有当 completeness_score >= 80 时，用户才能触发 Skill 创建。
"""

    def create_session(self, initial_message: str) -> ConversationSession:
        """
        创建新会话并处理用户的第一条消息。

        Args:
            initial_message: 用户输入的初始需求描述（中文）

        Returns:
            新创建的 ConversationSession 实例（已持久化）。
        """
        # 创建会话实例
        session = ConversationSession(
            id=str(uuid.uuid4()),
            messages=[],
            requirement_spec=self._empty_requirement_spec(),
            completeness_score=0,
            phase=ConversationSession.PHASE_GATHERING,
        )
        db.session.add(session)
        db.session.flush()  # 获取 ID 但不提交

        # 处理第一条消息
        ai_reply, updated_spec, score = self._process_message(
            session, initial_message
        )

        # 更新会话状态
        session.add_message("user", initial_message)
        session.add_message("assistant", ai_reply)
        session.requirement_spec = updated_spec
        session.completeness_score = score

        db.session.commit()
        return session

    def send_message(self, session_id: str, user_message: str) -> Tuple[str, ConversationSession]:
        """
        在现有会话中发送一条用户消息，获取 AI 回复。

        Args:
            session_id: 会话 ID
            user_message: 用户消息内容（中文）

        Returns:
            (ai_reply_text, updated_session) 元组。

        Raises:
            SessionNotFoundError: 当会话 ID 不存在时
        """
        session = ConversationSession.query.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"会话不存在: {session_id}")

        # 调用 AI 并获取结构化更新
        ai_reply, updated_spec, score = self._process_message(session, user_message)

        # 持久化消息和需求更新
        session.add_message("user", user_message)
        session.add_message("assistant", ai_reply)
        session.requirement_spec = updated_spec
        session.completeness_score = score

        # 需求完整度达到 80 分时，自动进入结构化确认阶段
        if score >= 80 and session.phase == ConversationSession.PHASE_GATHERING:
            session.phase = ConversationSession.PHASE_STRUCTURING

        db.session.commit()
        return ai_reply, session

    def get_session(self, session_id: str) -> ConversationSession:
        """
        获取指定会话。

        Args:
            session_id: 会话 ID

        Returns:
            ConversationSession 实例。

        Raises:
            SessionNotFoundError: 当会话不存在时
        """
        session = ConversationSession.query.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"会话不存在: {session_id}")
        return session

    def confirm_and_start_creation(self, session_id: str) -> SkillCreationTask:
        """
        用户确认需求，触发 Skill 创建任务。

        将当前会话的 RequirementSpec 快照到 SkillCreationTask，
        然后将任务提交给 Celery 异步执行。

        Args:
            session_id: 会话 ID

        Returns:
            新创建的 SkillCreationTask 实例。

        Raises:
            SessionNotFoundError: 当会话不存在时
            RequirementIncompleteError: 当需求完整度不足 80 分时
        """
        from ..exceptions import RequirementIncompleteError
        from ..tasks.skill_creation_task import create_skill_task

        session = self.get_session(session_id)

        if session.completeness_score < 80:
            raise RequirementIncompleteError(
                f"当前需求完整度 {session.completeness_score} 分，"
                "需要达到 80 分以上才能触发创建"
            )

        # 从需求中提取 skill_name
        spec = session.requirement_spec or {}
        skill_name = spec.get("skill_name", f"skill-{str(uuid.uuid4())[:8]}")

        # 创建 SkillCreationTask（状态为 PENDING）
        task = SkillCreationTask(
            id=str(uuid.uuid4()),
            skill_name=skill_name,
            status=SkillCreationTask.STATUS_PENDING,
            requirement_spec=spec,
            kernel_id="skill-creator",
        )
        db.session.add(task)

        # 更新会话状态和关联 task_id
        session.task_id = task.id
        session.phase = ConversationSession.PHASE_CREATING

        db.session.commit()

        # 提交 Celery 异步任务
        celery_result = create_skill_task.delay(task.id, spec)
        task.celery_task_id = celery_result.id
        db.session.commit()

        return task

    def _process_message(
        self,
        session: ConversationSession,
        user_message: str,
    ) -> Tuple[str, dict, int]:
        """
        调用 AI 处理用户消息，返回 AI 回复、更新后的需求和完整度分数。

        处理流程：
        1. 从 KernelRegistry 加载 skill-creator 指南
        2. 构建 System Prompt（注入创建指南）
        3. 将历史消息 + 新消息传给 AI
        4. 解析 AI 回复中的 requirement_spec JSON 代码块
        5. 提取 completeness_score

        Args:
            session: 当前会话实例
            user_message: 用户新消息

        Returns:
            (ai_reply_text, updated_requirement_spec, completeness_score) 三元组。
        """
        # 获取 skill-creator 创建指南（作为 System Prompt 的核心）
        try:
            registry = KernelRegistry.get_instance()
            kernel = registry.get_kernel("skill-creator")
            guide = kernel.get_skill_creation_guide()
        except Exception:
            # 内核加载失败时，使用降级模式（无指南）
            guide = "（skill-creator 指南暂不可用）"

        # 构建 System Prompt
        system_prompt = self._SYSTEM_PROMPT_TEMPLATE.format(
            skill_creation_guide=guide
        )

        # 将历史消息转换为 Message 对象列表
        history = []
        for msg in (session.messages or []):
            history.append(Message(role=msg["role"], content=msg["content"]))
        history.append(Message(role="user", content=user_message))

        # 调用 AI 模型
        provider = ModelProviderFactory.create_from_active_config()
        ai_reply = provider.chat(history, system=system_prompt)

        # 从 AI 回复中解析 requirement_spec（提取 JSON 代码块）
        updated_spec, score = self._extract_requirement_spec(
            ai_reply, session.requirement_spec or self._empty_requirement_spec()
        )

        # 从 AI 回复中去除 JSON 代码块，保留面向用户的文本部分
        display_reply = re.sub(
            r"```requirement_spec\s*\{.*?\}\s*```",
            "",
            ai_reply,
            flags=re.DOTALL,
        ).strip()

        return display_reply or ai_reply, updated_spec, score

    def _extract_requirement_spec(
        self, ai_reply: str, current_spec: dict
    ) -> Tuple[dict, int]:
        """
        从 AI 回复文本中提取 requirement_spec JSON 代码块。

        如果解析失败，返回未修改的当前需求（容错处理）。

        Args:
            ai_reply: AI 的完整回复文本
            current_spec: 当前已有的需求字典（作为回退值）

        Returns:
            (updated_spec_dict, completeness_score) 元组。
        """
        # 查找 ```requirement_spec ... ``` 代码块
        pattern = r"```requirement_spec\s*(\{.*?\})\s*```"
        match = re.search(pattern, ai_reply, re.DOTALL)
        if not match:
            # AI 没有返回更新，保持当前需求不变
            return current_spec, current_spec.get("completeness_score", 0)

        try:
            spec = json.loads(match.group(1))
            # 确保所有必要字段存在（防止 AI 漏掉字段）
            merged = {**self._empty_requirement_spec(), **current_spec, **spec}
            score = int(merged.get("completeness_score", 0))
            return merged, score
        except (json.JSONDecodeError, ValueError):
            # 解析失败，保持当前需求
            return current_spec, current_spec.get("completeness_score", 0)

    @staticmethod
    def _empty_requirement_spec() -> dict:
        """返回空的 RequirementSpec 模板字典。"""
        return {
            "skill_name": "",
            "display_name": "",
            "core_function": "",
            "trigger_contexts": [],
            "not_for": [],
            "expected_output": "",
            "needs_scripts": False,
            "script_requirements": None,
            "edge_cases": [],
            "dependencies": [],
            "completeness_score": 0,
        }
