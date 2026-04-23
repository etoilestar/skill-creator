"""
backend/app/models/skill_creation_task.py

Skill 创建任务数据模型。

职责：
    - 记录每一次 Skill 创建任务的全生命周期状态
    - 存储创建所使用的结构化需求、工作区路径、使用的内核信息
    - 维护任务状态机（草稿→等待→创建中→已创建→测试中→通过/失败）
    - 提供错误信息存储，便于失败分析和用户提示

状态机说明（status 字段）：
    DRAFT           草稿，需求采集中尚未确认
    PENDING         需求已确认，等待 Celery Worker 开始执行
    CREATING        Celery Worker 正在执行 Skill 创建
    CREATED         Skill 文件已成功生成，等待测试或用户编辑
    TESTING         沙盒测试执行中
    PASSED          沙盒测试通过
    FAILED          沙盒测试未通过（Skill 效果不达标）
    CREATION_FAILED 创建失败（AI 调用失败、校验失败等）
    TEST_ERROR      沙盒执行异常（非测试结果，而是执行环境问题）
    ITERATING       用户基于测试结果修改 Skill，准备重新测试
"""

import uuid
from datetime import datetime

from ..extensions import db


class SkillCreationTask(db.Model):
    """
    Skill 创建任务数据模型。

    Attributes:
        id: 任务 UUID，主键
        skill_name: 目标 Skill 名称（lowercase kebab-case）
        status: 当前任务状态（见状态机说明）
        requirement_spec: 创建所使用的结构化需求对象（JSON）
        workspace_path: 工作区绝对路径（容器内路径）
        kernel_id: 执行创建时使用的内核 ID（如 "skill-creator"）
        celery_task_id: Celery 异步任务 ID，用于查询任务进度
        error_message: 失败时的错误描述（面向用户的中文说明）
        error_detail: 失败时的完整错误堆栈（面向开发者）
        created_at: 任务创建时间
        updated_at: 任务最后更新时间
    """

    __tablename__ = "skill_creation_tasks"

    # ------------------------------------------------------------------
    # 任务状态枚举值
    # ------------------------------------------------------------------
    STATUS_DRAFT = "draft"
    STATUS_PENDING = "pending"
    STATUS_CREATING = "creating"
    STATUS_CREATED = "created"
    STATUS_TESTING = "testing"
    STATUS_PASSED = "passed"
    STATUS_FAILED = "failed"
    STATUS_CREATION_FAILED = "creation_failed"
    STATUS_TEST_ERROR = "test_error"
    STATUS_ITERATING = "iterating"

    # 允许触发测试的状态集合
    TESTABLE_STATUSES = {STATUS_CREATED, STATUS_FAILED, STATUS_ITERATING}

    # 允许重试创建的状态集合
    RETRYABLE_STATUSES = {STATUS_CREATION_FAILED}

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="任务唯一标识符（UUID）",
    )
    skill_name = db.Column(
        db.String(100),
        nullable=True,
        comment="目标 Skill 名称（lowercase kebab-case），创建完成后填入",
    )
    status = db.Column(
        db.String(50),
        nullable=False,
        default=STATUS_DRAFT,
        comment="任务当前状态，详见状态机枚举值",
    )
    requirement_spec = db.Column(
        db.JSON,
        nullable=True,
        comment="触发创建时使用的结构化需求对象（快照），后续修改不影响此字段",
    )
    workspace_path = db.Column(
        db.String(500),
        nullable=True,
        comment="工作区绝对路径（容器内路径），用于文件管理和沙盒测试",
    )
    kernel_id = db.Column(
        db.String(100),
        nullable=True,
        default="skill-creator",
        comment="执行创建时使用的内核 ID，便于追溯和版本管理",
    )
    celery_task_id = db.Column(
        db.String(200),
        nullable=True,
        comment="Celery 异步任务 ID，可通过 Celery API 查询任务实时进度",
    )
    error_message = db.Column(
        db.Text,
        nullable=True,
        comment="面向用户的中文错误描述，失败时展示给用户",
    )
    error_detail = db.Column(
        db.Text,
        nullable=True,
        comment="面向开发者的完整错误堆栈，记录详细技术信息",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="任务创建时间（UTC）",
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="任务最后更新时间（UTC）",
    )

    # 关联关系
    session = db.relationship(
        "ConversationSession",
        back_populates="task",
        uselist=False,
        foreign_keys="ConversationSession.task_id",
    )
    sandbox_tests = db.relationship(
        "SandboxTest",
        back_populates="task",
        order_by="SandboxTest.executed_at.desc()",
    )
    event_logs = db.relationship(
        "TaskEventLog",
        back_populates="task",
        order_by="TaskEventLog.created_at.desc()",
    )

    def transition_to(self, new_status: str) -> None:
        """
        执行任务状态转换。

        Args:
            new_status: 目标状态

        Raises:
            ValueError: 当目标状态不在允许的状态枚举中时
        """
        valid_statuses = {
            self.STATUS_DRAFT, self.STATUS_PENDING, self.STATUS_CREATING,
            self.STATUS_CREATED, self.STATUS_TESTING, self.STATUS_PASSED,
            self.STATUS_FAILED, self.STATUS_CREATION_FAILED,
            self.STATUS_TEST_ERROR, self.STATUS_ITERATING,
        }
        if new_status not in valid_statuses:
            raise ValueError(f"非法任务状态: {new_status}")
        self.status = new_status

    def to_dict(self) -> dict:
        """
        将任务序列化为字典，用于 API 响应。

        Returns:
            包含任务信息的字典（不含敏感信息）。
        """
        return {
            "id": self.id,
            "skill_name": self.skill_name,
            "status": self.status,
            "requirement_spec": self.requirement_spec,
            "kernel_id": self.kernel_id,
            "error_message": self.error_message,
            "can_test": self.status in self.TESTABLE_STATUSES,
            "can_retry": self.status in self.RETRYABLE_STATUSES,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<SkillCreationTask {self.id} skill={self.skill_name} status={self.status}>"
