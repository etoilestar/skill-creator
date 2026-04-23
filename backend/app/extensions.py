"""
backend/app/extensions.py

Flask 扩展的全局实例化。

职责：
    - 在模块级别创建各扩展实例（不绑定到具体 app）
    - 通过 Flask 的 init_app() 模式避免循环导入
    - 提供统一的扩展访问入口

注意：
    - 扩展实例在此创建但不初始化（不传入 app）
    - 实际初始化在 create_app() 工厂函数中调用 xxx.init_app(app)
    - celery_app 的特殊处理：需要在 create_app() 中绑定 Flask 上下文
"""

from celery import Celery
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# ------------------------------------------------------------------
# SQLAlchemy 数据库扩展实例
# 所有数据模型都通过 db.Model 基类定义
# ------------------------------------------------------------------
db = SQLAlchemy()

# ------------------------------------------------------------------
# Flask-Migrate 数据库迁移扩展实例
# 封装 Alembic，提供 flask db init/migrate/upgrade 命令
# ------------------------------------------------------------------
migrate = Migrate()

# ------------------------------------------------------------------
# Celery 异步任务队列实例
# 在 create_app() 中会通过 ContextTask 绑定 Flask app 上下文，
# 确保 Celery Worker 执行任务时能访问数据库等 Flask 资源
# ------------------------------------------------------------------
celery_app = Celery(__name__)
