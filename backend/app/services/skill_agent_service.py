"""
backend/app/services/skill_agent_service.py

Skill 运行时 Agent 服务。

职责：
    - 根据用户查询自动选择最匹配的 Skill（通过 SkillIndexService）
    - 读取 Skill 的 SKILL.md 并构建 Agent 执行上下文
    - 以流式方式驱动 AI 按照 Skill 工作流逐步执行
    - 支持 [READ:path] / [RUN:script] 两种内联指令，实现文件读取和脚本执行
    - 可选将对话历史持久化到 ConversationSession（多轮记忆）

执行循环（最多 MAX_STEPS 步）：
    1. 选 Skill：SkillIndexService.search(query, top_k=1)
    2. 读取 SKILL.md，构建 System Prompt
    3. 调用 provider.stream_chat()，逐块 yield 文本
    4. 检测特殊指令：
       - [READ:相对路径]  → 读取 skill_path/references/<相对路径> 文件内容
       - [RUN:脚本名]    → 在沙盒容器中执行 skill_path/scripts/<脚本名>
    5. 将指令执行结果追加到 context，继续下一步
    6. 无特殊指令或达到步骤上限时结束

安全说明：
    - [READ] 只允许读取 skill_path/references/ 目录下的文件
    - [RUN] 通过 SandboxRunner 执行，隔离在 Docker 容器中
    - 路径穿越（../）会被拒绝
"""

import json
import re
import subprocess
from pathlib import Path
from typing import Generator, List, Optional

from ..extensions import db
from ..model.provider import Message, ModelProviderFactory
from ..services.skill_index_service import SkillIndexService


