"""
backend/app/api/v1/kernels.py

内核管理 API 蓝图。

接口列表：
    GET    /api/v1/kernels                   列出所有已注册内核
    GET    /api/v1/kernels/<kernel_id>       获取内核详情
    GET    /api/v1/kernels/<kernel_id>/guide 获取内核创建指南（SKILL.md 内容）
    POST   /api/v1/kernels/<kernel_id>/reload 重新加载内核（不升级版本）

注意：
    - 内核目录在 Docker 中以只读方式挂载，upgrade 接口为预留接口（第二阶段实现）
    - guide 接口返回 SKILL.md 的完整内容，供前端展示参考
"""

from flask import Blueprint, current_app, jsonify

from ...exceptions import KernelNotFoundError
from ...kernel.registry import KernelRegistry

kernels_bp = Blueprint("kernels", __name__)


@kernels_bp.route("", methods=["GET"])
def list_kernels():
    """
    列出所有已注册内核及其元数据。

    Returns:
        JSON 数组，包含所有已注册内核的元数据。
    """
    registry = KernelRegistry.get_instance()
    kernels = registry.list_kernels()
    return jsonify([
        {
            "kernel_id": k.kernel_id,
            "version": k.version,
            "source_url": k.source_url,
            "description": k.description,
            "capabilities": k.capabilities,
            "status": k.status,
        }
        for k in kernels
    ])


@kernels_bp.route("/<kernel_id>", methods=["GET"])
def get_kernel(kernel_id: str):
    """
    获取指定内核的详细信息。

    Args:
        kernel_id: 内核唯一标识符

    Returns:
        内核详细信息 JSON。
    """
    try:
        registry = KernelRegistry.get_instance()
        kernel = registry.get_kernel(kernel_id)
        meta = kernel.get_kernel_meta()
        return jsonify({
            "kernel_id": meta.kernel_id,
            "version": meta.version,
            "source_url": meta.source_url,
            "description": meta.description,
            "capabilities": meta.capabilities,
            "status": meta.status,
            "is_loaded": True,
        })
    except KernelNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404


@kernels_bp.route("/<kernel_id>/guide", methods=["GET"])
def get_kernel_guide(kernel_id: str):
    """
    获取内核的 Skill 创建指南（SKILL.md 全文内容）。

    此接口主要供前端展示参考，也可用于调试。

    Returns:
        包含 SKILL.md 内容的 JSON 对象。
    """
    try:
        registry = KernelRegistry.get_instance()
        kernel = registry.get_kernel(kernel_id)
        guide = kernel.get_skill_creation_guide()
        return jsonify({
            "kernel_id": kernel_id,
            "guide": guide,
        })
    except KernelNotFoundError as e:
        return jsonify({"error": {"code": e.code, "message": e.message}}), 404


@kernels_bp.route("/<kernel_id>/reload", methods=["POST"])
def reload_kernel(kernel_id: str):
    """
    重新加载指定内核（从本地文件系统重新读取）。

    适用场景：手动替换内核文件后，无需重启服务即可生效。
    不触发网络下载，只重新读取本地文件。

    Returns:
        重新加载后的内核元数据。
    """
    kernel_base = current_app.config.get("KERNEL_BASE_PATH", "/app/kernels")
    kernel_path = f"{kernel_base}/{kernel_id}"

    try:
        registry = KernelRegistry.get_instance()
        registry.reload_kernel(kernel_id, kernel_path)
        kernel = registry.get_kernel(kernel_id)
        meta = kernel.get_kernel_meta()
        return jsonify({
            "message": f"内核 '{kernel_id}' 已重新加载",
            "kernel": {
                "kernel_id": meta.kernel_id,
                "version": meta.version,
                "status": meta.status,
            },
        })
    except Exception as e:
        current_app.logger.error(f"内核重载失败: {e}", exc_info=True)
        return jsonify({
            "error": {"code": "KERNEL_RELOAD_ERROR", "message": "内核重新加载失败，请查看服务日志"}
        }), 500
