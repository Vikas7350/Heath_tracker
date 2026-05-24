import re
import secrets
import smtplib
import threading
from datetime import timedelta
from email.mime.text import MIMEText

from flask import current_app, session

from db import mongo, now_utc


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def valid_email(email):
    return bool(EMAIL_RE.match((email or "").strip().lower()))


def generate_otp():
    return f"{secrets.randbelow(900000) + 100000}"


def save_otp(email, purpose, otp):
    expires_at = now_utc() + timedelta(minutes=5)
    current_app.logger.debug("OTP generated for %s (purpose=%s)", email, purpose)
    mongo.db.otp_verification.delete_many({"email": email, "purpose": purpose})
    mongo.db.otp_verification.insert_one({
        "email": email,
        "purpose": purpose,
        "otp": otp,
        "expires_at": expires_at,
        "created_at": now_utc(),
        "request_count": 1,
    })
    return expires_at


def verify_otp(email, purpose, otp):
    user_otp = (otp or "").strip()
    current_app.logger.debug("OTP entered for %s (purpose=%s)", email, purpose)
    record = mongo.db.otp_verification.find_one({
        "email": email,
        "purpose": purpose,
        "otp": user_otp,
        "expires_at": {"$gt": now_utc()},
    })
    if not record:
        return False
    mongo.db.otp_verification.delete_many({"email": email, "purpose": purpose})
    current_app.logger.debug("OTP verified for %s (purpose=%s)", email, purpose)
    return True


def can_request_otp(email, purpose):
    record = mongo.db.otp_verification.find_one({"email": email, "purpose": purpose})
    if not record:
        return True
    created_at = record.get("created_at")
    if not created_at:
        return True
    if (now_utc() - created_at.replace(tzinfo=now_utc().tzinfo)).total_seconds() < 60:
        return False
    return True


def send_otp_email(email, otp, purpose="verification"):
    subject = "Your HealthAI OTP"
    body = f"Your HealthAI {purpose} OTP is {otp}. It expires in 5 minutes."
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = current_app.config.get("MAIL_USERNAME", "")
    msg["To"] = email

    server = current_app.config.get("MAIL_SERVER")
    username = current_app.config.get("MAIL_USERNAME")
    password = current_app.config.get("MAIL_PASSWORD")
    port = int(current_app.config.get("MAIL_PORT", 587))
    
    if not server or not username or not password:
        current_app.logger.warning("Mail is not configured. Skipping send for %s", email)
        return False

    try:
        # Add timeout to prevent hanging connections on Render
        # Timeout set to 10 seconds for SMTP connection and operations
        with smtplib.SMTP(server, port, timeout=10) as smtp:
            smtp.set_debuglevel(0)
            if current_app.config.get("MAIL_USE_TLS", True):
                smtp.starttls(timeout=10)
            smtp.login(username, password)
            smtp.send_message(msg)
        current_app.logger.debug("OTP email sent successfully to %s", email)
        return True
    except smtplib.SMTPAuthenticationError as e:
        current_app.logger.error("SMTP authentication failed for %s. Check MAIL_USERNAME and MAIL_PASSWORD: %s", email, e)
        return False
    except smtplib.SMTPException as e:
        current_app.logger.error("SMTP error while sending to %s: %s", email, e)
        return False
    except TimeoutError as e:
        current_app.logger.error("SMTP connection timeout for %s (server: %s:%s): %s", email, server, port, e)
        return False
    except Exception as e:
        current_app.logger.exception("Failed to send OTP email to %s: %s", email, e)
        return False


def send_email_async(app, email, otp, purpose="verification"):
    with app.app_context():
        try:
            send_otp_email(email, otp, purpose)
        except Exception as e:
            app.logger.exception("Background email error: %s", e)


def send_otp_email_async(email, otp, purpose="verification"):
    """
    Send OTP email in a background thread to avoid blocking the request.
    This prevents SMTP timeouts from causing worker process to hang.
    """
    app = current_app._get_current_object()

    # Start email sending in background thread (daemon thread)
    thread = threading.Thread(
        target=send_email_async,
        args=(app, email, otp, purpose),
        daemon=True,
    )
    thread.start()


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf(token):
    return token and token == session.get("_csrf_token")


def to_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
