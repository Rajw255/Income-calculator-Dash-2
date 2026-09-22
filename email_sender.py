"""
EMAIL SENDER
=============
Sends the submitted scenario's PDF by email via SMTP. Credentials come
from Streamlit secrets (st.secrets["smtp"]) — never hardcoded — so this
works the same locally (.streamlit/secrets.toml) and on Streamlit
Community Cloud (App settings > Secrets).

Expected secrets.toml shape (Gmail example — see README for full setup):

    [smtp]
    host = "smtp.gmail.com"
    port = 587
    user = "youraccount@gmail.com"
    password = "16-character app password"
    from_email = "youraccount@gmail.com"
    from_name = "Wealthy Partner Desk"

Any SMTP provider works the same way — Outlook/Office365, SendGrid's
SMTP relay, Brevo, Resend, Amazon SES, a company mail server — just
change host/port/user/password.
"""

import re
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(addr: str) -> bool:
    return bool(addr) and bool(EMAIL_RE.match(addr.strip()))


def get_smtp_config(secrets):
    """secrets is st.secrets (or a plain dict for testing). Returns the
    smtp config dict, or None if not configured."""
    try:
        cfg = dict(secrets["smtp"])
    except Exception:
        return None
    required = ["host", "port", "user", "password", "from_email"]
    if not all(k in cfg for k in required):
        return None
    return cfg


def send_email_with_pdf(secrets, to_emails, subject: str, body: str,
                         pdf_bytes: bytes, filename: str = "income_projection.pdf") -> tuple:
    """to_emails: a single address or a list of addresses.
    Returns (success: bool, message: str)."""
    if isinstance(to_emails, str):
        to_emails = [to_emails]
    to_emails = [e.strip() for e in to_emails if e and e.strip()]

    if not to_emails:
        return False, "Enter at least one recipient email address."
    bad = [e for e in to_emails if not is_valid_email(e)]
    if bad:
        return False, f"'{bad[0]}' doesn't look like a valid email address."

    cfg = get_smtp_config(secrets)
    if cfg is None:
        return False, ("Email isn't configured yet. Add an [smtp] block to this app's Secrets "
                        "(App settings > Secrets on Streamlit Cloud) — see README for the exact format.")

    msg = MIMEMultipart()
    msg["From"] = f"{cfg.get('from_name', '')} <{cfg['from_email']}>".strip()
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    part = MIMEApplication(pdf_bytes, Name=filename)
    part["Content-Disposition"] = f'attachment; filename="{filename}"'
    msg.attach(part)

    try:
        with smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=20) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.sendmail(cfg["from_email"], to_emails, msg.as_string())
        return True, f"Email sent to {', '.join(to_emails)}."
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed — check the username/password (or app password) in Secrets."
    except Exception as e:
        return False, f"Couldn't send the email: {e}"
