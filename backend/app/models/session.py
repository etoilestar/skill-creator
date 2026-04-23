"""
backend/app/models/session.py

对话会话数据模型。

职责：
    - 存储用户与系统之间的多轮对话历史
    - 维护当前已沉淀的结构化需求（RequirementSpec）
    - 记录会话所处的阶段（需求采集 / 结构化确认 / 创建中 / 已完成）
    - 支持需求完整度评分，驱动前端显示"是否可以开始创建"

数据流说明：
    - 用户发消息 → SessionService 更新 messages 字段 → AI 返回更新后的 requirement_spec
    - completeness_score 达到 80 分时，前端可以显示"开始创建"按钮
    - 确认创建后，从 session 中取出 requirement_spec 传给 SkillCreationService
"""

import uuid
from datetime import datetime

from ..extensions import db


class ConversationSession(db.Model):
    """
    对话会话数据模型。

    一个 Session 对应一次完整的 Skill 需求采集过程，
    从用户输入初始想法开始，到结构化需求被确认为止。

    Attributes:
        id: 会话 UUID，主键
        task_id: 关联的 SkillCreationTask ID（会话确认后创建任务时填入）
        messages: 完整对话历史，JSON 数组，每条消息格式：
                  {"role": "user"/"assistant", "content": "...", "timestamp": "..."}
        requirement_spec: 当前已结构化的需求对象（JSON），随对话逐步完善
        completeness_score: 需求完整度评分（0-100），由 AI 在每轮对话后更新
        phase: 会话当前阶段枚举值
        created_at: 创建时间
        updated_at: 最后更新时间
    """

    __tablename__ = "conversation_sessions"

    # ------------------------------------------------------------------
    # 会话阶段枚举值（phase 字段使用）
    # ------------------------------------------------------------------
    PHASE_GATHERING = "gathering"        # 需求采集中（AI 多轮提问补全）
    PHASE_STRUCTURING = "structuring"    # 结构化确认中（用户确认 RequirementSpec）
    PHASE_CREATING = "creating"          # 已触发创建，等待任务完成
    PHASE_DONE = "done"                  # 会话结束

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="会话唯一标识符（UUID）",
    )
    task_id = db.Column(
        db.String(36),
        db.ForeignKey("skill_creation_tasks.id"),
        nullable=True,
        comment="关联的 Skill 创建任务 ID，会话确认创建后填入",
    )
    messages = db.Column(
        db.JSON,
        nullable=False,
        default=list,
        comment="完整对话历史，JSON 数组，按时间顺序存储所有消息",
    )
    requirement_spec = db.Column(
        db.JSON,
        nullable=True,
        comment="当前已结构化的需求对象，随每轮对话逐步完善",
    )
    completeness_score = db.Column(
        db.Integer,
        nullable=False,
        default=0,
        comment="需求完整度评分（0-100），达到 80 分时可触发 Skill 创建",
    )
    phase = db.Column(
        db.String(50),
        nullable=False,
        default=PHASE_GATHERING,
        comment="会话当前阶段：gathering / structuring / creating / done",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="会话创建时间（UTC）",
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="会话最后更新时间（UTC）",
    )

    # 关联关系（反向引用）
    task = db.relationship("SkillCreationTask", back_populates="session", foreign_keys=[task_id])

    def add_message(self, role: str, content: str) -> None:
        """
        向对话历史中追加一条消息。

        Args:
            role: 消息角色（"user" 或 "assistant"）
            content: 消息内容
        """
        messages = list(self.messages or [])
        messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.messages = messages

    def to_dict(self) -> dict:
        """
        将会话序列化为字典，用于 API 响应。

        Returns:
            包含会话完整信息的字典。
        """
        return {
            "id": self.id,
            "task_id": self.task_id,
            "messages": self.messages or [],
            "requirement_spec": self.requirement_spec,
            "completeness_score": self.completeness_score,
            "phase": self.phase,
            "can_create": self.completeness_score >= 80,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<ConversationSession {self.id} phase={self.phase} score={self.completeness_score}>"