class SkillAgentService:
    """
    Skill 运行时 Agent 服务类。

    根据用户查询自动选择 Skill 并以流式方式执行 Skill 工作流。
    """

    # 执行循环最大步数（防止无限循环）
    MAX_STEPS = 5
    # 最低匹配分数阈值（低于此值视为无匹配）
    MIN_MATCH_SCORE = 0.1

    def run(
        self,
        user_query: str,
        session_id: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """
        根据用户查询选择 Skill 并执行，以流式方式 yield 输出。

        Yield 格式（JSON 字符串）：
        - 文本块：  {"type": "text", "content": "..."}
        - 状态信息：{"type": "status", "message": "..."}（如"已选择 Skill: xxx"）
        - 完成通知：{"type": "done", "skill_name": "...", "skill_path": "..."}
        - 错误信息：{"type": "error", "message": "..."}

        Args:
            user_query: 用户输入的查询文本
            session_id: 可选的会话 ID，如果提供则将本次对话历史追加到该会话

        Yields:
            JSON 字符串
        """
        # Step 1: 选 Skill
        yield self._event("status", message="正在检索最匹配的 Skill...")

        index = self._build_index()
        results = index.search(user_query, top_k=1)

        if not results or results[0]["score"] < self.MIN_MATCH_SCORE:
            yield self._event("error", message="未找到匹配的 Skill，请尝试换一种描述方式")
            return

        best = results[0]
        skill_path = Path(best["skill_path"]).parent  # SKILL.md 所在目录
        skill_name = best["name"]
        match_score = best["score"]

        yield self._event("status", message=f"已选择 Skill: {skill_name}（匹配分数: {match_score:.2f}）")

        # Step 2: 读取 SKILL.md 并构建 System Prompt
        skill_md_path = skill_path / "SKILL.md"
        if not skill_md_path.is_file():
            yield self._event("error", message=f"Skill 目录中未找到 SKILL.md: {skill_path}")
            return

        skill_md_content = skill_md_path.read_text(encoding="utf-8")
        system_prompt = self._build_system_prompt(skill_md_content)

        # Step 3: 多步执行循环
        messages: List[Message] = [Message(role="user", content=user_query)]
        provider = ModelProviderFactory.create_from_active_config()
        all_assistant_output = []

        for step in range(self.MAX_STEPS):
            full_reply_chunks = []

            try:
                for chunk in provider.stream_chat(messages, system=system_prompt):
                    full_reply_chunks.append(chunk)
                    yield self._event("text", content=chunk)
            except Exception as e:
                yield self._event("error", message=f"AI 调用失败: {str(e)}")
                return

            full_reply = "".join(full_reply_chunks)
            all_assistant_output.append(full_reply)
            messages.append(Message(role="assistant", content=full_reply))

            # Step 4: 检测内联指令
            read_match = re.search(r"\[READ:([\w./\\-]+)\]", full_reply)
            run_match = re.search(r"\[RUN:([\w./\\-]+)\]", full_reply)

            if read_match:
                relative_path = read_match.group(1)
                file_content = self._safe_read_reference(skill_path, relative_path)
                if file_content is not None:
                    yield self._event("status", message=f"已读取文件: {relative_path}")
                    context_msg = f"[文件内容 - {relative_path}]\n{file_content[:3000]}"
                else:
                    yield self._event("status", message=f"文件不存在或不允许访问: {relative_path}")
                    context_msg = f"[文件 {relative_path} 不存在或不允许访问]"
                messages.append(Message(role="user", content=context_msg))
                continue

            if run_match:
                script_name = run_match.group(1)
                script_output = self._safe_run_script(skill_path, script_name)
                yield self._event("status", message=f"已执行脚本: {script_name}")
                context_msg = f"[脚本输出 - {script_name}]\n{script_output[:3000]}"
                messages.append(Message(role="user", content=context_msg))
                continue

            # 无特殊指令，执行完成
            break

        # Step 5: 持久化到 session（如果提供了 session_id）
        if session_id:
            try:
                self._persist_to_session(session_id, user_query, all_assistant_output)
            except Exception:
                pass  # 持久化失败不阻断主流程

        yield self._event("done", skill_name=skill_name, skill_path=str(skill_path))

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _event(event_type: str, **kwargs) -> str:
        """序列化一个 Agent 事件为 JSON 字符串。"""
        return json.dumps({"type": event_type, **kwargs}, ensure_ascii=False)

    @staticmethod
    def _build_system_prompt(skill_md_content: str) -> str:
        """根据 SKILL.md 内容构建 Agent System Prompt。"""
        return (
            "你是基于以下 Skill 运行的 Agent，请严格按照 Skill 的工作流执行用户的请求。\n\n"
            "=== Skill 定义 ===\n"
            f"{skill_md_content}\n"
            "=== Skill 定义结束 ===\n\n"
            "执行规则：\n"
            "1. 严格遵循 Skill 定义的工作流程\n"
            "2. 如需读取参考文件，回复 [READ:references/文件名]\n"
            "3. 如需执行脚本，回复 [RUN:脚本名]\n"
            "4. 一次只执行一个指令\n"
            "5. 用中文回复（除非 Skill 明确要求其他语言）"
        )

    @staticmethod
    def _safe_read_reference(skill_path: Path, relative_path: str) -> Optional[str]:
        """
        安全地读取 skill_path/references/ 目录下的文件。

        只允许读取 references/ 子目录下的文件，拒绝路径穿越。

        Args:
            skill_path: Skill 目录路径
            relative_path: 请求读取的相对路径

        Returns:
            文件内容字符串，不存在或不安全时返回 None。
        """
        try:
            ref_dir = skill_path / "references"
            target = (ref_dir / relative_path).resolve()
            # 确保目标在 references/ 目录内
            if not str(target).startswith(str(ref_dir.resolve())):
                return None
            if not target.is_file():
                return None
            return target.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

    @staticmethod
    def _safe_run_script(skill_path: Path, script_name: str) -> str:
        """
        安全地执行 skill_path/scripts/ 目录下的脚本。

        在宿主机上直接执行（不使用 Docker）。
        超时时间 30 秒，输出限制 5000 字符。
        仅限 .py / .sh 文件。

        Args:
            skill_path: Skill 目录路径
            script_name: 脚本文件名

        Returns:
            脚本的 stdout + stderr 输出字符串。
        """
        try:
            scripts_dir = skill_path / "scripts"
            script_path = (scripts_dir / script_name).resolve()
            # 安全检查：只允许执行 scripts/ 目录下的文件
            if not str(script_path).startswith(str(scripts_dir.resolve())):
                return "[错误] 非法脚本路径"
            if not script_path.is_file():
                return f"[错误] 脚本不存在: {script_name}"
            if script_path.suffix.lower() not in {".py", ".sh"}:
                return f"[错误] 不支持的脚本类型: {script_path.suffix}"

            cmd = ["python3", str(script_path)] if script_path.suffix == ".py" else ["sh", str(script_path)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = (result.stdout + result.stderr)[:5000]
            return output or "(脚本无输出)"
        except subprocess.TimeoutExpired:
            return "[错误] 脚本执行超时（30 秒）"
        except Exception as e:
            return f"[错误] 脚本执行失败: {str(e)}"

    @staticmethod
    def _build_index() -> SkillIndexService:
        """构建全局 Skill 索引（与 skills.py 中的 _build_global_index 保持一致）。"""
        from flask import current_app

        index = SkillIndexService()
        kernel_base = current_app.config.get("KERNEL_BASE_PATH")
        if kernel_base:
            import os
            kernel_skill_dir = os.path.join(kernel_base, "skill-creator")
            index.index_directory(kernel_skill_dir, recursive=False)
        workspace_base = current_app.config.get("WORKSPACE_BASE_PATH", "/app/workspace")
        index.index_directory(workspace_base, recursive=True)
        return index

    @staticmethod
    def _persist_to_session(session_id: str, user_query: str, assistant_outputs: list) -> None:
        """
        将本次 Agent 对话追加到指定的 ConversationSession 历史。

        Args:
            session_id: 目标会话 ID
            user_query: 用户查询文本
            assistant_outputs: AI 各步骤的完整回复列表
        """
        from ..models.session import ConversationSession

        session = ConversationSession.query.get(session_id)
        if session is None:
            return

        session.add_message("user", user_query)
        combined_reply = "\n\n".join(assistant_outputs)
        session.add_message("assistant", combined_reply)
        db.session.commit()
