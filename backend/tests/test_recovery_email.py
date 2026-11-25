from datetime import UTC, datetime
from hashlib import sha256

import pytest

from app.services.account_recovery import CODE_ALPHABET, code_digest, generate_code, send_code
from app.services.recovery_email import build_recovery_email


@pytest.mark.parametrize("binding, chinese, english", [
    (True, "绑定找回邮箱", "Bind your recovery email"),
    (False, "重置你的密码", "Reset your password"),
])
def test_personalized_bilingual_html_mail_has_code_security_reminders_and_signature(app, binding, chinese, english):
    app.config["SMTP_FROM"] = "judge@example.test"
    message = build_recovery_email("owner@example.test", "X7M2Q9", "张晓雨", binding=binding,
                                    valid_minutes=15, sent_at=datetime(2026, 11, 25, 6, 30, tzinfo=UTC))
    assert message.get_content_type() == "multipart/alternative"
    html = message.get_body(preferencelist=("html",)).get_content()
    text = message.get_body(preferencelist=("plain",)).get_content()
    for body in (html, text):
        for phrase in (chinese, english, "张晓雨", "X7M2Q9", "15", "Sunjudge", "2026-11-25 14:30 (UTC+08:00)"):
            assert phrase in body
        assert "ignore this email" in body
        assert "验证码" in body and "Single use" in body
        assert "System" not in body and "系统自动发送" not in body
        if binding:
            assert "完成找回邮箱绑定" in body and "重置你的密码" not in body
        else:
            assert "继续重置你的密码" in body and "找回邮箱绑定" not in body
    assert 'color:#0969da' in html and 'class="email-code"' in html
    assert message["From"].addresses[0].display_name == "Sunjudge"
    assert message["To"] == "owner@example.test"
    assert chinese in str(message["Subject"]) and english in str(message["Subject"])
    assert message["Date"] and message["Message-ID"]


def test_personalized_name_is_html_escaped(app):
    app.config["SMTP_FROM"] = "judge@example.test"
    message = build_recovery_email("owner@example.test", "X7M2Q9", '<img src=x onerror="alert(1)">',
                                    binding=False, valid_minutes=15)
    html = message.get_body(preferencelist=("html",)).get_content()
    assert "<img" not in html
    assert "&lt;img" in html and "&#34;" in html


def test_six_character_codes_mix_letters_and_digits_and_accept_either_letter_case(app):
    for _ in range(50):
        code = generate_code()
        assert len(code) == 6 and set(code) <= set(CODE_ALPHABET)
        assert any(character.isalpha() for character in code)
        assert any(character.isdigit() for character in code)
        assert code_digest(code) == code_digest(f" {code.lower()} ")
        assert code_digest(code) != sha256(code.encode()).hexdigest()
    for value in (None, 123456, "X7M2Q", "X7M2Q9Z", "X7 M2Q", "X7M2Q!"):
        assert code_digest(value) is None
    legacy = "aB-cD_12" * 4
    assert code_digest(legacy) == sha256(legacy.encode()).hexdigest()


@pytest.mark.parametrize("security", ["ssl", "starttls"])
def test_smtp_transport_sends_the_html_message_with_personalized_name(app, monkeypatch, security):
    delivered, actions = [], []

    class SMTP:
        def __init__(self, host, port, **kwargs):
            assert host == "smtp.example.test" and kwargs["timeout"] == 8

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, **kwargs):
            actions.append("starttls")

        def login(self, username, password):
            assert (username, password) == ("judge@example.test", "test-authorization-code")
            actions.append("login")

        def send_message(self, message):
            delivered.append(message)

    monkeypatch.setattr("app.services.account_recovery.smtplib.SMTP_SSL", SMTP)
    monkeypatch.setattr("app.services.account_recovery.smtplib.SMTP", SMTP)
    app.config.update(SMTP_FROM="judge@example.test", SMTP_HOST="smtp.example.test", SMTP_SECURITY=security,
                      SMTP_USERNAME="judge@example.test", SMTP_PASSWORD="test-authorization-code")
    send_code("owner@example.test", "X7M2Q9", binding=True, recipient_name="teacher1")
    assert actions == (["starttls", "login"] if security == "starttls" else ["login"])
    assert len(delivered) == 1
    assert "teacher1" in delivered[0].get_body(preferencelist=("html",)).get_content()
