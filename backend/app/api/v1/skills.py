"""
backend/app/api/v1/skills.py

Skill 检索 API 蓝图。

接口列表：
    GET    /api/v1/skills                    列出所有已索引的 Skill
    GET    /api/v1/skills/search             全局 Skill 搜索（在所有已创建任务的工作区中检索）
    GET    /api/v1/skills/search/<task_id>   在指定任务的工作区中检索，返回竞争排名
    GET    /api/v1/skills/<task_id>          获取指定任务的 Skill 详情（含 SKILL.md 内容）
    DELETE /api/v1/skills/<task_id>          删除指定任务的 Skill 工作区文件
    POST   /api/v1/skills/import             导入 ZIP 格式的 Skill 包

设计说明：
    每次搜索请求都会临时构建一个 SkillIndexService 实例并扫描工作区，
    不维护持久化索引（避免工作区文件变化后索引失效）。
    对于大量 Skill 的场景，可改为定期重建索引的缓存方案。
"""

import os
import shutil
import uuid
import zipfile
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

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


@skills_bp.route("/import", methods=["POST"])
def import_skill():
    """
    导入 ZIP 格式的 Skill 包，创建一个 CREATED 状态的 SkillCreationTask。

    接收一个 .zip 文件，要求 ZIP 中必须包含 SKILL.md。
    解压到工作区后调用内核校验 Skill 结构合规性。

    Request:
        multipart/form-data，字段名 file，文件类型 .zip

    安全限制：
        - 解压文件总大小 ≤ 50MB
        - 过滤路径穿越（../）
        - 解压文件扩展名白名单：.md/.py/.js/.json/.yaml/.yml/.txt

    Returns:
        新创建的 SkillCreationTask 的 task_id 和状态。
    """
    from ...kernel.registry import KernelRegistry
    from ...models.skill_creation_task import SkillCreationTask
    from ...extensions import db

    ALLOWED_EXTENSIONS = {".md", ".py", ".js", ".json", ".yaml", ".yml", ".txt"}
    MAX_UNZIP_SIZE = 50 * 1024 * 1024  # 50MB

    if "file" not in request.files:
        return jsonify({"error": {"code": "MISSING_FILE", "message": "缺少 file 字段"}}), 400

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".zip"):
        return jsonify({"error": {"code": "INVALID_FILE_TYPE", "message": "只支持 .zip 格式的 Skill 包"}}), 400

    workspace_base = current_app.config.get("WORKSPACE_BASE_PATH", "/app/workspace")
    import_id = str(uuid.uuid4())
    import_dir = Path(workspace_base) / "imported" / import_id
    import_dir.mkdir(parents=True, exist_ok=True)

    try:
        import io
        zip_bytes = file.read()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            # 安全检查：过滤路径穿越和非白名单文件
            total_size = 0
            for info in zf.infolist():
                # 过滤目录项
                if info.filename.endswith("/"):
                    continue
                # 路径穿越检查
                norm = os.path.normpath(info.filename)
                if norm.startswith("..") or os.path.isabs(norm):
                    return jsonify({
                        "error": {"code": "PATH_SECURITY_VIOLATION", "message": f"ZIP 包含非法路径: {info.filename}"}
                    }), 400
                # 扩展名白名单
                ext = Path(info.filename).suffix.lower()
                if ext not in ALLOWED_EXTENSIONS:
                    continue  # 跳过不支持的文件类型
                # 文件大小检查
                total_size += info.file_size
                if total_size > MAX_UNZIP_SIZE:
                    return jsonify({
                        "error": {"code": "FILE_TOO_LARGE", "message": "解压后总大小超过 50MB 限制"}
                    }), 400

            # 安全解压（只解压白名单文件）
            for info in zf.infolist():
                if info.filename.endswith("/"):
                    continue
                ext = Path(info.filename).suffix.lower()
                if ext not in ALLOWED_EXTENSIONS:
                    continue
                norm = os.path.normpath(info.filename)
                if norm.startswith("..") or os.path.isabs(norm):
                    continue
                dest = import_dir / norm
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(info.filename))

        # 查找 SKILL.md（允许在子目录中）
        skill_md_files = list(import_dir.rglob("SKILL.md")) + list(import_dir.rglob("skill.md"))
        if not skill_md_files:
            shutil.rmtree(import_dir, ignore_errors=True)
            return jsonify({"error": {"code": "MISSING_SKILL_MD", "message": "ZIP 包中未找到 SKILL.md"}}), 400

        skill_dir = skill_md_files[0].parent

        # 使用内核校验 Skill 结构
        try:
            registry = KernelRegistry.get_instance()
            kernel = registry.get_kernel("skill-creator")
            validation = kernel.validate_skill_structure(str(skill_dir))
            if not validation.valid:
                shutil.rmtree(import_dir, ignore_errors=True)
                return jsonify({
                    "error": {
                        "code": "SKILL_VALIDATION_ERROR",
                        "message": "Skill 结构校验失败",
                        "details": validation.errors,
                    }
                }), 422
            # 从 frontmatter 提取 skill_name
            skill_name = _parse_skill_name(skill_md_files[0])
        except Exception:
            skill_name = skill_dir.name

        # 创建 SkillCreationTask（status=CREATED，手动填充 workspace_path）
        task = SkillCreationTask(
            id=import_id,
            skill_name=skill_name or import_id[:8],
            status=SkillCreationTask.STATUS_CREATED,
            workspace_path=str(skill_dir),
            kernel_id="skill-creator",
        )
        db.session.add(task)
        db.session.commit()

        return jsonify({
            "message": "Skill 导入成功",
            "task": task.to_dict(),
        }), 201

    except zipfile.BadZipFile:
        shutil.rmtree(import_dir, ignore_errors=True)
        return jsonify({"error": {"code": "INVALID_ZIP", "message": "无效的 ZIP 文件"}}), 400
    except Exception as e:
        shutil.rmtree(import_dir, ignore_errors=True)
        current_app.logger.error(f"Skill 导入失败: {e}", exc_info=True)
        return jsonify({"error": {"code": "IMPORT_ERROR", "message": f"导入失败: {str(e)}"}}), 500


