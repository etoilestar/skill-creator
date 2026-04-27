"""
backend/app/models/task_event_log.py

任务事件日志数据模型。

职责：
    - 记录每个 Skill 创建任务的完整事件流水线
    - 支持追溯一个 Skill 从需求进入到测试完成的全过程
    - 记录模型调用、内核调用、文件操作、状态变更等所有关键事件

事件类型（event_type 字段）：
    status_change   任务状态发生变更
    model_call      调用 AI 模型（记录 token 消耗、耗时）
    kernel_call     调用 skill-creator 内核（记录调用方法和结果）
    file_operation  文件读写删除操作
    sandbox_start   沙盒测试启动
    sandbox_done    沙盒测试完成（记录结果摘要）
    error           发生错误
    user_action     用户主动触发的操作（如确认需求、触发创建）

日志用途：
    - 开发调试：追踪具体步骤的执行情况
    - 运营监控：统计模型调用成本、任务成功率
    - 用户体验：在前端展示任务进度时序
"""

import uuid
from datetime import datetime

from ..extensions import db


class TaskEventLog(db.Model):
    """
    任务事件日志数据模型。

    Attributes:
        id: 日志记录 UUID，主键
        task_id: 关联的 SkillCreationTask ID
        event_type: 事件类型（见模块文档中的事件类型说明）
        event_data: 事件详细数据（JSON），内容因 event_type 不同而不同
        created_at: 事件发生时间（UTC）
    """

    __tablename__ = "task_event_logs"

    # 事件类型常量
    ET_STATUS_CHANGE = "status_change"
    ET_MODEL_CALL = "model_call"
    ET_KERNEL_CALL = "kernel_call"
    ET_FILE_OPERATION = "file_operation"
    ET_SANDBOX_START = "sandbox_start"
    ET_SANDBOX_DONE = "sandbox_done"
    ET_ERROR = "error"
    ET_USER_ACTION = "user_action"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="日志记录唯一标识符（UUID）",
    )
    task_id = db.Column(
        db.String(36),
        db.ForeignKey("skill_creation_tasks.id"),
        nullable=False,
        index=True,
        comment="关联的 Skill 创建任务 ID（已建索引，便于按任务查询日志）",
    )
    event_type = db.Column(
        db.String(100),
        nullable=False,
        comment="事件类型，见枚举常量定义",
    )
    event_data = db.Column(
        db.JSON,
        nullable=True,
        comment="事件详细数据（JSON），不同事件类型有不同的 schema",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        index=True,
        comment="事件发生时间（UTC，已建索引便于时序查询）",
    )

    # 关联关系
    task = db.relationship("SkillCreationTask", back_populates="event_logs")

    @classmethod
    def log(cls, task_id: str, event_type: str, event_data: dict = None) -> "TaskEventLog":
        """
        工厂方法：创建并返回一条事件日志记录（需要调用方自行提交数据库事务）。

        Args:
            task_id: 任务 ID
            event_type: 事件类型（使用枚举常量）
            event_data: 事件附加数据（JSON 可序列化的字典）

        Returns:
            未提交的 TaskEventLog 实例，调用方负责 db.session.add() 和 commit()
        """
        return cls(task_id=task_id, event_type=event_type, event_data=event_data or {})

    def to_dict(self) -> dict:
        """
        将日志记录序列化为字典，用于 API 响应。

        Returns:
            包含日志信息的字典。
        """
        return {
            "id": self.id,
            "task_id": self.task_id,
            "event_type": self.event_type,
            "event_data": self.event_data or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<TaskEventLog {self.id} task={self.task_id} type={self.event_type}>"
