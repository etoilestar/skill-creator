"""
backend/app/api/v1/tasks.py

Skill 创建任务管理 API 蓝图。

接口列表：
    GET    /api/v1/tasks                   列出所有任务
    POST   /api/v1/tasks                   创建草稿任务（直接新建，无需经过会话确认）
    GET    /api/v1/tasks/<task_id>         获取任务详情和当前状态
    DELETE /api/v1/tasks/<task_id>         删除任务（同时清理工作区文件）
    GET    /api/v1/tasks/<task_id>/logs    获取任务执行日志
    POST   /api/v1/tasks/<task_id>/retry   重试失败的任务
"""

import shutil
from pathlib import Path

from flask import Blueprint, jsonify, request

from ...exceptions import InvalidTaskStateError, TaskNotFoundError
from ...extensions import db
from ...models.skill_creation_task import SkillCreationTask
from ...models.task_event_log import TaskEventLog

tasks_bp = Blueprint("tasks", __name__)


@tasks_bp.route("", methods=["GET"])
def list_tasks():
    """
    列出所有 Skill 创建任务。

    Query Params:
        status: 按状态筛选（可选）
        page: 页码（默认 1）
        per_page: 每页数量（默认 20，最大 100）

    Returns:
        分页的任务列表。
    """
    status_filter = request.args.get("status")
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = min(max(1, int(request.args.get("per_page", 20))), 100)
    except (ValueError, TypeError):
        per_page = 20

    query = SkillCreationTask.query.order_by(SkillCreationTask.created_at.desc())
    if status_filter:
        query = query.filter_by(status=status_filter)

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "tasks": [t.to_dict() for t in paginated.items],
        "total": paginated.total,
        "page": page,
        "per_page": per_page,
        "pages": paginated.pages,
    })

@tasks_bp.route("", methods=["POST"])
def create_task():
    """
    直接创建一个草稿（draft）状态的 Skill 任务。

    不需要经过多轮会话确认；用于「新建对话时立即在侧栏显示任务」的场景。

    Request Body (JSON, 均可选):
        skill_name: str  任务显示名称（默认 "新建 Skill"）

    Returns:
        新创建的草稿任务信息（status = draft）。
    """
    data = request.get_json(silent=True) or {}
    skill_name = (data.get("skill_name") or "新建 Skill").strip()

    task = SkillCreationTask(
        status=SkillCreationTask.STATUS_DRAFT,
        skill_name=skill_name,
    )
    db.session.add(task)
    db.session.commit()

    return jsonify(task.to_dict()), 201


@tasks_bp.route("/<task_id>", methods=["DELETE"])
def delete_task(task_id: str):
    """
    删除指定任务及其关联的事件日志，并清理工作区文件目录。

    Args:
        task_id: 要删除的任务 UUID

    Returns:
        204 No Content（成功）或 404（任务不存在）。
    """
    task = SkillCreationTask.query.get(task_id)
    if task is None:
        return jsonify({"error": {"code": "TASK_NOT_FOUND", "message": "任务不存在"}}), 404

    # 清理工作区目录（如果存在）
    if task.workspace_path:
        workspace = Path(task.workspace_path)
        if workspace.exists() and workspace.is_dir():
            shutil.rmtree(workspace, ignore_errors=True)

    # 解除会话关联（避免外键约束残留）
    if task.session:
        task.session.task_id = None

    # 级联删除事件日志（SQLAlchemy 关系已配置 back_populates，手动删除更安全）
    TaskEventLog.query.filter_by(task_id=task_id).delete()

    db.session.delete(task)
    db.session.commit()

    return "", 204


@tasks_bp.route("/<task_id>", methods=["GET"])
def get_task(task_id: str):
    """
    获取指定任务的详细信息和当前状态。

    Returns:
        任务详情 JSON，包含状态、需求快照、工作区路径等。
    """
    task = SkillCreationTask.query.get(task_id)
    if task is None:
        return jsonify({"error": {"code": "TASK_NOT_FOUND", "message": "任务不存在"}}), 404
    return jsonify(task.to_dict())


@tasks_bp.route("/<task_id>/logs", methods=["GET"])
def get_task_logs(task_id: str):
    """
    获取任务的完整事件日志列表。

    支持按事件类型筛选，便于调试特定环节的问题。

    Query Params:
        event_type: 按事件类型筛选（可选）
        limit: 返回数量上限（默认 100）

    Returns:
        事件日志列表（按时间倒序）。
    """
    task = SkillCreationTask.query.get(task_id)
    if task is None:
        return jsonify({"error": {"code": "TASK_NOT_FOUND", "message": "任务不存在"}}), 404

    event_type_filter = request.args.get("event_type")
    try:
        limit = min(max(1, int(request.args.get("limit", 100))), 500)
    except (ValueError, TypeError):
        limit = 100

    query = (
        TaskEventLog.query
        .filter_by(task_id=task_id)
    )
    if event_type_filter:
        query = query.filter_by(event_type=event_type_filter)
    query = query.order_by(TaskEventLog.created_at.desc()).limit(limit)

    logs = query.all()
    return jsonify([log.to_dict() for log in logs])


@tasks_bp.route("/<task_id>/retry", methods=["POST"])
def retry_task(task_id: str):
    """
    重试失败的任务（仅限 CREATION_FAILED 状态的任务）。

    操作流程：
    1. 检查任务状态是否允许重试
    2. 重置任务状态为 PENDING
    3. 重新提交 Celery 任务

    Returns:
        更新后的任务状态。
    """
    task = SkillCreationTask.query.get(task_id)
    if task is None:
        return jsonify({"error": {"code": "TASK_NOT_FOUND", "message": "任务不存在"}}), 404

    if task.status not in SkillCreationTask.RETRYABLE_STATUSES:
        return jsonify({
            "error": {
                "code": "INVALID_TASK_STATE",
                "message": f"任务状态 '{task.status}' 不允许重试，只有失败状态才能重试",
            }
        }), 409

    from ...tasks.skill_creation_task import create_skill_task

    task.transition_to(SkillCreationTask.STATUS_PENDING)
    task.error_message = None
    task.error_detail = None
    db.session.commit()

    celery_result = create_skill_task.delay(task_id, task.requirement_spec or {})
    task.celery_task_id = celery_result.id
    db.session.commit()

    return jsonify({
        "message": "任务已重新提交",
        "task": task.to_dict(),
    })
