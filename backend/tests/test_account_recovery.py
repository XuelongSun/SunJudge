from datetime import timedelta
from hashlib import sha256

import pytest

from app.extensions import db
from app.models import AccountRecovery, AuditLog, ClassRoster, Course, CourseClass, User, utc_now
from app.services.account_recovery import CODE_LIFETIME, SEND_INTERVAL, code_digest


BASE = "/api/auth/recovery"


@pytest.fixture()
def messages(app, monkeypatch):
    app.config.update(SMTP_HOST="smtp.example.test", SMTP_FROM="judge@example.test")
    outbox = []

    def queue_code(email, code, *, binding, recipient_name):
        outbox.append((email, code, binding, recipient_name))
        return True

    monkeypatch.setattr("app.routes.auth.queue_code", queue_code)
    return outbox


def test_recovery_requires_verified_email_and_consumes_reset_once(client, admin, messages):
    admin_id = User.query.filter_by(username="admin").one().id
    email = "admin@example.test"
    identity = {"role": "admin", "identifier": "admin", "email": email}
    creds = {"username": "admin", "password": "admin123"}
    login = "/api/auth/login"
    assert client.get(f"{BASE}/email").status_code == 401
    assert client.post(login, json=creds).status_code == 200
    assert client.get(f"{BASE}/email").json == {"email": None, "enabled": True}
    assert client.post(f"{BASE}/email/request", json={"email": email, "password": "wrong123"}).status_code == 403
    assert client.post(f"{BASE}/email/request", json={"email": email.upper(), "password": "admin123"}).status_code == 202
    assert client.post(f"{BASE}/email/request", json={"email": email, "password": "admin123"}).status_code == 429
    _, verification, binding, name = messages[0]
    assert binding and messages[0][0] == email
    assert name == "admin"
    assert len(verification) == 6 and verification.isalnum()
    assert db.session.get(AccountRecovery, admin_id).binding_digest == code_digest(verification)
    assert code_digest(verification) != sha256(verification.encode()).hexdigest()
    assert client.post(f"{BASE}/password/request", json=identity).status_code == 202
    assert len(messages) == 1
    assert client.post(f"{BASE}/email/confirm", json={"email": "other@example.test", "code": verification}).status_code == 400
    assert client.post(f"{BASE}/email/confirm", json={"email": email, "code": verification}).status_code == 200
    assert client.get(f"{BASE}/email").json["email"] == email
    assert "email" not in client.get("/api/auth/me").json["user"]

    legacy = client.application.test_client()
    with legacy.session_transaction() as session:
        session["_user_id"] = str(admin_id)
    with client.application.app_context():
        assert legacy.get("/api/auth/me").json["user"]["id"] == admin_id
    guest = client.application.test_client()
    known = guest.post(f"{BASE}/password/request", json=identity)
    unknown = guest.post(f"{BASE}/password/request", json={**identity, "email": "unknown@example.test"})
    repeated = guest.post(f"{BASE}/password/request", json=identity)
    assert (known.status_code, unknown.status_code, repeated.status_code) == (202, 202, 202)
    assert known.json == unknown.json == repeated.json
    assert len(messages) == 2
    reset = {**identity, "code": messages[-1][1], "password": "new-password"}
    assert guest.post(f"{BASE}/password/confirm", json=reset).status_code == 200
    assert guest.post(f"{BASE}/password/confirm", json=reset).status_code == 400
    for browser in (guest, client, legacy):
        with client.application.app_context():
            assert browser.get("/api/auth/me").json["user"] is None
    assert client.post(login, json=creds).status_code == 401
    assert client.post(login, json={**creds, "password": reset["password"]}).status_code == 200


def test_expired_codes_and_conflicting_address_preserve_existing_binding(client, admin, messages):
    admin_id = User.query.filter_by(username="admin").one().id
    teacher = User(username="teacher", role=User.ROLE_TEACHER, teacher_status=User.TEACHER_STATUS_APPROVED)
    teacher.set_password("teacher123")
    db.session.add(teacher)
    db.session.flush()
    taken, email = "taken@example.test", "old@example.test"
    db.session.add_all([AccountRecovery(user_id=teacher.id, email=taken), AccountRecovery(user_id=admin_id, email=email)])
    db.session.commit()
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert client.post(f"{BASE}/email/request", json={"email": taken, "password": "admin123"}).status_code == 202
    verify = {"email": taken, "code": messages[-1][1]}
    assert client.post(f"{BASE}/email/confirm", json=verify).status_code == 409
    recovery = db.session.get(AccountRecovery, admin_id)
    assert recovery.email == email
    recovery.binding_expires_at = utc_now() - timedelta(seconds=1)
    db.session.commit()
    assert client.post(f"{BASE}/email/confirm", json=verify).status_code == 400
    identity = {"role": "admin", "identifier": "admin", "email": email}
    assert client.post(f"{BASE}/password/request", json=identity).status_code == 202
    recovery.reset_expires_at = utc_now() - timedelta(seconds=1)
    db.session.commit()
    assert client.post(f"{BASE}/password/confirm", json={**identity, "code": messages[-1][1], "password": "new-password"}).status_code == 400
    assert db.session.get(User, admin_id).check_password("admin123")


