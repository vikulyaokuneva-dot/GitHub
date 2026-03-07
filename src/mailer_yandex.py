import os
import smtplib
from email.message import EmailMessage


def send_email_with_pdf(subject: str, body: str, pdf_path: str) -> None:
    smtp_user = os.environ["YANDEX_SMTP_USER"].strip()
    smtp_pass = os.environ["YANDEX_SMTP_APP_PASS"].strip().replace(" ", "")
    to_addr = os.environ["EMAIL_TO"].strip()

    if "@" not in smtp_user:
        raise RuntimeError("YANDEX_SMTP_USER must be a full email address like name@yandex.ru")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr
    msg.set_content(body)

    with open(pdf_path, "rb") as f:
        data = f.read()

    filename = pdf_path.split("/")[-1]
    msg.add_attachment(data, maintype="application", subtype="pdf", filename=filename)

    # Яндекс SMTP SSL
    host = os.environ.get("YANDEX_SMTP_HOST", "smtp.yandex.com")
    port = int(os.environ.get("YANDEX_SMTP_PORT", "465"))

    try:
        with smtplib.SMTP_SSL(host, port) as s:
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(
            "Yandex SMTP auth failed. Обычно причина: нужен пароль приложения (не основной пароль) "
            "или логин не совпадает с ящиком. Проверь YANDEX_SMTP_USER и YANDEX_SMTP_APP_PASS."
        ) from e
