from __future__ import annotations

from pathlib import Path

import click
from cryptography.fernet import Fernet
from flask import Flask, jsonify, request
from flask_cors import CORS

from .config import Config
from .extensions import db, login_manager, migrate
from .models import TeacherLLMConfig, User
from .routes.admin import admin_bp
from .routes.assignments import assignments_bp
from .routes.auth import auth_bp
from .routes.classes import classes_bp
from .routes.markdown_documents import markdown_bp
from .services.grading_queue import init_grading_queue
from .services.secrets import PREFIX, encrypt_api_key


def create_app(config_object: type[Config] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)
    if app.config.get("PRODUCTION"):
        if len(app.config["SECRET_KEY"]) < 32 or app.config["SECRET_KEY"] == "dev-only-change-me":
            raise ValueError("Production requires a SECRET_KEY of at least 32 characters.")
        if not app.config.get("TRUSTED_ORIGINS"):
            raise ValueError("Production requires explicit TRUSTED_ORIGINS.")
        if not app.config.get("SESSION_COOKIE_SECURE"):
            raise ValueError("Production requires secure session cookies.")
        Fernet(app.config.get("LLM_ENCRYPTION_KEY", "").encode())
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(classes_bp, url_prefix="/api/classes")
    app.register_blueprint(assignments_bp, url_prefix="/api")
    app.register_blueprint(markdown_bp, url_prefix="/api")

    register_cli(app)
    register_error_handlers(app)
    register_origin_guard(app)
    init_grading_queue(app)

    return app


def register_origin_guard(app: Flask) -> None:
    @app.before_request
    def protect_mutating_requests():
        # Exact origin checks also reject untrusted sibling subdomains.
        if app.config.get("PRODUCTION") and request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.headers.get("Origin") not in app.config["TRUSTED_ORIGINS"]:
                return jsonify({"message": "请求来源不受信任。"}), 403

    @app.get("/api/health")
    def health():
        # Liveness only: no database credentials or operational details.
        return jsonify({"status": "ok"})


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

    @app.errorhandler(413)
    def too_large(_error):
        return jsonify({"message": "请求体超过允许的大小。"}), 413


def register_cli(app: Flask) -> None:
    @app.cli.command("cleanup-markdown-assets")
    @click.option("--days", default=7, type=click.IntRange(min=1), help="Only consider unused images older than this many days.")
    @click.option("--apply", is_flag=True, help="Delete candidates; otherwise only report a count.")
    def cleanup_markdown_assets(days: int, apply: bool) -> None:
        from .services.markdown_documents import asset_path, unused_image_assets
        assets = unused_image_assets(days)
        if apply:
            for asset in assets:
                asset_path(asset).unlink(missing_ok=True)
                db.session.delete(asset)
            db.session.commit()
        click.echo(f"{'Deleted' if apply else 'Unused candidates'}: {len(assets)}")

    @app.cli.command("encrypt-llm-keys")
    def encrypt_llm_keys_command() -> None:
        if not app.config.get("LLM_ENCRYPTION_KEY"):
            raise click.ClickException("Configure LLM_ENCRYPTION_KEY first.")
        count = 0
        for config in TeacherLLMConfig.query.all():
            if config.encrypted_api_key and not config.encrypted_api_key.startswith(PREFIX):
                config.encrypted_api_key = encrypt_api_key(config.encrypted_api_key)
                count += 1
        db.session.commit()
        click.echo(f"Encrypted {count} legacy API keys.")

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.argument("password", required=False)
    def create_admin_command(username: str, password: str | None) -> None:
        if password is None:
            password = click.prompt("管理员密码", hide_input=True, confirmation_prompt=True)
        if len(password) < 6:
            raise click.ClickException("密码至少需要 6 个字符。")
        existing = User.query.filter_by(username=username).first()
        if existing:
            raise SystemExit(f"用户 {username} 已存在。")

        user = User(username=username, role=User.ROLE_ADMIN)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"管理员 {username} 已创建。")
