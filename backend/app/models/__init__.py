"""
backend/app/models/__init__.py

数据模型包初始化。

统一导出所有数据模型类，确保 Alembic 在生成迁移脚本时
能够自动发现所有模型，并在 create_all() 时正确建表。

注意：
    - 所有新增的数据模型都必须在此处导入，否则 Alembic 无法发现
    - 导入顺序需注意外键依赖关系（被依赖的表先导入）
"""

from .model_config import ModelConfig
from .skill_creation_task import SkillCreationTask
from .session import ConversationSession
from .sandbox_test import SandboxTest
from .task_event_log import TaskEventLog

__all__ = [
    "ModelConfig",
    "SkillCreationTask",
    "ConversationSession",
    "SandboxTest",
    "TaskEventLog",
]
