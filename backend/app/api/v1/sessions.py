"""
backend/app/api/v1/sessions.py

多轮会话 API 蓝图。

接口列表：
    POST   /api/v1/sessions                          创建新会话（含初始需求描述）
    GET    /api/v1/sessions/<session_id>             获取会话详情
    POST   /api/v1/sessions/<session_id>/messages    发送消息（多轮对话）
    GET    /api/v1/sessions/<session_id>/requirement 获取当前结构化需求
    POST   /api/v1/sessions/<session_id>/confirm     确认需求并触发创建

注意：
    - 所有消息发送都是同步的（AI 调用在请求内完成），如需流式输出后续扩展
    - confirm 操作会触发 Celery 异步任务，立即返回 task_id
    - completeness_score 由 AI 在每轮对话后更新，前端据此决定是否显示"开始创建"按钮
"""

from flask import Blueprint, Response, jsonify, request, stream_with_context

from ...exceptions import RequirementIncompleteError, SessionNotFoundError
from ...services.session_service import SessionService

sessions_bp = Blueprint("sessions", __name__)


@sessions_bp.route("", methods=["POST"])
def create_session():
    """
    创建新会话并处理用户的初始需求描述。

    Request Body (JSON):
        message: str, 必填，用户的初始需求描述（中文）

    Returns:
        新创建的会话信息，包含 AI 的第一条回复。
    """
    data = request.get_json(force=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": {"code": "MISSING_FIELD", "message": "缺少 message 字段"}}), 400

    service = SessionService()
    session = service.create_session(message)

    return jsonify(session.to_dict()), 201


@sessions_bp.route("/<session_id>", methods=["GET"])
def get_session(session_id: str):
    """
    获取会话详情，包含完整消息历史和当前结构化需求。

    Args:
        session_id: 会话 UUID
    """
    try:
        service = SessionService()
        session = service.get_session(session_id)
        return jsonify(session.to_dict())
    except SessionNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404


@sessions_bp.route("/<session_id>/messages", methods=["POST"])
def send_message(session_id: str):
    """
    在已有会话中发送一条用户消息，获取 AI 回复。

    Request Body (JSON):
        message: str, 必填，用户消息（中文）

    Returns:
        包含 AI 回复、更新后需求和完整度评分的 JSON。
    """
    data = request.get_json(force=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": {"code": "MISSING_FIELD", "message": "缺少 message 字段"}}), 400

    try:
        service = SessionService()
        ai_reply, session = service.send_message(session_id, message)
        return jsonify({
            "ai_reply": ai_reply,
            "session": session.to_dict(),
        })
    except SessionNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404


@sessions_bp.route("/<session_id>/requirement", methods=["GET"])
def get_requirement(session_id: str):
    """
    获取会话当前的结构化需求（RequirementSpec）。

    Returns:
        RequirementSpec 字典和完整度评分。
    """
    try:
        service = SessionService()
        session = service.get_session(session_id)
        return jsonify({
            "session_id": session_id,
            "requirement_spec": session.requirement_spec,
            "completeness_score": session.completeness_score,
            "can_create": session.completeness_score >= 80,
        })
    except SessionNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404


@sessions_bp.route("/<session_id>/attachments", methods=["POST"])
def upload_attachment(session_id: str):
    """
    上传文件作为会话参考附件。

    上传的文件将被保存到会话附件目录，文本类文件（.txt/.md/.py/.js/.json/.yaml）
    会提取前 2000 字符作为摘要，在后续 AI 对话中作为上下文注入。

    Request:
        multipart/form-data，字段名为 file

    限制：
        - 文件大小 ≤ 10MB
        - 类型白名单：.txt/.md/.py/.js/.json/.yaml/.yml/.csv/.pdf

    Returns:
        附件元数据 JSON（filename, path, size, summary, uploaded_at）
    """
    ALLOWED_EXTENSIONS = {".txt", ".md", ".py", ".js", ".json", ".yaml", ".yml", ".csv", ".pdf"}
    MAX_SIZE = 10 * 1024 * 1024  # 10MB

    if "file" not in request.files:
        return jsonify({"error": {"code": "MISSING_FILE", "message": "缺少 file 字段"}}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": {"code": "MISSING_FILE", "message": "文件名为空"}}), 400

    from pathlib import Path as _Path
    ext = _Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({
            "error": {
                "code": "UNSUPPORTED_FILE_TYPE",
                "message": f"不支持的文件类型 '{ext}'，支持：{', '.join(sorted(ALLOWED_EXTENSIONS))}",
            }
        }), 400

    file_content = file.read()
    if len(file_content) > MAX_SIZE:
        return jsonify({
            "error": {"code": "FILE_TOO_LARGE", "message": "文件大小超过 10MB 限制"}
        }), 400

    try:
        service = SessionService()
        meta = service.add_attachment(session_id, file.filename, file_content)
        return jsonify(meta), 201
    except SessionNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404


@sessions_bp.route("/<session_id>/stream", methods=["POST"])
def stream_message(session_id: str):
    """
    在已有会话中以 SSE 流式方式发送用户消息，实时接收 AI 回复。

    Request Body (JSON):
        message: str, 必填，用户消息（中文）

    Returns:
        text/event-stream 响应，每个 SSE 事件的格式为：
        - 普通文本块：data: {"type":"text","content":"...分片..."}\n\n
        - 流结束（含更新后的 session）：data: {"type":"done","session":{...}}\n\n
        - 错误：data: {"type":"error","message":"..."}\n\n
    """
    import json

    data = request.get_json(force=True) or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": {"code": "MISSING_FIELD", "message": "缺少 message 字段"}}), 400

    service = SessionService()

    def generate():
        for chunk in service.stream_message(session_id, message):
            # 判断是否为 done/error 控制包（JSON 字符串），否则包装为 text 事件
            stripped = chunk.strip()
            if stripped.startswith("{") and ('"type":"done"' in stripped or '"type":"error"' in stripped):
                yield f"data: {chunk}\n\n"
            else:
                payload = json.dumps({"type": "text", "content": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁止 Nginx 缓冲，确保实时推送
        },
    )


@sessions_bp.route("/<session_id>/confirm", methods=["POST"])
def confirm_session(session_id: str):
    """
    确认需求并触发 Skill 创建任务。

    需求完整度必须达到 80 分以上才能触发。
    操作成功后立即返回 task_id，客户端通过 /api/v1/tasks/{task_id} 轮询进度。

    Returns:
        新创建的 SkillCreationTask 信息（含 task_id 和初始状态）。
    """
    try:
        service = SessionService()
        task = service.confirm_and_start_creation(session_id)
        return jsonify({
            "message": "Skill 创建任务已启动",
            "task": task.to_dict(),
        }), 202

    except SessionNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404

    except RequirementIncompleteError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 400
