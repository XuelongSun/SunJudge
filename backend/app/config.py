from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'instance' / 'sunjudge.sqlite'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", str(BASE_DIR / "instance" / "uploads"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(64 * 1024 * 1024)))
    JUDGE_DOCKER_IMAGE = os.getenv("JUDGE_DOCKER_IMAGE", "python:3.11-slim")
    JUDGE_DOCKER_PREPARE_TIMEOUT = int(os.getenv("JUDGE_DOCKER_PREPARE_TIMEOUT", "300"))
    JUDGE_DOCKER_HOST_TIMEOUT_BUFFER = int(os.getenv("JUDGE_DOCKER_HOST_TIMEOUT_BUFFER", "30"))
    GRADING_QUEUE_INLINE = os.getenv("GRADING_QUEUE_INLINE", "false").lower() in {"1", "true", "yes"}
    LLM_GRADING_TIMEOUT = int(os.getenv("LLM_GRADING_TIMEOUT", "60"))


class TestingConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    GRADING_QUEUE_INLINE = True
