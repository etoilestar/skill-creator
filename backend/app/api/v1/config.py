"""
backend/app/api/v1/config.py

模型配置管理 API 蓝图。

接口列表：
    GET    /api/v1/config/models          获取所有模型配置列表
    POST   /api/v1/config/models          新增模型配置
    PUT    /api/v1/config/models/<id>     更新模型配置
    DELETE /api/v1/config/models/<id>     删除模型配置
    POST   /api/v1/config/models/<id>/activate  激活指定配置
    POST   /api/v1/config/models/<id>/test      测试模型连通性

注意：
    - API Key 在接收时加密存储，返回时只显示"已配置/未配置"状态
    - 同时只能有一个激活的模型配置（activate 操作会取消其他配置的激活）
    - 删除激活中的配置前需先激活其他配置
"""

from flask import Blueprint, jsonify, request

from ...exceptions import AppBaseError, ModelNotConfiguredError
from ...extensions import db
from ...model.encryption import decrypt_api_key, encrypt_api_key
from ...model.provider import ModelProviderFactory
from ...models.model_config import ModelConfig

config_bp = Blueprint("config", __name__)


@config_bp.route("/models", methods=["GET"])
def list_models():
    """
    获取所有模型配置列表。

    Returns:
        JSON 数组，每个元素为脱敏后的模型配置信息。
    """
    configs = ModelConfig.query.order_by(ModelConfig.created_at.desc()).all()
    return jsonify([c.to_dict() for c in configs])


@config_bp.route("/models", methods=["POST"])
def create_model():
    """
    新增模型配置。

    Request Body (JSON):
        name: str, 必填，配置显示名称
        provider: str, 必填，提供商类型（openai/azure/local_openai_compat）
        model_name: str, 必填，模型名称
        api_key: str, 可选，API Key 明文（存储时加密）
        api_base_url: str, 可选，API 基础 URL
        max_tokens: int, 可选，默认 4096
        temperature: float, 可选，默认 0.7
        extra_params: dict, 可选，额外参数

    Returns:
        新创建的配置信息（脱敏）。
    """
    data = request.get_json(force=True) or {}

    # 必填字段校验
    for field in ("name", "provider", "model_name"):
        if not data.get(field):
            return jsonify({"error": {"code": "MISSING_FIELD", "message": f"缺少必填字段: {field}"}}), 400

    config = ModelConfig(
        name=data["name"],
        provider=data["provider"],
        model_name=data["model_name"],
        api_base_url=data.get("api_base_url"),
        api_key_encrypted=encrypt_api_key(data.get("api_key", "")),
        max_tokens=int(data.get("max_tokens", 4096)),
        temperature=float(data.get("temperature", 0.7)),
        extra_params=data.get("extra_params", {}),
        is_active=False,
    )
    db.session.add(config)
    db.session.commit()
    return jsonify(config.to_dict()), 201


@config_bp.route("/models/<config_id>", methods=["PUT"])
def update_model(config_id: str):
    """
    更新已有模型配置。

    Request Body (JSON): 同 create_model，所有字段均可选。
    """
    config = ModelConfig.query.get(config_id)
    if config is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "配置不存在"}}), 404

    data = request.get_json(force=True) or {}

    if "name" in data:
        config.name = data["name"]
    if "provider" in data:
        config.provider = data["provider"]
    if "model_name" in data:
        config.model_name = data["model_name"]
    if "api_base_url" in data:
        config.api_base_url = data["api_base_url"]
    if "api_key" in data and data["api_key"]:
        # 只有提供了新 api_key 才更新（空字符串视为不修改）
        config.api_key_encrypted = encrypt_api_key(data["api_key"])
    if "max_tokens" in data:
        config.max_tokens = int(data["max_tokens"])
    if "temperature" in data:
        config.temperature = float(data["temperature"])
    if "extra_params" in data:
        config.extra_params = data["extra_params"]

    db.session.commit()
    return jsonify(config.to_dict())


@config_bp.route("/models/<config_id>", methods=["DELETE"])
def delete_model(config_id: str):
    """
    删除模型配置。

    不允许删除当前激活的配置（需要先激活其他配置再删除）。
    """
    config = ModelConfig.query.get(config_id)
    if config is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "配置不存在"}}), 404

    if config.is_active:
        return jsonify({
            "error": {
                "code": "CANNOT_DELETE_ACTIVE",
                "message": "无法删除当前激活的配置，请先激活其他配置",
            }
        }), 400

    db.session.delete(config)
    db.session.commit()
    return jsonify({"message": "配置已删除"}), 200


@config_bp.route("/models/<config_id>/activate", methods=["POST"])
def activate_model(config_id: str):
    """
    将指定配置设为当前激活配置。

    执行步骤：
    1. 将所有配置的 is_active 设为 False
    2. 将指定配置的 is_active 设为 True
    """
    config = ModelConfig.query.get(config_id)
    if config is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "配置不存在"}}), 404

    # 取消所有配置的激活状态
    ModelConfig.query.update({"is_active": False})
    config.is_active = True
    db.session.commit()

    return jsonify({"message": f"配置 '{config.name}' 已激活", "config": config.to_dict()})


@config_bp.route("/models/test", methods=["POST"])
def test_model_inline():
    """
    使用请求体中的凭据直接测试模型连通性（无需已保存的配置 ID）。

    适用于添加/编辑模型配置弹窗中的"测试连接"按钮，
    在用户保存配置之前即可验证凭据是否有效。

    Request Body (JSON):
        provider:     str, 必填，提供商类型（openai/azure/local_openai_compat）
        model_name:   str, 必填，模型名称
        api_key:      str, 可选，API Key 明文
        api_base_url: str, 可选，API 基础 URL
        max_tokens:   int, 可选，默认 4096
        temperature:  float, 可选，默认 0.7

    Returns:
        {success, latency_ms, error, model_info}
    """
    data = request.get_json(force=True) or {}

    for field in ("provider", "model_name"):
        if not data.get(field):
            return jsonify({"error": {"code": "MISSING_FIELD", "message": f"缺少必填字段: {field}"}}), 400

    class _InlineConfig:
        """临时配置对象，无需持久化到数据库。"""
        provider = data["provider"]
        model_name = data["model_name"]
        api_base_url = data.get("api_base_url") or None
        max_tokens = int(data.get("max_tokens", 4096))
        temperature = float(data.get("temperature", 0.7))
        extra_params = data.get("extra_params") or {}

    provider = ModelProviderFactory.create(_InlineConfig(), data.get("api_key", ""))
    result = provider.test_connection()

    return jsonify({
        "success": result.success,
        "latency_ms": result.latency_ms,
        "error": result.error,
        "model_info": result.model_info,
    })


@config_bp.route("/models/<config_id>/test", methods=["POST"])
def test_model_connection(config_id: str):
    """
    测试指定模型配置的 API 连通性。

    发送一条简单请求验证 API 可达性，返回连通状态和响应延迟。
    """
    config = ModelConfig.query.get(config_id)
    if config is None:
        return jsonify({"error": {"code": "NOT_FOUND", "message": "配置不存在"}}), 404

    decrypted_key = decrypt_api_key(config.api_key_encrypted) if config.api_key_encrypted else ""
    provider = ModelProviderFactory.create(config, decrypted_key)
    result = provider.test_connection()

    return jsonify({
        "success": result.success,
        "latency_ms": result.latency_ms,
        "error": result.error,
        "model_info": result.model_info,
    })