@pytest.mark.parametrize("role, identifier", [("teacher", "teacher-name"), ("student", "测试学生")])
def test_password_recovery_matches_role_identity_and_verified_email(client, messages, role, identifier):
    user = User(username="teacher-name" if role == "teacher" else "old-test-nickname", role=role,
                student_name=identifier if role == "student" else None)
    user.set_password("old-password")
    db.session.add(user)
    db.session.flush()
    user_id = user.id
    identity = {"role": role, "identifier": identifier, "email": "owner@example.test"}
    # Existing accounts may have never configured an email, or only requested verification.
    for recovery in (None, AccountRecovery(user_id=user_id, pending_email=identity["email"])):
        if recovery:
            db.session.add(recovery)
            db.session.commit()
        response = client.post(f"{BASE}/password/request", json=identity)
        assert response.status_code == 202
        assert messages == []
        assert db.session.get(User, user_id).check_password("old-password")
    recovery.email = identity["email"]
    recovery.pending_email = None
    db.session.commit()
    wrong_inputs = [{**identity, "identifier": "另一个人"}, {**identity, "role": "admin"},
                    {**identity, "email": "attacker@example.test"}]
    if role == "student":
        wrong_inputs.append({**identity, "identifier": "old-test-nickname"})
        # The verified email selects the correct account when students have the same real name.
        other = User(username="another-student", role="student", student_name=identifier)
        other.set_password("other-password")
        db.session.add(other)
        db.session.commit()
    for payload in wrong_inputs:
        response = client.post(f"{BASE}/password/request", json=payload)
        assert response.status_code == 202 and messages == []
    valid = client.post(f"{BASE}/password/request", json={**identity, "identifier": f" {identifier} "})
    assert valid.json == response.json
    assert len(messages) == 1 and messages[0][0] == identity["email"]
    assert messages[0][3] == identifier
    code = messages[0][1]
    for payload in wrong_inputs:
        assert client.post(f"{BASE}/password/confirm", json={**payload, "code": code, "password": "new-password"}).status_code == 400
    assert db.session.get(User, user_id).check_password("old-password")
    assert client.post(f"{BASE}/password/confirm", json={**identity, "code": code, "password": "new-password"}).status_code == 200
    assert db.session.get(User, user_id).check_password("new-password")


@pytest.mark.parametrize("identity", [{}, {"role": "teacher", "identifier": ""},
                                   {"role": "student", "identifier": " "},
                                   {"role": [], "identifier": "Alice"},
                                   {"role": "student", "identifier": ["Alice"]}])
def test_password_recovery_requires_account_information(client, messages, identity):
    assert client.post(f"{BASE}/password/request", json={**identity, "email": "owner@example.test"}).status_code == 400
    assert messages == []


def test_operator_can_recover_unbound_legacy_account_and_invalidate_old_sessions(client, app):
    teacher = User(username="teacher", role="teacher")
    teacher.set_password("teacher123")
    student = User(username="OS-01", student_name="Alice", student_id="OS-01", role="student")
    student.set_password("old-password")
    db.session.add_all([teacher, student])
    db.session.flush()
    student_id = student.id
    course = Course(teacher_id=teacher.id, name="Demo", code="demo", semester="2026")
    db.session.add(course)
    db.session.flush()
    course_class = CourseClass(course_id=course.id, name="Next class", alias="NEXT", invite_code="NEXT")
    db.session.add(course_class)
    db.session.flush()
    db.session.add(ClassRoster(class_id=course_class.id, student_name="Alice", student_id="NEXT-03",
                               student_no="03", matched_user_id=student.id))
    db.session.commit()
    with app.app_context():
        assert client.post("/api/auth/login", json={"username": "OS-01", "password": "old-password"}).status_code == 200
    legacy = app.test_client()
    with legacy.session_transaction() as session:
        session["_user_id"] = str(student_id)
    runner = app.test_cli_runner()
    assert runner.invoke(args=["reset-password", "--role", "student", "Alice"], input="new-password\nnew-password\n").exit_code != 0
    result = runner.invoke(args=["reset-password", "--role", "student", "NEXT-03"], input="new-password\nnew-password\n")
    assert result.exit_code == 0, result.output
    assert "new-password" not in result.output
    recovery = db.session.get(AccountRecovery, student_id)
    assert recovery.email is None and recovery.password_reset_at
    assert AuditLog.query.filter_by(action="operator_password_reset", target_id=student_id).count() == 1
    for browser in (client, legacy):
        with app.app_context():
            assert browser.get("/api/auth/me").json["user"] is None
    with app.app_context():
        assert client.post("/api/auth/login", json={"username": "OS-01", "password": "new-password"}).status_code == 200


