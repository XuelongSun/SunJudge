from datetime import datetime, timedelta, timezone
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid

from flask import current_app, render_template

from ..models import utc_now


def build_recovery_email(email: str, code: str, recipient_name: str, *, binding: bool,
                         valid_minutes: int, sent_at: datetime | None = None) -> EmailMessage:
    sent_at = sent_at or utc_now()
    date_label = sent_at.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M (UTC+08:00)")
    if binding:
        title_zh, title_en = "绑定找回邮箱", "Bind your recovery email"
        intro_zh = "请输入以下验证码，完成找回邮箱绑定。"
        intro_en = "Enter this code to bind your recovery email."
    else:
        title_zh, title_en = "重置你的密码", "Reset your password"
        intro_zh = "请输入以下验证码，继续重置你的密码。"
        intro_en = "Enter this code to reset your password."
    context = dict(recipient_name=recipient_name, code=code, date_label=date_label,
                   title_zh=title_zh, title_en=title_en, intro_zh=intro_zh, intro_en=intro_en,
                   valid_minutes=valid_minutes)
    message = EmailMessage()
    message["From"] = Address(display_name="Sunjudge", addr_spec=current_app.config["SMTP_FROM"])
    message["To"] = email
    message["Subject"] = f"SunJudge · {title_zh} / {title_en}"
    message["Date"] = format_datetime(sent_at)
    message["Message-ID"] = make_msgid(domain=current_app.config["SMTP_FROM"].rsplit("@", 1)[-1])
    message.set_content(
        f"{title_zh} / {title_en}\n\n"
        f"你好，{recipient_name}！ / Hi, {recipient_name}!\n{intro_zh}\n{intro_en}\n\n"
        f"验证码 / Code: {code}\n"
        f"{valid_minutes} 分钟有效，仅可使用一次。\nValid for {valid_minutes} minutes. Single use.\n\n"
        "请勿泄露验证码，非本人操作请忽略。\n"
        "Keep this code private. If you didn't request this, ignore this email.\n\n"
        f"Sunjudge\n{date_label}\n"
    )
    message.add_alternative(render_template("emails/account_recovery.html", **context), subtype="html")
    return message
