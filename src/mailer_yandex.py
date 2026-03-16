import os
import smtplib
from email.header import Header
from email.message import EmailMessage
from pathlib import Path


def build_email_message(
    *,
    subject: str,
    body: str,
    from_addr: str,
    to_addr: str,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> EmailMessage:
    msg = EmailMessage()
    # RFC-compliant encoded-word header for non-ASCII subjects.
    msg["Subject"] = str(Header(str(subject or ""), "utf-8"))
    msg["From"] = str(from_addr or "").strip()
    msg["To"] = str(to_addr or "").strip()
    msg.set_content(str(body or ""), subtype="plain", charset="utf-8")
    msg.add_attachment(
        bytes(pdf_bytes or b""),
        maintype="application",
        subtype="pdf",
        filename=str(pdf_filename or "report.pdf"),
    )
    return msg


def send_email_with_pdf(subject: str, body: str, pdf_path: str) -> None:
    smtp_user = os.environ["YANDEX_SMTP_USER"].strip()
    smtp_pass = os.environ["YANDEX_SMTP_APP_PASS"].strip().replace(" ", "")
    to_addr = os.environ["EMAIL_TO"].strip()

    if "@" not in smtp_user:
        raise RuntimeError("YANDEX_SMTP_USER must be a full email address like name@yandex.ru")

    with open(pdf_path, "rb") as f:
        data = f.read()

    filename = Path(pdf_path).name
    msg = build_email_message(
        subject=subject,
        body=body,
        from_addr=smtp_user,
        to_addr=to_addr,
        pdf_bytes=data,
        pdf_filename=filename,
    )

    host = os.environ.get("YANDEX_SMTP_HOST", "smtp.yandex.com")
    port = int(os.environ.get("YANDEX_SMTP_PORT", "465"))

    try:
        with smtplib.SMTP_SSL(host, port) as s:
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError(
            "EMAIL DELIVERY FAILED: Yandex SMTP auth failed. Usually this means app password is required "
            "(not your mailbox password), or YANDEX_SMTP_USER does not match the mailbox."
        ) from e
    except (smtplib.SMTPException, OSError, TimeoutError) as e:
        raise RuntimeError(f"EMAIL DELIVERY FAILED: {e}") from e

