import time

from django.conf import settings
from django.core import signing
from django.core.mail import send_mail


def build_verify_email_url(token):
    return settings.AUTH_VERIFY_EMAIL_URL_TEMPLATE.format(token=token)


def build_verify_email_token(user):
    return signing.dumps(
        {
            "user_id": user.pk,
            "exp": int(time.time()) + settings.AUTH_VERIFY_EMAIL_MAX_AGE_SECONDS,
        },
        salt=settings.AUTH_VERIFY_EMAIL_SALT,
    )


def load_verify_email_user_id(token):
    payload = signing.loads(token, salt=settings.AUTH_VERIFY_EMAIL_SALT)
    expires_at = payload["exp"]
    if expires_at < time.time():
        raise signing.SignatureExpired("Token expired.")
    return payload["user_id"]


def send_verification_email(user):
    token = build_verify_email_token(user)
    verification_url = build_verify_email_url(token)
    subject = "Verify your email"
    message = (
        "Welcome to Bravo.\n\n"
        "Verify your email by opening this link:\n"
        f"{verification_url}\n"
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
