import os
import socket
import smtplib
from email.header import Header
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict


def normalize_email_failure_reason(exc: BaseException) -> str:
    text = str(exc or "")
    winerror = getattr(exc, "winerror", None)
    if winerror == 10013 or "WinError 10013" in text:
        return "SMTP connection blocked by runtime environment"
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "SMTP authentication failed"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "SMTP connection timeout"
    if isinstance(exc, smtplib.SMTPConnectError):
        return "SMTP connection failed"
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return "SMTP server disconnected unexpectedly"
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "SMTP recipients refused by server"
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "SMTP sender address refused by server"
    if isinstance(exc, smtplib.SMTPDataError):
        return "SMTP send failed"
    if isinstance(exc, smtplib.SMTPException):
        return "SMTP protocol error"
    if isinstance(exc, OSError):
        return "SMTP connection failed"
    return "SMTP transport failed"


class EmailDeliveryError(RuntimeError):
    def __init__(self, *, stage: str, cause: BaseException):
        self.email_stage = str(stage or "unknown")
        self.raw_reason = str(cause or "")
        self.failure_reason_normalized = normalize_email_failure_reason(cause)
        message = (
            f"EMAIL DELIVERY FAILED [{self.email_stage}]: "
            f"{self.failure_reason_normalized} ({self.raw_reason})"
        )
        super().__init__(message)
        self.__cause__ = cause


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


def send_email_with_pdf(subject: str, body: str, pdf_path: str) -> Dict[str, Any]:
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

    host = os.environ.get("YANDEX_SMTP_HOST", "smtp.yandex.com").strip() or "smtp.yandex.com"
    port = int(os.environ.get("YANDEX_SMTP_PORT", "465"))
    security_mode = str(os.environ.get("YANDEX_SMTP_SECURITY", "ssl") or "ssl").strip().lower()
    if security_mode not in {"ssl", "starttls"}:
        security_mode = "ssl"
    timeout_seconds = float(os.environ.get("YANDEX_SMTP_TIMEOUT_SECONDS", "30") or "30")

    print(f"[mail][smtp] host={host} port={port} security={security_mode}")
    client: smtplib.SMTP | smtplib.SMTP_SSL | None = None
    try:
        print("[mail][smtp] stage=connect started")
        if security_mode == "ssl":
            client = smtplib.SMTP_SSL(host, port, timeout=timeout_seconds)
        else:
            client = smtplib.SMTP(host, port, timeout=timeout_seconds)
            client.ehlo()
            print("[mail][smtp] stage=connect starttls")
            client.starttls()
            client.ehlo()
        print("[mail][smtp] stage=connect ok")
    except (smtplib.SMTPException, OSError, TimeoutError, socket.timeout) as exc:
        raise EmailDeliveryError(stage="connect", cause=exc) from exc

    try:
        print("[mail][smtp] stage=login started")
        client.login(smtp_user, smtp_pass)
        print("[mail][smtp] stage=login ok")
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPException, OSError, TimeoutError, socket.timeout) as exc:
        raise EmailDeliveryError(stage="login", cause=exc) from exc

    try:
        print("[mail][smtp] stage=send started")
        client.send_message(msg)
        print("[mail][smtp] stage=send ok")
    except (smtplib.SMTPException, OSError, TimeoutError, socket.timeout) as exc:
        raise EmailDeliveryError(stage="send", cause=exc) from exc
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                pass

    return {
        "email_stage": "send",
        "email_transport_status": "success",
        "email_failure_reason_normalized": "",
        "smtp_host": host,
        "smtp_port": port,
        "smtp_security": security_mode,
    }

