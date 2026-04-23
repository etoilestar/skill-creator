"""
backend/app/models/model_config.py

AI 模型配置数据模型。

职责：
    - 存储用户配置的 AI 模型接入信息
    - 支持多个模型配置，但同一时刻只能有一个处于激活状态
    - API Key 以加密形式存储，防止数据库泄露时密钥外露
    - 提供序列化方法用于 API 响应

表结构说明：
    - 每行代表一个模型配置（可以是不同的 Provider 或不同的模型名称）
    - is_active 字段确保系统始终知道当前应使用哪个模型
    - api_key_encrypted 存储 Fernet 加密后的 API Key 密文
"""

import uuid
from datetime import datetime

from ..extensions import db


class ModelConfig(db.Model):
    """
    AI 模型配置数据模型。

    Attributes:
        id: 配置 UUID，主键
        name: 配置显示名称（如"本地 Qwen"、"云端 GPT-4"）
        provider: 模型提供商类型（openai / azure / local_openai_compat）
        api_base_url: 模型 API 地址（如 http://ollama:11434/v1）
        api_key_encrypted: 加密存储的 API Key
        model_name: 具体模型名称（如 qwen2.5-72b、gpt-4o）
        is_active: 是否为当前激活使用的配置（全局只能有一个为 True）
        max_tokens: 单次调用最大 Token 数
        temperature: 模型温度参数（0.0-2.0，越高越随机）
        extra_params: 额外模型参数（JSON 格式，用于厂商特定参数）
        created_at: 创建时间
        updated_at: 最后更新时间
    """

    __tablename__ = "model_configs"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        comment="配置唯一标识符（UUID）",
    )
    name = db.Column(
        db.String(100),
        nullable=False,
        comment="配置显示名称，便于用户区分不同配置",
    )
    provider = db.Column(
        db.String(50),
        nullable=False,
        comment="模型提供商类型：openai / azure / local_openai_compat",
    )
    api_base_url = db.Column(
        db.String(500),
        nullable=True,
        comment="模型 API 基础 URL，本地模型必须填写，OpenAI 可留空使用默认值",
    )
    api_key_encrypted = db.Column(
        db.Text,
        nullable=True,
        comment="加密存储的 API Key，使用 Fernet 对称加密",
    )
    model_name = db.Column(
        db.String(200),
        nullable=False,
        comment="模型名称，如 gpt-4o / qwen2.5-72b / deepseek-chat",
    )
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        comment="是否为当前激活的模型配置，全局同时只能有一个为 True",
    )
    max_tokens = db.Column(
        db.Integer,
        nullable=False,
        default=4096,
        comment="单次调用允许的最大 Token 数，影响生成 Skill 的长度上限",
    )
    temperature = db.Column(
        db.Float,
        nullable=False,
        default=0.7,
        comment="模型温度参数（0.0-2.0），Skill 创建场景建议 0.6-0.8",
    )
    extra_params = db.Column(
        db.JSON,
        nullable=True,
        default=dict,
        comment="额外模型参数（JSON 格式），用于传递厂商特定参数",
    )
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="记录创建时间（UTC）",
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="记录最后更新时间（UTC）",
    )

    def to_dict(self, include_key: bool = False) -> dict:
        """
        将模型配置序列化为字典，用于 API 响应。

        Args:
            include_key: 是否在返回结果中包含 API Key（默认不包含）。
                         仅在内部调试场景下设为 True，绝不对外暴露。

        Returns:
            包含配置信息的字典，api_key 字段始终做脱敏处理。
        """
        result = {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "api_base_url": self.api_base_url,
            "model_name": self.model_name,
            "is_active": self.is_active,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "extra_params": self.extra_params or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        # API Key 只返回脱敏后的提示字符串，不返回实际密文
        result["has_api_key"] = bool(self.api_key_encrypted)
        return result

    def __repr__(self):
        return f"<ModelConfig {self.name} ({self.provider}/{self.model_name}) active={self.is_active}>"