@skills_bp.route("/<task_id>", methods=["GET"])
def get_skill_detail(task_id: str):
    """
    获取指定任务的 Skill 详情，返回 SKILL.md 全文内容和 frontmatter 解析结果。

    Args:
        task_id: SkillCreationTask UUID

    Returns:
        {task_id, skill_name, skill_md_content, frontmatter: {name, description}, workspace_path}
    """
    from ...models.skill_creation_task import SkillCreationTask

    task = SkillCreationTask.query.get(task_id)
    if task is None:
        return jsonify({"error": {"code": "TASK_NOT_FOUND", "message": "任务不存在"}}), 404

    if not task.workspace_path:
        return jsonify({"error": {"code": "WORKSPACE_NOT_FOUND", "message": "该任务尚未生成工作区"}}), 404

    skill_dir = Path(task.workspace_path)
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.is_file():
        # 兼容大小写
        for candidate in skill_dir.glob("*.md"):
            if candidate.name.upper() == "SKILL.MD":
                skill_md_path = candidate
                break
        else:
            return jsonify({"error": {"code": "SKILL_MD_NOT_FOUND", "message": "SKILL.md 不存在"}}), 404

    content = skill_md_path.read_text(encoding="utf-8")
    frontmatter = _parse_skill_frontmatter(content)

    return jsonify({
        "task_id": task_id,
        "skill_name": task.skill_name,
        "skill_md_content": content,
        "frontmatter": frontmatter,
        "workspace_path": task.workspace_path,
    })


@skills_bp.route("/<task_id>", methods=["DELETE"])
def delete_skill(task_id: str):
    """
    删除指定任务的 Skill 工作区文件，并将任务状态重置为 CREATION_FAILED。

    此操作不可撤销。任务记录本身保留（便于审计），只删除文件。

    Args:
        task_id: SkillCreationTask UUID

    Returns:
        操作结果信息。
    """
    from ...extensions import db
    from ...models.skill_creation_task import SkillCreationTask

    task = SkillCreationTask.query.get(task_id)
    if task is None:
        return jsonify({"error": {"code": "TASK_NOT_FOUND", "message": "任务不存在"}}), 404

    workspace_path = task.workspace_path
    if workspace_path and Path(workspace_path).exists():
        try:
            shutil.rmtree(workspace_path)
        except Exception as e:
            current_app.logger.warning(f"工作区删除失败 {workspace_path}: {e}")

    task.workspace_path = None
    task.status = SkillCreationTask.STATUS_CREATION_FAILED
    task.error_message = "工作区文件已被手动删除"
    db.session.commit()

    return jsonify({"message": "Skill 工作区文件已删除", "task_id": task_id})


def _parse_skill_name(skill_md_path: Path) -> str:
    """从 SKILL.md 的 frontmatter 提取 name 字段。"""
    try:
        content = skill_md_path.read_text(encoding="utf-8")
        fm = _parse_skill_frontmatter(content)
        return fm.get("name", "")
    except Exception:
        return ""


def _parse_skill_frontmatter(content: str) -> dict:
    """解析 SKILL.md frontmatter，提取 name 和 description。"""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {"name": "", "description": ""}
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {"name": "", "description": ""}
    name, description = "", ""
    for line in lines[1:end]:
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip()
        elif line.startswith("description:"):
            description = line.split(":", 1)[1].strip()
    return {"name": name, "description": description}


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
