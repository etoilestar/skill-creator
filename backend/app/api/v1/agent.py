"""
backend/app/api/v1/agent.py

Skill Agent 执行 API 蓝图。

接口列表：
    POST /api/v1/agent/chat        同步执行（等待完整回复，适合短任务）
    POST /api/v1/agent/stream      SSE 流式执行（实时返回 AI 输出，适合长任务）

设计说明：
    Agent 通过 SkillAgentService 自动选择最匹配的 Skill 并执行工作流。
    两个端点均接受相同的请求体：
        {
          "query": "用户输入文本",
          "session_id": "可选的会话ID，用于多轮记忆"
        }

    SSE 流式端点 /stream 每个事件的 data 字段格式：
        {"type": "text",   "content": "AI 输出的文本片段"}
        {"type": "status", "message": "状态提示（如已选择 Skill）"}
        {"type": "done",   "skill_name": "...", "skill_path": "..."}
        {"type": "error",  "message": "错误信息"}
"""

from flask import Blueprint, Response, jsonify, request, stream_with_context

from ...services.skill_agent_service import SkillAgentService

agent_bp = Blueprint("agent", __name__)


@agent_bp.route("/chat", methods=["POST"])
def agent_chat():
    """
    同步执行 Skill Agent，等待完整回复后返回。

    适合查询较短、执行快速的场景。
    对于需要实时显示进度的场景，请使用 /stream 端点。

    Request Body (JSON):
        query:      str, 必填，用户输入文本
        session_id: str, 可选，关联的会话 ID（用于持久化对话历史）

    Returns:
        {
          "skill_name": "所选 Skill 名称",
          "skill_path": "Skill 目录路径",
          "reply":      "AI 完整回复文本",
          "match_score": 0.42
        }
    """
    data = request.get_json(force=True) or {}
    query = data.get("query", "").strip()
    session_id = data.get("session_id")

    if not query:
        return jsonify({"error": {"code": "MISSING_FIELD", "message": "缺少 query 字段"}}), 400

    service = SkillAgentService()

    text_parts = []
    skill_name = None
    skill_path = None
    error_message = None

    import json

    for event_str in service.run(user_query=query, session_id=session_id):
        try:
            event = json.loads(event_str)
        except Exception:
            text_parts.append(event_str)
            continue

        etype = event.get("type")
        if etype == "text":
            text_parts.append(event.get("content", ""))
        elif etype == "done":
            skill_name = event.get("skill_name")
            skill_path = event.get("skill_path")
        elif etype == "error":
            error_message = event.get("message")
            break

    if error_message:
        return jsonify({"error": {"code": "AGENT_ERROR", "message": error_message}}), 500

    return jsonify({
        "skill_name": skill_name,
        "skill_path": skill_path,
        "reply": "".join(text_parts),
    })


@agent_bp.route("/stream", methods=["POST"])
def agent_stream():
    """
    以 SSE 流式方式执行 Skill Agent，实时推送 AI 输出。

    Request Body (JSON):
        query:      str, 必填，用户输入文本
        session_id: str, 可选，关联的会话 ID

    Returns:
        text/event-stream 响应，每条 SSE 事件的 data 字段格式见模块文档。
    """
    data = request.get_json(force=True) or {}
    query = data.get("query", "").strip()
    session_id = data.get("session_id")

    if not query:
        return jsonify({"error": {"code": "MISSING_FIELD", "message": "缺少 query 字段"}}), 400

    service = SkillAgentService()

    def generate():
        for event_str in service.run(user_query=query, session_id=session_id):
            yield f"data: {event_str}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