@pytest.mark.parametrize("role", ["teacher", "admin"])
def test_operator_recovery_preserves_verified_email_and_clears_pending_codes(app, role):
    user = User(username="staff-account", role=role, teacher_status="pending" if role == "teacher" else "none")
    user.set_password("old-password")
    db.session.add(user)
    db.session.flush()
    user_id = user.id
    db.session.add(AccountRecovery(user_id=user.id, email="owner@example.test", pending_email="new@example.test",
                                   binding_digest="a" * 64, binding_expires_at=utc_now() + timedelta(minutes=1),
                                   reset_digest="b" * 64, reset_expires_at=utc_now() + timedelta(minutes=1)))
    db.session.commit()
    result = app.test_cli_runner().invoke(args=["reset-password", "--role", role, "staff-account"], input="new-password\nnew-password\n")
    assert result.exit_code == 0, result.output
    db.session.expire_all()
    user = db.session.get(User, user_id)
    assert user.role == role and user.check_password("new-password")
    assert user.teacher_status == ("pending" if role == "teacher" else "none")
    recovery = db.session.get(AccountRecovery, user_id)
    assert recovery.email == "owner@example.test" and recovery.password_reset_at
    assert recovery.pending_email is recovery.binding_digest is recovery.binding_expires_at is None
    assert recovery.reset_digest is recovery.reset_expires_at is None


@pytest.mark.parametrize("binding", [True, False])
def test_short_code_limits_failed_attempts_and_resending_resets_the_counter(client, admin, messages, binding):
    admin_id = User.query.filter_by(username="admin").one().id
    email = "owner@example.test"
    identity = {"email": email, "role": "admin", "identifier": "admin"}
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    if binding:
        request_url, confirm_url = f"{BASE}/email/request", f"{BASE}/email/confirm"
        request_payload, confirmation = {"email": email, "password": "admin123"}, {"email": email}
    else:
        db.session.add(AccountRecovery(user_id=admin_id, email=email))
        db.session.commit()
        request_url, confirm_url = f"{BASE}/password/request", f"{BASE}/password/confirm"
        request_payload, confirmation = identity, {**identity, "password": "new-password"}
    assert client.post(request_url, json=request_payload).status_code == 202
    original = messages[-1][1]
    wrong = "A2B3C4" if original != "A2B3C4" else "Z9Y8X7"
    for _ in range(5):
        assert client.post(confirm_url, json={**confirmation, "code": wrong}).status_code == 400
    assert client.post(confirm_url, json={**confirmation, "code": original}).status_code == 400
    recovery = db.session.get(AccountRecovery, admin_id)
    assert getattr(recovery, "binding_attempts" if binding else "reset_attempts") == 5
    assert db.session.get(User, admin_id).check_password("admin123")
    setattr(recovery, "binding_expires_at" if binding else "reset_expires_at", utc_now() + CODE_LIFETIME - SEND_INTERVAL - timedelta(seconds=1))
    db.session.commit()
    assert client.post(request_url, json=request_payload).status_code == 202
    assert client.post(confirm_url, json={**confirmation, "code": messages[-1][1].lower()}).status_code == 200
    assert client.post(confirm_url, json={**confirmation, "code": messages[-1][1]}).status_code == 400


@pytest.mark.parametrize("binding", [True, False])
def test_legacy_code_sent_before_upgrade_remains_usable_until_expiry(client, admin, messages, binding):
    admin_id = User.query.filter_by(username="admin").one().id
    legacy = "aB-cD_12" * 4
    email = "owner@example.test"
    recovery = AccountRecovery(user_id=admin_id)
    if binding:
        recovery.pending_email = email
        recovery.binding_digest = sha256(legacy.encode()).hexdigest()
        recovery.binding_expires_at = utc_now() + timedelta(minutes=10)
    else:
        recovery.email = email
        recovery.reset_digest = sha256(legacy.encode()).hexdigest()
        recovery.reset_expires_at = utc_now() + timedelta(minutes=10)
    db.session.add(recovery)
    db.session.commit()
    client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    url = f"{BASE}/email/confirm" if binding else f"{BASE}/password/confirm"
    assert client.post(url, json={"email": email, "role": "admin", "identifier": "admin",
                                  "password": "new-password", "code": legacy}).status_code == 200
