"""
backend/app/api/v1/skills.py

Skill 检索 API 蓝图。

接口列表：
    GET  /api/v1/skills/search          全局 Skill 搜索（在所有已创建任务的工作区中检索）
    GET  /api/v1/skills/search/<task_id> 在指定任务的工作区中检索，返回竞争排名
    GET  /api/v1/skills                  列出所有已索引的 Skill

设计说明：
    每次搜索请求都会临时构建一个 SkillIndexService 实例并扫描工作区，
    不维护持久化索引（避免工作区文件变化后索引失效）。
    对于大量 Skill 的场景，可改为定期重建索引的缓存方案。
"""

from flask import Blueprint, jsonify, current_app, request

from ...services.skill_index_service import SkillIndexService

skills_bp = Blueprint("skills", __name__)


@skills_bp.route("", methods=["GET"])
def list_skills():
    """
    列出系统中所有已创建的 Skill（扫描所有任务工作区）。

    Query Params:
        limit: 最多返回条数（默认 50，最大 200）

    Returns:
        已索引的 Skill 列表（按名称字母序）。
    """
    limit = min(int(request.args.get("limit", 50)), 200)

    index = _build_global_index()
    all_skills = index.list_all()

    return jsonify({
        "skills": all_skills[:limit],
        "total": len(all_skills),
    })


@skills_bp.route("/search", methods=["GET"])
def search_skills():
    """
    在所有工作区中搜索与查询文本最匹配的 Skill。

    Query Params:
        q (required): 查询文本（中英文均支持）
        top_k: 返回结果数量上限（默认 5，最大 20）

    Returns:
        按得分降序排列的 Skill 匹配列表，每项包含 name、description、skill_path、score。
    """
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": {"code": "MISSING_QUERY", "message": "请提供查询文本 q 参数"}}), 400

    top_k = min(int(request.args.get("top_k", 5)), 20)

    index = _build_global_index()
    results = index.search(query, top_k=top_k)

    return jsonify({
        "query": query,
        "results": results,
        "total_indexed": index.size,
    })


@skills_bp.route("/search/<task_id>", methods=["GET"])
def search_skills_in_task(task_id: str):
    """
    在指定任务工作区中搜索 Skill，并在全局 Skill 池中给出竞争排名。

    用于沙盒测试前的手动验证：输入用户查询，查看当前 Skill 是否排在第一位，
    从而评估 description 的区分度。

    Query Params:
        q (required): 查询文本
        top_k: 返回结果数量上限（默认 5，最大 20）

    Returns:
        全局检索结果，其中会标注当前 task 对应的 Skill（is_current: true）。
    """
    from ...models.skill_creation_task import SkillCreationTask

    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": {"code": "MISSING_QUERY", "message": "请提供查询文本 q 参数"}}), 400

    top_k = min(int(request.args.get("top_k", 5)), 20)

    # 获取任务工作区路径
    task = SkillCreationTask.query.get(task_id)
    if task is None:
        return jsonify({"error": {"code": "TASK_NOT_FOUND", "message": "任务不存在"}}), 404

    current_skill_path = task.workspace_path

    # 构建全局索引
    index = _build_global_index()
    results = index.search(query, top_k=top_k)

    # 标注当前 task 对应的 Skill
    if current_skill_path:
        import os
        current_abs = os.path.realpath(current_skill_path)
        for item in results:
            item_abs = os.path.realpath(os.path.dirname(item["skill_path"]))
            item["is_current"] = (item_abs == current_abs or
                                  item["skill_path"].startswith(current_skill_path))
    else:
        for item in results:
            item["is_current"] = False

    return jsonify({
        "query": query,
        "task_id": task_id,
        "results": results,
        "total_indexed": index.size,
    })


def _build_global_index() -> SkillIndexService:
    """
    扫描所有工作区，构建全局 Skill 索引。

    同时索引：
    1. kernels/skill-creator/SKILL.md（内核技能本身）
    2. workspace/ 下所有任务的工作区

    Returns:
        填充完成的 SkillIndexService 实例。
    """
    index = SkillIndexService()

    # 索引内核目录中的 Skill
    kernel_base = current_app.config.get("KERNEL_BASE_PATH")
    if kernel_base:
        import os
        kernel_skill_dir = os.path.join(kernel_base, "skill-creator")
        index.index_directory(kernel_skill_dir, recursive=False)

    # 索引所有任务工作区
    workspace_base = current_app.config.get("WORKSPACE_BASE_PATH", "/app/workspace")
    index.index_directory(workspace_base, recursive=True)

    return index
