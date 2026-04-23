"""
backend/app/tasks/sandbox_test_task.py

Celery 异步任务：沙盒测试。

职责：
    - 在 Celery Worker 中异步执行沙盒测试
    - 调用 SandboxService.run_test() 完成测试流程
    - 处理测试超时和执行异常

为什么使用异步任务：
    - 沙盒测试需要启动 Docker 容器，耗时通常在 10-120 秒
    - Docker 镜像拉取（首次）可能需要更长时间
    - HTTP 请求不应阻塞等待容器执行完成

超时策略：
    - soft_time_limit: 120 秒（触发 SoftTimeLimitExceeded，允许清理）
    - time_limit: 180 秒（强制终止任务进程）
    - 独立于 Docker 内部的 eval 脚本超时（由 SandboxRunner 控制）
"""

from ..extensions import celery_app


@celery_app.task(
    bind=True,
    name="app.tasks.sandbox_test_task.run_sandbox_test_task",
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def run_sandbox_test_task(self, task_id: str, test_id: str) -> dict:
    """
    异步执行沙盒测试的 Celery 任务。

    此任务由 /api/v1/tasks/{task_id}/tests POST 接口触发，
    在 Celery Worker 进程中的 Flask 应用上下文内执行。

    Args:
        task_id: SkillCreationTask ID
        test_id: SandboxTest ID（已在 HTTP 请求阶段预创建）

    Returns:
        包含测试结果摘要的字典：
        {"success": True, "test_id": "...", "status": "passed/failed/error"}
    """
    from celery.exceptions import SoftTimeLimitExceeded

    from ..models.sandbox_test import SandboxTest
    from ..extensions import db
    from ..services.sandbox_service import SandboxService

    try:
        service = SandboxService()
        test = service.run_test(task_id, test_id)
        return {
            "success": True,
            "test_id": test_id,
            "status": test.status,
            "trigger_accuracy": test.trigger_accuracy,
        }

    except SoftTimeLimitExceeded:
        # 任务软超时：更新测试状态为 timeout
        test = SandboxTest.query.get(test_id)
        if test:
            test.status = SandboxTest.STATUS_TIMEOUT
            db.session.commit()
        return {
            "success": False,
            "test_id": test_id,
            "status": "timeout",
        }

    except Exception as e:
        # 未预期错误
        return {
            "success": False,
            "test_id": test_id,
            "error": str(e),
        }
