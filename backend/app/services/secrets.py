"""Encrypt teacher keys without changing the existing database column."""
from cryptography.fernet import Fernet
from flask import current_app

PREFIX = "fernet:"


def encrypt_api_key(value: str) -> str:
    key = current_app.config.get("LLM_ENCRYPTION_KEY")
    if not key:
        if current_app.config.get("PRODUCTION"):
            raise ValueError("LLM_ENCRYPTION_KEY is required in production.")
        return value
    encrypted = PREFIX + Fernet(key.encode()).encrypt(value.encode()).decode()
    if len(encrypted) > 500:
        raise ValueError("Encrypted API key exceeds the database column limit.")
    return encrypted


def decrypt_api_key(value: str) -> str:
    if not value.startswith(PREFIX):
        if current_app.config.get("PRODUCTION"):
            raise ValueError("Legacy plaintext API key: run encrypt-llm-keys first.")
        return value
    key = current_app.config.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY is required to decrypt this API key.")
    return Fernet(key.encode()).decrypt(value[len(PREFIX):].encode()).decode()
