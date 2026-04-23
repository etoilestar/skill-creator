"""
backend/app/api/v1/tests.py

沙盒测试 API 蓝图。

接口列表：
    POST   /api/v1/tasks/<task_id>/tests            触发新一轮沙盒测试
    GET    /api/v1/tasks/<task_id>/tests             获取测试历史列表
    GET    /api/v1/tasks/<task_id>/tests/<test_id>  获取测试结果详情
    GET    /api/v1/tasks/<task_id>/tests/<test_id>/logs  获取沙盒执行原始日志

注意：
    - POST 触发测试是异步的，立即返回 test_id（状态为 running）
    - 客户端通过 GET /{test_id} 轮询测试状态
    - 只有 CREATED / FAILED / ITERATING 状态的任务才能触发测试
"""

from flask import Blueprint, jsonify

from ...exceptions import InvalidTaskStateError, TaskNotFoundError
from ...models.sandbox_test import SandboxTest
from ...models.skill_creation_task import SkillCreationTask
from ...services.sandbox_service import SandboxService
from ...tasks.sandbox_test_task import run_sandbox_test_task

tests_bp = Blueprint("tests", __name__)


@tests_bp.route("/<task_id>/tests", methods=["POST"])
def trigger_test(task_id: str):
    """
    触发指定任务的沙盒测试。

    操作流程：
    1. 校验任务状态是否允许测试
    2. 创建 SandboxTest 记录（状态 running）
    3. 提交 Celery 异步任务
    4. 立即返回 test_id

    Returns:
        新创建的 SandboxTest 信息（状态为 running）。
    """
    try:
        service = SandboxService()
        test = service.create_test_record(task_id)

        # 提交 Celery 异步任务执行沙盒测试
        celery_result = run_sandbox_test_task.delay(task_id, test.id)
        test.celery_task_id = celery_result.id

        from ...extensions import db
        db.session.commit()

        return jsonify({
            "message": "沙盒测试已启动",
            "test": test.to_dict(),
        }), 202

    except TaskNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404
    except InvalidTaskStateError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 409


@tests_bp.route("/<task_id>/tests", methods=["GET"])
def list_tests(task_id: str):
    """
    获取指定任务的历史测试记录列表（按时间倒序）。

    Returns:
        SandboxTest 列表。
    """
    task = SkillCreationTask.query.get(task_id)
    if task is None:
        return jsonify({"error": {"code": "TASK_NOT_FOUND", "message": "任务不存在"}}), 404

    tests = (
        SandboxTest.query
        .filter_by(task_id=task_id)
        .order_by(SandboxTest.executed_at.desc())
        .all()
    )
    return jsonify([t.to_dict() for t in tests])


@tests_bp.route("/<task_id>/tests/<test_id>", methods=["GET"])
def get_test(task_id: str, test_id: str):
    """
    获取指定测试记录的详细结果。

    Returns:
        SandboxTest 详情，包含触发精度、通过率、失败用例等信息。
    """
    test = SandboxTest.query.filter_by(id=test_id, task_id=task_id).first()
    if test is None:
        return jsonify({"error": {"code": "TEST_NOT_FOUND", "message": "测试记录不存在"}}), 404
    return jsonify(test.to_dict())


@tests_bp.route("/<task_id>/tests/<test_id>/logs", methods=["GET"])
def get_test_logs(task_id: str, test_id: str):
    """
    获取沙盒测试的原始执行日志。

    返回 Docker 容器的原始 stdout/stderr 输出，用于调试测试失败原因。

    Returns:
        包含原始日志字符串的 JSON 对象。
    """
    test = SandboxTest.query.filter_by(id=test_id, task_id=task_id).first()
    if test is None:
        return jsonify({"error": {"code": "TEST_NOT_FOUND", "message": "测试记录不存在"}}), 404

    return jsonify({
        "test_id": test_id,
        "status": test.status,
        "raw_output": test.raw_output or "",
        "executed_at": test.executed_at.isoformat() if test.executed_at else None,
        "duration_seconds": test.duration_seconds,
    })
