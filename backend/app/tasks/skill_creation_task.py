"""
backend/app/tasks/skill_creation_task.py

Celery 异步任务：Skill 创建。

职责：
    - 在 Celery Worker 中异步执行 Skill 创建流程
    - 调用 SkillCreationService.create_skill() 完成实际创建
    - 处理任务重试逻辑（网络/模型调用失败时自动重试）
    - 确保任务失败时正确更新数据库状态

为什么使用异步任务：
    - Skill 创建涉及多次 AI 模型调用，每次可能耗时 10-60 秒
    - 整个流程（AI 调用 + 校验 + 文件写入）可能耗时 1-5 分钟
    - HTTP 请求不应等待这么长时间（连接超时、用户体验差）
    - 使用 Celery 将任务异步化，HTTP 请求立即返回任务 ID，
      客户端通过轮询 /api/v1/tasks/{task_id} 获取进度

重试策略：
    - 最多重试 3 次（通过 max_retries 参数）
    - 指数退避：第 1 次重试等 10 秒，第 2 次等 20 秒，第 3 次等 40 秒
    - 只对可重试错误（网络超时、模型 503）重试，业务逻辑错误不重试
"""

import traceback

from ..extensions import celery_app
from ..models.skill_creation_task import SkillCreationTask


@celery_app.task(
    bind=True,
    name="app.tasks.skill_creation_task.create_skill_task",
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,  # 任务执行完成后才 ack，防止任务丢失
)
def create_skill_task(self, task_id: str, requirement_spec: dict) -> dict:
    """
    异步执行 Skill 创建的 Celery 任务。

    此任务由 SessionService.confirm_and_start_creation() 触发，
    在 Celery Worker 进程中的 Flask 应用上下文内执行。

    执行流程：
    1. 调用 SkillCreationService.create_skill(task_id) 执行创建
    2. 成功时返回创建结果摘要
    3. 失败时记录错误、更新任务状态，并根据错误类型决定是否重试

    Args:
        task_id: SkillCreationTask ID（字符串格式 UUID）
        requirement_spec: 结构化需求字典（用于日志记录，实际读取来自数据库）

    Returns:
        包含创建结果的字典：
        {"success": True, "task_id": "...", "workspace_path": "..."}
    """
    from ..services.skill_creation_service import SkillCreationService
    from ..exceptions import ModelCallError

    try:
        service = SkillCreationService()
        workspace_path = service.create_skill(task_id)
        return {
            "success": True,
            "task_id": task_id,
            "workspace_path": workspace_path,
        }

    except ModelCallError as e:
        # 模型调用失败（网络问题、服务暂时不可用），触发重试
        raise self.retry(exc=e, countdown=10 * (2 ** self.request.retries))

    except Exception as e:
        # 其他错误（业务逻辑错误）：不重试，记录失败状态
        # 注意：SkillCreationService.create_skill() 已经更新了任务状态，
        # 此处只需返回错误信息
        return {
            "success": False,
            "task_id": task_id,
            "error": str(e),
        }
