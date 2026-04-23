from flask import Flask
from app.config import config
from app.extensions import db, migrate


def create_app(config_name='development'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)

    from app.kernel.kernel_runtime_manager import KernelRuntimeManager
    kernel_manager = KernelRuntimeManager()
    app.extensions['kernel_manager'] = kernel_manager

    from app.blueprints.health import health_bp
    from app.blueprints.model_configs import model_configs_bp
    from app.blueprints.sessions import sessions_bp
    from app.blueprints.skills import skills_bp
    from app.blueprints.tasks import tasks_bp
    from app.blueprints.sandboxes import sandboxes_bp
    from app.blueprints.kernels import kernels_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(model_configs_bp)
    app.register_blueprint(sessions_bp)
    app.register_blueprint(skills_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(sandboxes_bp)
    app.register_blueprint(kernels_bp)

    return app
