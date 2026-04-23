"""
backend/app/__init__.py

Flask 应用工厂函数（Application Factory）。

职责：
    - 创建并配置 Flask 应用实例
    - 注册所有扩展（数据库、迁移、CORS 等）
    - 注册所有 API 蓝图（Blueprint）
    - 完成启动时的内核加载与校验

注意：
    - 使用工厂模式便于测试时创建独立的 app 实例
    - 所有扩展必须先在 extensions.py 中实例化，再在此处绑定 app
    - 内核加载失败时应记录错误日志但不阻断启动（允许降级运行）
"""

import logging
import os

from flask import Flask
from flask_cors import CORS

from .extensions import db, migrate, celery_app
from .kernel.registry import KernelRegistry


def create_app(config_name: str = None) -> Flask:
    """
    创建并返回 Flask 应用实例。

    Args:
        config_name: 配置环境名称（development / production / testing）。
                     若为 None，则从环境变量 FLASK_ENV 读取，默认为 development。

    Returns:
        配置完成的 Flask 应用实例。
    """
    app = Flask(__name__, instance_relative_config=True)

    # ------------------------------------------------------------------
    # 1. 加载配置
    # ------------------------------------------------------------------
    _load_config(app, config_name)

    # ------------------------------------------------------------------
    # 2. 初始化扩展
    # ------------------------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # 初始化 Celery，将 Flask app 上下文绑定到 Celery 任务
    _init_celery(app)

    # ------------------------------------------------------------------
    # 3. 注册 API 蓝图
    # ------------------------------------------------------------------
    _register_blueprints(app)

    # ------------------------------------------------------------------
    # 4. 启动时加载 skill-creator 内核
    # ------------------------------------------------------------------
    with app.app_context():
        _load_kernels(app)

    # ------------------------------------------------------------------
    # 5. 注册错误处理器
    # ------------------------------------------------------------------
    _register_error_handlers(app)

    return app


def _load_config(app: Flask, config_name: str = None) -> None:
    """
    加载 Flask 应用配置。

    优先级：环境变量 > 默认配置
    配置类定义在 app/config.py 中。

    Args:
        app: Flask 应用实例
        config_name: 配置名称
    """
    from .config import config_map

    env = config_name or os.environ.get("FLASK_ENV", "development")
    cfg_class = config_map.get(env, config_map["development"])
    app.config.from_object(cfg_class)
    app.logger.info(f"已加载配置环境: {env}")


def _init_celery(app: Flask) -> None:
    """
    将 Flask app 上下文绑定到 Celery 实例。

    Celery 任务在执行时需要访问 Flask app 上下文（数据库连接等），
    通过此函数确保每次 Celery 任务执行时自动推入 Flask 上下文。

    Args:
        app: Flask 应用实例
    """
    celery_app.conf.update(app.config.get("CELERY", {}))

    class ContextTask(celery_app.Task):
        """在 Flask 应用上下文中执行的 Celery 任务基类。"""

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app.Task = ContextTask


def _register_blueprints(app: Flask) -> None:
    """
    注册所有 API 蓝图。

    每个蓝图对应一组相关接口，统一挂载在 /api/v1/ 前缀下。

    Args:
        app: Flask 应用实例
    """
    from .api.v1.config import config_bp
    from .api.v1.kernels import kernels_bp
    from .api.v1.sessions import sessions_bp
    from .api.v1.tasks import tasks_bp
    from .api.v1.files import files_bp
    from .api.v1.tests import tests_bp

    app.register_blueprint(config_bp, url_prefix="/api/v1/config")
    app.register_blueprint(kernels_bp, url_prefix="/api/v1/kernels")
    app.register_blueprint(sessions_bp, url_prefix="/api/v1/sessions")
    app.register_blueprint(tasks_bp, url_prefix="/api/v1/tasks")
    app.register_blueprint(files_bp, url_prefix="/api/v1/tasks")
    app.register_blueprint(tests_bp, url_prefix="/api/v1/tasks")

    app.logger.info("所有 API 蓝图注册完成")


def _load_kernels(app: Flask) -> None:
    """
    应用启动时加载所有已注册的内核。

    当前第一阶段只加载 skill-creator 内核。
    加载失败时记录错误日志，但不中止服务启动（允许降级运行）。
    后续可扩展为从数据库动态加载多个内核。

    Args:
        app: Flask 应用实例
    """
    kernel_base_path = app.config.get("KERNEL_BASE_PATH")
    if not kernel_base_path:
        app.logger.warning("KERNEL_BASE_PATH 未配置，跳过内核加载")
        return

    registry = KernelRegistry.get_instance()
    try:
        registry.load_kernel(
            kernel_id="skill-creator",
            kernel_path=os.path.join(kernel_base_path, "skill-creator"),
        )
        app.logger.info("skill-creator 内核加载成功")
    except Exception as e:
        app.logger.error(f"skill-creator 内核加载失败: {e}", exc_info=True)


def _register_error_handlers(app: Flask) -> None:
    """
    注册全局错误处理器，统一 API 错误响应格式。

    所有未捕获的异常都会被转换为标准 JSON 错误响应：
    {"error": {"code": "...", "message": "..."}}

    Args:
        app: Flask 应用实例
    """
    from flask import jsonify
    from .exceptions import AppBaseError

    @app.errorhandler(AppBaseError)
    def handle_app_error(e):
        """处理应用自定义异常。"""
        return jsonify({"error": {"code": e.code, "message": e.message}}), e.http_status

    @app.errorhandler(404)
    def handle_not_found(e):
        return jsonify({"error": {"code": "NOT_FOUND", "message": "资源不存在"}}), 404

    @app.errorhandler(405)
    def handle_method_not_allowed(e):
        return jsonify({"error": {"code": "METHOD_NOT_ALLOWED", "message": "请求方法不允许"}}), 405

    @app.errorhandler(500)
    def handle_internal_error(e):
        app.logger.error(f"未处理的服务器错误: {e}", exc_info=True)
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "服务器内部错误"}}), 500
