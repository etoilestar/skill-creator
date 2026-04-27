"""
backend/app/models/sandbox_test.py

沙盒测试记录数据模型。

职责：
    - 记录每次沙盒测试的执行结果
    - 存储触发精度测试报告、结构校验结果、脚本校验结果
    - 保留测试时使用的测试用例（evals），便于复现和对比
    - 存储沙盒 Docker 的原始输出日志，用于调试

与 SkillCreationTask 的关系：
    - 一个 Task 可以有多次测试记录（每次迭代后重新测试）
    - 最新的测试结果决定 Task 的 PASSED/FAILED 状态
"""

import uuid
from datetime import datetime

from ..extensions import db


class SandboxTest(db.Model):
    """
    沙盒测试记录数据模型。

    Attributes:
        id: 测试记录 UUID，主键
        task_id: 关联的 SkillCreationTask ID
        status: 测试状态（running / passed / failed / error / timeout）
        trigger_accuracy: 描述触发精度（0.0-1.0），来自 eval_description.py
        total_cases: 测试用例总数
        passed_cases: 通过的测试用例数
        test_results: 完整的测试结果 JSON（来自 eval_description.py 的 report）
        structure_valid: Skill 目录结构是否合规（布尔值）
        structure_errors: 结构校验错误详情（JSON 数组）
        evals_used: 本次测试使用的测试用例 JSON
        raw_output: Docker 容器执行的原始 stdout/stderr 输出
        executed_at: 测试执行时间（UTC）
        duration_seconds: 执行耗时（秒）
        celery_task_id: 关联的 Celery 任务 ID
    """

    __tablename__ = "sandbox_tests"

    # 测试状态枚举值
    STATUS_RUNNING = "running"
    STATUS_PASSED = "passed"
    STATUS_FAILED = "failed"
    STATUS_ERROR = "error"
    STATUS_TIMEOUT = "timeout"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="测试记录唯一标识符（UUID）",
    )
    task_id = db.Column(
        db.String(36),
        db.ForeignKey("skill_creation_tasks.id"),
        nullable=False,
        comment="关联的 Skill 创建任务 ID",
    )
    status = db.Column(
        db.String(50),
        nullable=False,
        default=STATUS_RUNNING,
        comment="测试状态：running / passed / failed / error / timeout",
    )
    trigger_accuracy = db.Column(
        db.Float,
        nullable=True,
        comment="描述触发精度（0.0-1.0），来自 eval_description.py 的评估结果",
    )
    total_cases = db.Column(
        db.Integer,
        nullable=True,
        comment="本次测试的用例总数",
    )
    passed_cases = db.Column(
        db.Integer,
        nullable=True,
        comment="通过的测试用例数",
    )
    test_results = db.Column(
        db.JSON,
        nullable=True,
        comment="完整的测试结果 JSON，来自 eval_description.py 的标准 report 格式",
    )
    structure_valid = db.Column(
        db.Boolean,
        nullable=True,
        comment="Skill 目录结构是否符合 OpenClaw 规范",
    )
    structure_errors = db.Column(
        db.JSON,
        nullable=True,
        comment="结构校验的错误列表（JSON 数组），structure_valid 为 False 时有值",
    )
    evals_used = db.Column(
        db.JSON,
        nullable=True,
        comment="本次测试使用的测试用例列表，格式：[{prompt, should_trigger}]",
    )
    raw_output = db.Column(
        db.Text,
        nullable=True,
        comment="Docker 容器执行的原始 stdout/stderr 输出，用于调试",
    )
    executed_at = db.Column(
        db.DateTime,
        nullable=True,
        default=datetime.utcnow,
        comment="测试执行开始时间（UTC）",
    )
    duration_seconds = db.Column(
        db.Float,
        nullable=True,
        comment="测试执行总耗时（秒），包含 Docker 启动时间",
    )
    celery_task_id = db.Column(
        db.String(200),
        nullable=True,
        comment="关联的 Celery 任务 ID，用于查询实时执行状态",
    )

    # 关联关系
    task = db.relationship("SkillCreationTask", back_populates="sandbox_tests")

    def to_dict(self) -> dict:
        """
        将测试记录序列化为字典，用于 API 响应。

        Returns:
            包含测试结果信息的字典。
        """
        return {
            "id": self.id,
            "task_id": self.task_id,
            "status": self.status,
            "trigger_accuracy": self.trigger_accuracy,
            "total_cases": self.total_cases,
            "passed_cases": self.passed_cases,
            "test_results": self.test_results,
            "structure_valid": self.structure_valid,
            "structure_errors": self.structure_errors or [],
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "duration_seconds": self.duration_seconds,
        }

    def __repr__(self):
        return (
            f"<SandboxTest {self.id} task={self.task_id} "
            f"status={self.status} accuracy={self.trigger_accuracy}>"
        )
