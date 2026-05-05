from collections import Counter

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.jobs.models import Job
from apps.organization.models import Announcement, Organization

from .models import (
    Notification,
    NotificationDispatch,
    NotificationPreference,
    NotificationRecipient,
    NotificationTemplate,
)


USER_MODEL = get_user_model()


def get_or_create_preferences(user):
    preferences, _ = NotificationPreference.objects.get_or_create(user=user)
    return preferences


def render_template_content(template, payload):
    context = dict(payload or {})
    try:
        title = template.title_template.format_map(context)
        body = template.body_template.format_map(context)
    except (KeyError, ValueError, AttributeError):
        title = template.title_template
        body = template.body_template
    return title, body


def get_category_preference(preferences, category):
    if category == Notification.Category.CHAT:
        return preferences.chat_notifications
    if category == Notification.Category.MARKETING:
        return preferences.marketing_notifications
    return preferences.system_notifications


def resolve_target_users(target_type, target_uuid=None, users=None):
    if users is not None:
        return list(users)

    if target_type == Notification.TargetType.USER:
        return [USER_MODEL.objects.get(uuid=target_uuid)]

    if target_type == Notification.TargetType.ORGANIZATION:
        organization = Organization.objects.select_related("user").get(uuid=target_uuid)
        return [organization.user]

    if target_type == Notification.TargetType.BROADCAST:
        return list(
            USER_MODEL.objects.filter(
                is_active=True,
                status=USER_MODEL.Status.ACTIVE,
            ).order_by("id")
        )

    return []


def build_target_label(target_type, target_uuid=None, users=None):
    if target_type == Notification.TargetType.USER and users:
        user = users[0]
        return user.email

    if target_type == Notification.TargetType.ORGANIZATION and users:
        user = users[0]
        return getattr(getattr(user, "organization", None), "name", user.email)

    if target_type == Notification.TargetType.BROADCAST:
        return "All active users"

    return ""


def record_dispatch(recipient, channel, status_value, error_message=""):
    dispatch = NotificationDispatch.objects.create(
        recipient=recipient,
        channel=channel,
        status=status_value,
        delivered_at=timezone.now() if status_value == NotificationDispatch.Status.DELIVERED else None,
        error_message=error_message,
    )
    return dispatch


def send_email_notification(recipient):
    try:
        send_mail(
            subject=recipient.notification.title,
            message=recipient.notification.body,
            from_email=None,
            recipient_list=[recipient.user.email],
            fail_silently=False,
        )
        recipient.email_status = NotificationRecipient.DeliveryStatus.DELIVERED
        recipient.save(update_fields=["email_status", "updated_at"])
        record_dispatch(
            recipient,
            NotificationDispatch.Channel.EMAIL,
            NotificationDispatch.Status.DELIVERED,
        )
    except Exception as exc:
        recipient.email_status = NotificationRecipient.DeliveryStatus.FAILED
        recipient.save(update_fields=["email_status", "updated_at"])
        record_dispatch(
            recipient,
            NotificationDispatch.Channel.EMAIL,
            NotificationDispatch.Status.FAILED,
            error_message=str(exc),
        )


def create_recipient(notification, user, channels, preferences):
    category_enabled = get_category_preference(preferences, notification.category)
    wants_in_app = Notification.Channel.IN_APP in channels
    wants_email = Notification.Channel.EMAIL in channels
    wants_push = Notification.Channel.PUSH in channels

    recipient = NotificationRecipient.objects.create(
        notification=notification,
        user=user,
        in_app_enabled=wants_in_app and preferences.in_app_enabled and category_enabled,
        email_enabled=wants_email and preferences.email_enabled and category_enabled,
        push_enabled=wants_push and preferences.push_enabled and category_enabled,
        delivered_at=timezone.now(),
        email_status=(
            NotificationRecipient.DeliveryStatus.PENDING
            if wants_email and preferences.email_enabled and category_enabled
            else NotificationRecipient.DeliveryStatus.SKIPPED
        ),
        push_status=(
            NotificationRecipient.DeliveryStatus.NOT_CONFIGURED
            if wants_push and preferences.push_enabled and category_enabled
            else NotificationRecipient.DeliveryStatus.SKIPPED
        ),
    )
    record_dispatch(
        recipient,
        NotificationDispatch.Channel.IN_APP,
        NotificationDispatch.Status.DELIVERED,
    )
    if wants_email:
        if recipient.email_enabled and user.email:
            send_email_notification(recipient)
        else:
            record_dispatch(
                recipient,
                NotificationDispatch.Channel.EMAIL,
                NotificationDispatch.Status.SKIPPED,
            )
    if wants_push:
        record_dispatch(
            recipient,
            NotificationDispatch.Channel.PUSH,
            NotificationDispatch.Status.NOT_CONFIGURED,
        )
    return recipient


