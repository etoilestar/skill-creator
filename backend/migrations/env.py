"""
backend/migrations/env.py

Alembic 数据库迁移环境配置。

此文件由 flask db init 生成，已根据项目需求进行定制。
确保所有 SQLAlchemy 模型都被导入，以便 Alembic 能够自动检测表结构变化。
"""

import os
from logging.config import fileConfig

from alembic import context
from flask import current_app

from app.extensions import db

# Alembic Config 对象
config = context.config

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 导入所有模型（确保 Alembic 能检测到所有表）
import app.models  # noqa: F401

target_metadata = db.metadata


def get_url():
    return current_app.config.get("SQLALCHEMY_DATABASE_URI", "")


def run_migrations_offline() -> None:
    """离线模式（不需要数据库连接）。"""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式（需要数据库连接）。"""
    connectable = db.engine
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
