"""
backend/scripts/init_db.py

数据库初始化脚本。

职责：
    - 创建所有数据库表（如果不存在）
    - 运行 Alembic 数据库迁移
    - 可选：创建初始测试数据（开发环境）

使用方式：
    # 在 backend/ 目录下执行
    python scripts/init_db.py

    # 跳过 Alembic 迁移（直接使用 create_all）
    python scripts/init_db.py --no-migrate

    # 创建示例模型配置（开发环境调试用）
    python scripts/init_db.py --seed

注意：
    - 生产环境推荐使用 flask db upgrade 而不是 create_all
    - --seed 选项只应在开发环境使用，不能在生产环境执行
"""

import argparse
import os
import sys
from pathlib import Path

# 将 backend/ 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("FLASK_ENV", "development")


def init_db(use_migrate: bool = True, seed: bool = False) -> None:
    """
    初始化数据库。

    Args:
        use_migrate: 是否使用 Alembic 迁移（True）还是直接 create_all（False）
        seed: 是否创建初始种子数据
    """
    from app import create_app
    from app.extensions import db

    app = create_app()

    with app.app_context():
        if use_migrate:
            print("运行 Alembic 数据库迁移...")
            from flask_migrate import upgrade
            upgrade()
        else:
            print("使用 create_all 创建数据库表...")
            # 导入所有模型（确保 SQLAlchemy 知道所有表）
            import app.models  # noqa
            db.create_all()

        print("✅ 数据库初始化完成")

        if seed:
            _create_seed_data(app)


def _create_seed_data(app) -> None:
    """
    创建开发环境种子数据（仅用于本地调试）。

    创建一个示例本地模型配置（指向 Ollama 默认端口）。
    """
    from app.extensions import db
    from app.models.model_config import ModelConfig
    from app.model.encryption import encrypt_api_key

    # 如果已有配置则跳过
    if ModelConfig.query.first():
        print("已存在模型配置，跳过种子数据创建")
        return

    print("创建示例本地模型配置（Ollama）...")
    config = ModelConfig(
        name="本地 Ollama (开发用)",
        provider="local_openai_compat",
        api_base_url="http://host.docker.internal:11434/v1",
        api_key_encrypted=encrypt_api_key("not-needed"),
        model_name="qwen2.5:7b",
        is_active=True,
        max_tokens=4096,
        temperature=0.7,
    )
    db.session.add(config)
    db.session.commit()
    print(f"✅ 已创建示例配置: {config.name}")


def main():
    parser = argparse.ArgumentParser(description="初始化数据库")
    parser.add_argument("--no-migrate", action="store_true", help="使用 create_all 而非 Alembic 迁移")
    parser.add_argument("--seed", action="store_true", help="创建种子数据（仅开发环境）")
    args = parser.parse_args()

    init_db(use_migrate=not args.no_migrate, seed=args.seed)


if __name__ == "__main__":
    main()
