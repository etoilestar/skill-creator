"""
backend/tests/conftest.py

pytest 全局 fixtures 配置。

提供：
    - Flask 测试应用实例
    - 数据库测试客户端（每个测试函数后回滚，不污染数据）
    - 测试专用 HTTP 客户端
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def app():
    """创建测试 Flask 应用实例（整个测试 session 共用一个）。"""
    import os
    os.environ["FLASK_ENV"] = "testing"

    from app import create_app
    app = create_app("testing")
    return app


@pytest.fixture(scope="session")
def db(app):
    """创建测试数据库（整个 session 建表一次）。"""
    from app.extensions import db as _db
    import app.models as _app_models  # noqa: ensure all models are registered

    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture(autouse=False)
def db_session(db, app):
    """
    每个测试函数提供干净的数据库事务。

    测试开始前开启事务，测试完成后回滚，
    确保测试之间不互相影响。
    """
    with app.app_context():
        connection = db.engine.connect()
        transaction = connection.begin()
        db.session.bind = connection
        yield db.session
        db.session.remove()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(app):
    """提供 Flask 测试 HTTP 客户端。"""
    with app.test_client() as client:
        yield client
