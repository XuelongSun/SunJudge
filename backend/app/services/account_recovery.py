from __future__ import annotations

import re
import hmac
import smtplib
import ssl
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from secrets import choice
from threading import BoundedSemaphore

from flask import Flask, current_app
from sqlalchemy import or_, update
from werkzeug.security import generate_password_hash

from ..extensions import db
from ..models import AccountRecovery, AuditLog, ClassRoster, User, utc_now
from .recovery_email import build_recovery_email


CODE_LIFETIME = timedelta(minutes=15)
SEND_INTERVAL = timedelta(minutes=1)
MAX_CODE_ATTEMPTS = 5
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
EMAIL_PATTERN = re.compile(r"[a-z0-9_+%-]+(?:\.[a-z0-9_+%-]+)*@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
CODE_PATTERN = re.compile(r"[A-Za-z0-9]{6}")
LEGACY_CODE_PATTERN = re.compile(r"[a-zA-Z0-9_-]{32}")
_mail_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="recovery-mail")
_mail_slots = BoundedSemaphore(12)


def normalize_email(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    email = value.strip().lower()
    if len(email) > 254 or len(email.split("@", 1)[0]) > 64 or not EMAIL_PATTERN.fullmatch(email):
        return None
    return email


def code_digest(value: object) -> str | None:
    code = value.strip() if isinstance(value, str) else ""
    if CODE_PATTERN.fullmatch(code):
        return hmac.new(current_app.config["SECRET_KEY"].encode(), code.upper().encode(), sha256).hexdigest()
    # Accept codes already sent before the short-code upgrade until they expire.
    return sha256(code.encode()).hexdigest() if LEGACY_CODE_PATTERN.fullmatch(code) else None


def generate_code() -> str:
    while True:
        code = "".join(choice(CODE_ALPHABET) for _ in range(6))
        if any(char.isalpha() for char in code) and any(char.isdigit() for char in code):
            return code


def recovery_display_name(user: User) -> str:
    return (user.student_name or user.username) if user.role == User.ROLE_STUDENT else user.username


def consume_code(user_id: int, email: str, digest: str, *, binding: bool) -> bool:
    """Consume once, or count a failed guess. The caller commits the transaction."""
    db.session.execute(update(User).where(User.id == user_id).values(password_hash=User.password_hash))
    address = AccountRecovery.pending_email if binding else AccountRecovery.email
    expires = AccountRecovery.binding_expires_at if binding else AccountRecovery.reset_expires_at
    attempts = AccountRecovery.binding_attempts if binding else AccountRecovery.reset_attempts
    stored_digest = AccountRecovery.binding_digest if binding else AccountRecovery.reset_digest
    scope = (AccountRecovery.user_id == user_id, address == email, expires > utc_now())
    attempted = db.session.execute(update(AccountRecovery).where(
        *scope, attempts < MAX_CODE_ATTEMPTS,
    ).values({attempts: attempts + 1}).execution_options(synchronize_session=False))
    if attempted.rowcount != 1:
        return False
    consumed = db.session.execute(update(AccountRecovery).where(
        *scope, stored_digest == digest,
    ).values({stored_digest: None, expires: None}).execution_options(synchronize_session=False))
    return consumed.rowcount == 1


def recovery_account_query(email: str, role: str, identifier: str):
    identity_column = User.student_name if role == User.ROLE_STUDENT else User.username
    return AccountRecovery.query.join(User, User.id == AccountRecovery.user_id).filter(
        AccountRecovery.email == email, User.role == role, identity_column == identifier,
    )


def operator_reset_password(role: str, identifier: str, password: str) -> User:
    query = User.query.filter_by(role=role)
    if role == User.ROLE_STUDENT:
        bound_ids = db.select(ClassRoster.matched_user_id).where(ClassRoster.student_id == identifier)
        query = query.filter(or_(User.student_id == identifier, User.id.in_(bound_ids)))
    else:
        query = query.filter_by(username=identifier)
    users = query.all()
    if len(users) != 1:
        raise ValueError("账号不存在或无法唯一匹配，请核对角色和账号编号。")
    user = users[0]
    # Follow the same lock order as online binding and reset operations.
    db.session.execute(update(User).where(User.id == user.id).values(password_hash=generate_password_hash(password)))
    recovery = db.session.get(AccountRecovery, user.id)
    if not recovery:
        recovery = AccountRecovery(user_id=user.id)
        db.session.add(recovery)
    recovery.password_reset_at = utc_now()
    recovery.pending_email = recovery.binding_digest = recovery.binding_expires_at = None
    recovery.reset_digest = recovery.reset_expires_at = None
    recovery.binding_attempts = recovery.reset_attempts = 0
    db.session.add(AuditLog(action="operator_password_reset", target_type="user", target_id=user.id,
                            payload_json={"method": "flask_cli"}))
    db.session.commit()
    return user


def issue_code(recovery: AccountRecovery, email: str, *, binding: bool) -> str | None:
    now = utc_now()
    code = generate_code()
    expires = now + CODE_LIFETIME
    expiry_column = AccountRecovery.binding_expires_at if binding else AccountRecovery.reset_expires_at
    statement = update(AccountRecovery).where(
        AccountRecovery.user_id == recovery.user_id,
        or_(expiry_column.is_(None), expiry_column <= expires - SEND_INTERVAL),
    )
    if binding:
        statement = statement.values(pending_email=email, binding_digest=code_digest(code), binding_expires_at=expires, binding_attempts=0)
    else:
        statement = statement.where(AccountRecovery.email == email).values(reset_digest=code_digest(code), reset_expires_at=expires, reset_attempts=0)
    if db.session.execute(statement.execution_options(synchronize_session=False)).rowcount != 1:
        db.session.rollback()
        return None
    db.session.commit()
    return code


def email_enabled() -> bool:
    config = current_app.config
    return bool(config["SMTP_HOST"] and normalize_email(config["SMTP_FROM"]) and config["SMTP_SECURITY"] in {"starttls", "ssl"})


def send_code(email: str, code: str, *, binding: bool, recipient_name: str) -> None:
    config = current_app.config
    message = build_recovery_email(email, code, recipient_name, binding=binding,
                                   valid_minutes=int(CODE_LIFETIME.total_seconds() / 60))
    context = ssl.create_default_context()
    host, port = config["SMTP_HOST"], config["SMTP_PORT"]
    smtp = (smtplib.SMTP_SSL(host, port, timeout=8, context=context) if config["SMTP_SECURITY"] == "ssl"
            else smtplib.SMTP(host, port, timeout=8))
    with smtp:
        if config["SMTP_SECURITY"] == "starttls":
            smtp.starttls(context=context)
        if config["SMTP_USERNAME"]:
            smtp.login(config["SMTP_USERNAME"], config["SMTP_PASSWORD"])
        smtp.send_message(message)


def _deliver_code(app: Flask, email: str, code: str, *, binding: bool, recipient_name: str) -> None:
    try:
        with app.app_context():
            send_code(email, code, binding=binding, recipient_name=recipient_name)
    except (OSError, ValueError) as exc:
        # SMTP errors may contain addresses or provider details.
        app.logger.warning("Recovery email delivery failed (%s)", type(exc).__name__)
    finally:
        _mail_slots.release()


def queue_code(email: str, code: str, *, binding: bool, recipient_name: str) -> bool:
    if not _mail_slots.acquire(blocking=False):
        return False
    _mail_executor.submit(_deliver_code, current_app._get_current_object(), email, code, binding=binding, recipient_name=recipient_name)
    return True
