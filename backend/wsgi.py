"""
backend/wsgi.py

WSGI 入口点。

职责：
    - 创建 Flask 应用实例（用于 gunicorn / uWSGI 等生产 WSGI 服务器）
    - 导出 celery_app 供 Celery Worker 和 Flower 使用
    - 提供开发服务器启动入口（python wsgi.py）

使用方式：
    开发环境：
        python wsgi.py
        或
        flask --app wsgi:app run --debug

    生产环境（gunicorn）：
        gunicorn --bind 0.0.0.0:5000 --workers 4 wsgi:app

    Celery Worker：
        celery -A wsgi.celery_app worker --loglevel=info

    Celery Flower 监控：
        celery -A wsgi.celery_app flower --port=5555
"""

import os

from app import create_app
from app.extensions import celery_app  # noqa: F401 — 供 Celery CLI 使用

# 根据环境变量创建 Flask 应用
app = create_app(os.environ.get("FLASK_ENV", "development"))

if __name__ == "__main__":
    # 开发服务器启动（不用于生产）
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=app.config.get("DEBUG", False))