@transaction.atomic
def emit_notification(
    *,
    title,
    body,
    origin,
    category,
    severity=Notification.Severity.MEDIUM,
    target_type=Notification.TargetType.USER,
    target_uuid=None,
    users=None,
    requested_channels=None,
    payload=None,
    action_url="",
    created_by=None,
    template_key=None,
):
    template = None
    channels = list(requested_channels or [Notification.Channel.IN_APP])

    if template_key:
        template = NotificationTemplate.objects.filter(key=template_key, is_active=True).first()
        if template is not None:
            if not title or not body:
                title, body = render_template_content(template, payload or {})
            if not requested_channels:
                channels = list(template.default_channels or [Notification.Channel.IN_APP])

    target_users = resolve_target_users(target_type, target_uuid=target_uuid, users=users)
    notification = Notification.objects.create(
        template=template,
        created_by=created_by,
        origin=origin,
        category=category,
        severity=severity,
        target_type=target_type,
        target_uuid=target_uuid,
        target_label=build_target_label(target_type, target_uuid=target_uuid, users=target_users),
        title=title,
        body=body,
        action_url=action_url,
        requested_channels=channels,
        payload=payload or {},
    )

    for user in target_users:
        preferences = get_or_create_preferences(user)
        create_recipient(notification, user, channels, preferences)

    return notification


def emit_status_change_notification(instance, old_status, new_status, *, actor=None, reason_text=""):
    if old_status == new_status:
        return None

    if isinstance(instance, USER_MODEL):
        users = [instance]
        title = "Actualizacion de cuenta"
        body = f"Tu cuenta ha cambiado de estado: {old_status} -> {new_status}."
        target_type = Notification.TargetType.USER
        target_uuid = instance.uuid
        payload = {"user_uuid": str(instance.uuid)}
    elif isinstance(instance, Organization):
        users = [instance.user]
        title = "Actualizacion de organizacion"
        body = f"La organizacion {instance.name} ha cambiado de estado: {old_status} -> {new_status}."
        target_type = Notification.TargetType.ORGANIZATION
        target_uuid = instance.uuid
        payload = {"organization_uuid": str(instance.uuid)}
    elif isinstance(instance, Announcement):
        users = [instance.organization.user]
        title = "Actualizacion de anuncio"
        body = f"El anuncio {instance.name} ha cambiado de estado: {old_status} -> {new_status}."
        target_type = Notification.TargetType.ORGANIZATION
        target_uuid = instance.organization.uuid
        payload = {"announcement_uuid": str(instance.uuid)}
    elif isinstance(instance, Job):
        provider_user = instance.announcement.organization.user
        users = [instance.user, provider_user]
        unique_users = []
        seen_ids = set()
        for user in users:
            if user.id in seen_ids:
                continue
            seen_ids.add(user.id)
            unique_users.append(user)
        users = unique_users
        title = "Actualizacion de job"
        body = f"El job {instance.uuid} ha cambiado de estado: {old_status} -> {new_status}."
        target_type = Notification.TargetType.BROADCAST
        target_uuid = None
        payload = {"job_uuid": str(instance.uuid)}
    else:
        return None

    return emit_notification(
        title=title,
        body=body if not reason_text else f"{body} Motivo: {reason_text}",
        origin=Notification.Origin.MANAGEMENT,
        category=Notification.Category.SYSTEM,
        severity=Notification.Severity.MEDIUM,
        target_type=target_type,
        target_uuid=target_uuid,
        users=users,
        requested_channels=[Notification.Channel.IN_APP, Notification.Channel.EMAIL],
        payload=payload,
        created_by=actor,
    )


def emit_job_chat_message_notification(message):
    job = message.job_chat.job
    participants = [job.user, job.announcement.organization.user]
    recipients = []
    seen_ids = set()
    for user in participants:
        if user.id == message.user_id or user.id in seen_ids:
            continue
        seen_ids.add(user.id)
        recipients.append(user)

    if not recipients:
        return None

    preview = message.content[:160]
    return emit_notification(
        title="Nuevo mensaje en chat",
        body=preview,
        origin=Notification.Origin.JOB_CHAT,
        category=Notification.Category.CHAT,
        severity=Notification.Severity.LOW,
        target_type=Notification.TargetType.BROADCAST if len(recipients) > 1 else Notification.TargetType.USER,
        users=recipients,
        requested_channels=[Notification.Channel.IN_APP, Notification.Channel.PUSH],
        payload={
            "job_uuid": str(job.uuid),
            "message_uuid": str(message.uuid),
        },
        action_url=f"/jobs/{job.uuid}",
        created_by=message.user,
    )


def summarize_notification(notification):
    recipient_count = notification.recipients.count()
    read_count = notification.recipients.exclude(read_at__isnull=True).count()
    email_counts = Counter(notification.recipients.values_list("email_status", flat=True))
    push_counts = Counter(notification.recipients.values_list("push_status", flat=True))
    return {
        "recipient_count": recipient_count,
        "read_count": read_count,
        "email_status_counts": dict(email_counts),
        "push_status_counts": dict(push_counts),
    }
