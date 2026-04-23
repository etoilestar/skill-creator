"""
backend/app/config.py

Flask 应用配置类定义。

职责：
    - 定义开发、生产、测试三种配置环境
    - 所有可变配置均从环境变量读取，不硬编码敏感信息
    - 提供 config_map 字典供应用工厂函数选择配置

注意：
    - 数据库连接字符串、Redis URL、密钥等必须通过环境变量注入
    - 生产环境必须设置 SECRET_KEY 和 ENCRYPTION_KEY 为强随机值
    - KERNEL_BASE_PATH 指向宿主机或容器内的内核目录绝对路径
"""

import os
from pathlib import Path

# 项目根目录（backend/ 的上一级，即仓库根目录）
BASE_DIR = Path(__file__).resolve().parent.parent


class BaseConfig:
    """
    基础配置类，所有环境配置继承此类。

    包含所有配置项的默认值，子类可覆盖特定配置。
    """

    # ------------------------------------------------------------------
    # Flask 核心配置
    # ------------------------------------------------------------------

    # 应用密钥，用于 session 签名等（生产环境必须设置强随机值）
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    # 是否开启调试模式（生产环境必须为 False）
    DEBUG: bool = False

    # 是否开启测试模式
    TESTING: bool = False

    # JSON 响应使用 UTF-8 编码（避免中文被转义为 Unicode 转义序列）
    JSON_AS_ASCII: bool = False

    # ------------------------------------------------------------------
    # 数据库配置（PostgreSQL）
    # ------------------------------------------------------------------

    # 数据库连接 URI，格式：postgresql://user:password@host:port/dbname
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        "postgresql://skilluser:skillpass@localhost:5432/skillfactory",
    )

    # 禁用 SQLAlchemy 修改追踪（节省内存，除非需要 Flask-SQLAlchemy 事件系统）
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # 数据库连接池配置
    SQLALCHEMY_ENGINE_OPTIONS: dict = {
        "pool_size": 10,         # 连接池大小
        "max_overflow": 20,      # 超出 pool_size 后最大允许的额外连接数
        "pool_pre_ping": True,   # 使用前检查连接是否存活，避免"连接已断开"错误
        "pool_recycle": 3600,    # 连接超过 1 小时后自动回收，防止 MySQL/PG 超时断开
    }

    # ------------------------------------------------------------------
    # Redis 配置（Celery 消息队列 + 任务结果后端）
    # ------------------------------------------------------------------

    REDIS_URL: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # ------------------------------------------------------------------
    # Celery 配置
    # ------------------------------------------------------------------

    CELERY: dict = {
        "broker_url": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        "result_backend": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        # 任务序列化格式（JSON 便于跨语言互操作）
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        # 时区设置
        "timezone": "Asia/Shanghai",
        "enable_utc": True,
        # 任务路由（将不同类型的任务路由到不同队列，便于独立扩展）
        "task_routes": {
            "app.tasks.skill_creation_task.*": {"queue": "skill_creation"},
            "app.tasks.sandbox_test_task.*": {"queue": "sandbox_test"},
        },
        # 任务超时设置（秒）
        "task_soft_time_limit": 300,    # 软超时：触发 SoftTimeLimitExceeded 异常
        "task_time_limit": 600,          # 硬超时：强制终止任务进程
    }

    # ------------------------------------------------------------------
    # 内核配置
    # ------------------------------------------------------------------

    # 内核目录的绝对路径（Docker 中为 /app/kernels，本地开发为 backend/kernels）
    KERNEL_BASE_PATH: str = os.environ.get(
        "KERNEL_BASE_PATH",
        str(BASE_DIR / "kernels"),
    )

    # ------------------------------------------------------------------
    # 工作区配置
    # ------------------------------------------------------------------

    # 用户 Skill 工作区根目录
    WORKSPACE_BASE_PATH: str = os.environ.get(
        "WORKSPACE_BASE_PATH",
        str(BASE_DIR / "app" / "workspace"),
    )

    # 沙盒测试区根目录
    SANDBOX_BASE_PATH: str = os.environ.get(
        "SANDBOX_BASE_PATH",
        str(BASE_DIR / "app" / "sandboxes"),
    )

    # ------------------------------------------------------------------
    # 加密配置（用于 API Key 等敏感信息的加密存储）
    # ------------------------------------------------------------------

    # Fernet 加密密钥，必须是 32 字节的 URL-safe base64 编码字符串
    # 生成方法：from cryptography.fernet import Fernet; Fernet.generate_key()
    ENCRYPTION_KEY: str = os.environ.get(
        "ENCRYPTION_KEY",
        "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTI=",  # 仅开发环境占位符
    )

    # ------------------------------------------------------------------
    # 沙盒测试配置
    # ------------------------------------------------------------------

    # 沙盒容器使用的 Docker 镜像
    SANDBOX_DOCKER_IMAGE: str = os.environ.get(
        "SANDBOX_DOCKER_IMAGE",
        "skillfactory-sandbox:latest",
    )

    # 沙盒执行超时时间（秒）
    SANDBOX_TIMEOUT_SECONDS: int = int(os.environ.get("SANDBOX_TIMEOUT_SECONDS", "60"))

    # 沙盒容器内存限制
    SANDBOX_MEMORY_LIMIT: str = os.environ.get("SANDBOX_MEMORY_LIMIT", "256m")

    # 沙盒容器 CPU 限制（核数）
    SANDBOX_CPU_LIMIT: str = os.environ.get("SANDBOX_CPU_LIMIT", "0.5")

    # 是否允许在沙盒测试前通过 pip 自动安装 requirements.txt 中的依赖
    # 安装步骤使用独立的、允许网络的容器，安装完成后正式测试仍使用 --network none
    SANDBOX_ALLOW_PIP_INSTALL: bool = os.environ.get(
        "SANDBOX_ALLOW_PIP_INSTALL", "false"
    ).lower() == "true"


class DevelopmentConfig(BaseConfig):
    """开发环境配置。"""

    DEBUG = True

    # 开发环境使用 SQLite，便于本地快速启动（无需 PostgreSQL）
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'dev.db'}",
    )


class ProductionConfig(BaseConfig):
    """生产环境配置。"""

    DEBUG = False

    # 生产环境必须通过环境变量设置数据库 URI
    SQLALCHEMY_DATABASE_URI: str = os.environ.get("DATABASE_URL", "")


class TestingConfig(BaseConfig):
    """测试环境配置。"""

    TESTING = True
    DEBUG = True

    # 测试使用内存 SQLite，每次测试后自动清理
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///:memory:"

    # 测试时禁用 Celery 异步，改为同步执行
    CELERY: dict = {
        **BaseConfig.CELERY,
        "task_always_eager": True,   # 任务同步执行，便于测试断言
        "task_eager_propagates": True,
    }


# 配置名称到配置类的映射，供应用工厂函数使用
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
