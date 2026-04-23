"""
backend/app/api/v1/files.py

Skill 文件管理 API 蓝图。

接口列表：
    GET    /api/v1/tasks/<task_id>/files              获取 Skill 目录树
    GET    /api/v1/tasks/<task_id>/files/<path:file_path>  读取文件内容
    PUT    /api/v1/tasks/<task_id>/files/<path:file_path>  更新文件内容
    DELETE /api/v1/tasks/<task_id>/files/<path:file_path>  删除文件
    POST   /api/v1/tasks/<task_id>/files/rename            文件重命名

安全注意：
    - 所有文件路径都经过 FileService._safe_resolve() 安全校验
    - 路径越界访问返回 400（PathSecurityError）
    - 只允许操作对应 task_id 的工作区目录内的文件
"""

from flask import Blueprint, current_app, jsonify, request

from ...exceptions import (
    PathSecurityError,
    TaskNotFoundError,
    WorkspaceFileNotFoundError,
)
from ...services.file_service import FileService

files_bp = Blueprint("files", __name__)


@files_bp.route("/<task_id>/files", methods=["GET"])
def list_files(task_id: str):
    """
    获取指定任务工作区的文件目录树。

    Returns:
        FileNode 数组（树形结构），表示工作区中的所有文件和目录。
    """
    try:
        service = FileService()
        nodes = service.list_files(task_id)
        return jsonify([n.to_dict() for n in nodes])
    except TaskNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404


@files_bp.route("/<task_id>/files/<path:file_path>", methods=["GET"])
def read_file(task_id: str, file_path: str):
    """
    读取工作区中指定文件的内容。

    Args:
        task_id: SkillCreationTask ID
        file_path: 相对于工作区根目录的文件路径（URL 路径部分）

    Returns:
        JSON 对象，包含 path 和 content 字段。
    """
    try:
        service = FileService()
        content = service.read_file(task_id, file_path)
        return jsonify({"path": file_path, "content": content})
    except PathSecurityError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 400
    except WorkspaceFileNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404
    except TaskNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404


@files_bp.route("/<task_id>/files/<path:file_path>", methods=["PUT"])
def write_file(task_id: str, file_path: str):
    """
    创建或更新工作区中的文件内容。

    Request Body (JSON):
        content: str, 必填，文件内容（UTF-8 编码）

    Returns:
        操作成功消息。
    """
    data = request.get_json(force=True) or {}
    content = data.get("content")
    if content is None:
        return jsonify({"error": {"code": "MISSING_FIELD", "message": "缺少 content 字段"}}), 400

    try:
        service = FileService()
        service.write_file(task_id, file_path, content)
        return jsonify({"message": f"文件 '{file_path}' 已保存"})
    except PathSecurityError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 400
    except TaskNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404
    except Exception as e:
        current_app.logger.error(f"文件写入失败 {file_path}: {e}", exc_info=True)
        return jsonify({"error": {"code": "FILE_WRITE_ERROR", "message": "文件写入失败，请重试"}}), 500


@files_bp.route("/<task_id>/files/<path:file_path>", methods=["DELETE"])
def delete_file(task_id: str, file_path: str):
    """
    删除工作区中的文件或空目录。

    Returns:
        操作成功消息。
    """
    try:
        service = FileService()
        service.delete_file(task_id, file_path)
        return jsonify({"message": f"文件 '{file_path}' 已删除"})
    except PathSecurityError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 400
    except WorkspaceFileNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404
    except TaskNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404


@files_bp.route("/<task_id>/files/rename", methods=["POST"])
def rename_file(task_id: str):
    """
    重命名工作区中的文件或目录。

    Request Body (JSON):
        old_path: str, 必填，原始相对路径
        new_path: str, 必填，新的相对路径

    Returns:
        操作成功消息。
    """
    data = request.get_json(force=True) or {}
    old_path = data.get("old_path", "").strip()
    new_path = data.get("new_path", "").strip()

    if not old_path or not new_path:
        return jsonify({
            "error": {"code": "MISSING_FIELD", "message": "缺少 old_path 或 new_path 字段"}
        }), 400

    try:
        service = FileService()
        service.rename_file(task_id, old_path, new_path)
        return jsonify({
            "message": f"文件已从 '{old_path}' 重命名为 '{new_path}'"
        })
    except PathSecurityError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 400
    except WorkspaceFileNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404
    except TaskNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404
