import pytest
from cryptography.fernet import Fernet

from app import create_app
from app.config import TestingConfig


class ProductionTestConfig(TestingConfig):
    PRODUCTION = True
    SECRET_KEY = "a-test-only-secret-with-at-least-32-characters"
    TRUSTED_ORIGINS = ["https://judge.example.cn"]
    SESSION_COOKIE_SECURE = True
    LLM_ENCRYPTION_KEY = Fernet.generate_key().decode()


def test_production_rejects_unsafe_configuration():
    class WeakSecret(ProductionTestConfig):
        SECRET_KEY = "dev-only-change-me"

    class NoOrigins(ProductionTestConfig):
        TRUSTED_ORIGINS = []

    class InsecureCookie(ProductionTestConfig):
        SESSION_COOKIE_SECURE = False

    for config in (WeakSecret, NoOrigins, InsecureCookie):
        with pytest.raises(ValueError):
            create_app(config)


@pytest.mark.parametrize("origin", [None, "https://evil.example", "https://example.cn", "null", "https://judge.example.cn.evil.example"])
def test_production_blocks_cross_origin_mutations(origin):
    client = create_app(ProductionTestConfig).test_client()
    headers = {"Origin": origin} if origin is not None else {}
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        response = client.open("/api/auth/logout", method=method, headers=headers)
        assert response.status_code == 403
        assert response.json["message"] == "请求来源不受信任。"


def test_trusted_origin_reaches_auth_and_health_is_public():
    client = create_app(ProductionTestConfig).test_client()
    assert client.post("/api/auth/logout", headers={"Origin": "https://judge.example.cn"}).status_code == 401
    assert client.get("/api/health").json == {"status": "ok"}
    assert client.get("/api/auth/me").json == {"user": None}


def test_oversize_upload_returns_json():
    class SmallRequest(ProductionTestConfig):
        MAX_CONTENT_LENGTH = 10

    client = create_app(SmallRequest).test_client()
    response = client.post("/api/auth/login", data='{"username":"too-long"}', content_type="application/json", headers={"Origin": "https://judge.example.cn"})
    assert response.status_code == 413
    assert "message" in response.json


def test_api_key_encryption_and_plaintext_refusal():
    from app.services.secrets import decrypt_api_key, encrypt_api_key

    app = create_app(ProductionTestConfig)
    with app.app_context():
        encrypted = encrypt_api_key("test-key-only")
        assert encrypted.startswith("fernet:")
        assert "test-key-only" not in encrypted
        assert decrypt_api_key(encrypted) == "test-key-only"
        with pytest.raises(ValueError, match="Legacy plaintext"):
            decrypt_api_key("test-key-only")


def test_legacy_key_conversion_is_idempotent():
    from app.extensions import db
    from app.models import TeacherLLMConfig, User
    from app.services.secrets import decrypt_api_key

    app = create_app(ProductionTestConfig)
    with app.app_context():
        db.create_all()
        teacher = User(username="encryption-test-teacher", role=User.ROLE_TEACHER)
        teacher.set_password("test-password")
        db.session.add(teacher)
        db.session.flush()
        config = TeacherLLMConfig(teacher_id=teacher.id, encrypted_api_key="test-key-only", base_url="https://api.example.com", model="test-model")
        db.session.add(config)
        db.session.commit()
        runner = app.test_cli_runner()
        assert runner.invoke(args=["encrypt-llm-keys"]).exit_code == 0
        first = config.encrypted_api_key
        second = runner.invoke(args=["encrypt-llm-keys"])
        assert second.exit_code == 0
        assert "Encrypted 0" in second.output
        assert config.encrypted_api_key == first
        assert decrypt_api_key(first) == "test-key-only"
        db.session.remove()
        db.drop_all()
