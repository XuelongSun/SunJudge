from __future__ import annotations

from pathlib import Path

import click
from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config
from .extensions import db, login_manager, migrate
from .models import User
from .routes.admin import admin_bp
from .routes.assignments import assignments_bp
from .routes.auth import auth_bp
from .routes.classes import classes_bp
from .services.grading_queue import init_grading_queue


def create_app(config_object: type[Config] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(classes_bp, url_prefix="/api/classes")
    app.register_blueprint(assignments_bp, url_prefix="/api")

    register_cli(app)
    register_error_handlers(app)
    init_grading_queue(app)

    return app


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({"message": "请先登录。"}), 401


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(403)
    def forbidden(_error):
        return jsonify({"message": "没有权限执行该操作。"}), 403

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"message": "资源不存在。"}), 404


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("password")
    def create_admin_command(username: str, password: str) -> None:
        existing = User.query.filter_by(username=username).first()
        if existing:
            raise SystemExit(f"用户 {username} 已存在。")

        user = User(username=username, role=User.ROLE_ADMIN)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"管理员 {username} 已创建。")
