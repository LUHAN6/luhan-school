import logging
import os
import re

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .bulk_models import Campaign, Contact, MessageLog

logger = logging.getLogger("messaging")


def _live_sending_enabled():
    return os.getenv("MESSAGING_LIVE_SEND_ENABLED", "").strip().lower() in (
        "1", "true", "yes", "on"
    )


def render_template(text, contact):
    values = {
        "first_name": getattr(contact, "first_name", "") or "",
        "last_name": getattr(contact, "last_name", "") or "",
        "full_name": getattr(contact, "full_name", "") or "",
        "school_name": os.getenv("SCHOOL_NAME", "Luhan School"),
    }

    def replace(match):
        key = match.group(1).strip()
        return values.get(key, match.group(0))

    return re.sub(r"{{\s*([a-zA-Z_]+)\s*}}", replace, text or "")


def eligible_contacts(campaign):
    qs = Contact.objects.filter(is_active=True, opted_out=False)

    audience = getattr(campaign, "audience", Campaign.Audience.GROUPS)

    if audience == Campaign.Audience.INDIVIDUAL:
        if not campaign.individual_contact_id:
            return qs.none()
        return qs.filter(pk=campaign.individual_contact_id)

    if audience == Campaign.Audience.PARENTS:
        return qs.filter(audience=Contact.Audience.PARENT)

    if audience == Campaign.Audience.STUDENTS:
        return qs.filter(audience=Contact.Audience.STUDENT)

    if audience == Campaign.Audience.STAFF:
        return qs.filter(audience=Contact.Audience.STAFF)

    if audience == Campaign.Audience.EVERYONE:
        return qs.filter(
            audience__in=[
                Contact.Audience.PARENT,
                Contact.Audience.STUDENT,
                Contact.Audience.STAFF,
            ]
        )

    # Compatibility: campaigns created before audience targeting keep their
    # original all_contacts / contact-group behaviour.
    if not campaign.all_contacts:
        qs = qs.filter(groups__in=campaign.groups.all()).distinct()

    return qs


def _send_sms(destination, body):
    backend = os.getenv("MESSAGING_SMS_BACKEND", "console").strip().lower()

    if backend == "console":
        logger.info("SMS simulation only; no message was sent.")
        return {
            "ok": False,
            "simulated": True,
            "id": "",
            "error": "SIMULATION ONLY: no SMS was sent.",
        }

    if not _live_sending_enabled():
        return {
            "ok": False,
            "blocked": True,
            "id": "",
            "error": (
                "LIVE SENDING DISABLED: set MESSAGING_LIVE_SEND_ENABLED=true "
                "only after completing provider and consent checks."
            ),
        }

    if backend == "africastalking":
        try:
            import requests
        except ImportError:
            return {
                "ok": False,
                "error": "Install requests to use Africa's Talking.",
            }

        username = os.getenv("AFRICASTALKING_USERNAME", "").strip()
        api_key = os.getenv("AFRICASTALKING_API_KEY", "").strip()
        sender = os.getenv("AFRICASTALKING_SENDER_ID", "").strip()

        if not username or not api_key:
            return {
                "ok": False,
                "error": "Africa's Talking credentials are missing.",
            }

        payload = {
            "username": username,
            "to": destination,
            "message": body,
        }
        if sender:
            payload["from"] = sender

        try:
            at_environment = os.getenv(
                "AFRICASTALKING_ENVIRONMENT", "sandbox"
            ).strip().lower()

            if at_environment == "sandbox":
                endpoint = (
                    "https://api.sandbox.africastalking.com/version1/messaging"
                )
            elif at_environment == "live":
                endpoint = (
                    "https://api.africastalking.com/version1/messaging"
                )
            else:
                return {
                    "ok": False,
                    "error": (
                        "Invalid AFRICASTALKING_ENVIRONMENT; "
                        "use sandbox or live."
                    ),
                }

            response = requests.post(
                endpoint,
                data=payload,
                headers={
                    "apiKey": api_key,
                    "Accept": "application/json",
                },
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            recipients = data.get("SMSMessageData", {}).get("Recipients", [])

            if recipients and str(recipients[0].get("statusCode", "")) in (
                "100", "101", "102", "200"
            ):
                return {
                    "ok": True,
                    "id": str(recipients[0].get("messageId", "")),
                }

            return {
                "ok": False,
                "error": str(
                    data.get("SMSMessageData", {}).get(
                        "Message", "Provider did not confirm acceptance."
                    )
                ),
            }
        except Exception:
            logger.exception("SMS provider request failed.")
            return {
                "ok": False,
                "error": "SMS provider request failed; inspect server logs.",
            }

    return {
        "ok": False,
        "error": f"Unknown SMS backend: {backend}",
    }


def _send_email(destination, subject, body):
    backend = os.getenv("MESSAGING_EMAIL_BACKEND", "console").strip().lower()

    if backend == "console":
        logger.info("Email simulation only; no message was sent.")
        return {
            "ok": False,
            "simulated": True,
            "id": "",
            "error": "SIMULATION ONLY: no email was sent.",
        }

    if not _live_sending_enabled():
        return {
            "ok": False,
            "blocked": True,
            "id": "",
            "error": (
                "LIVE SENDING DISABLED: real email delivery requires "
                "MESSAGING_LIVE_SEND_ENABLED=true."
            ),
        }

    if backend == "django":
        try:
            count = send_mail(
                subject,
                body,
                getattr(settings, "DEFAULT_FROM_EMAIL", None),
                [destination],
                fail_silently=False,
            )
            return {
                "ok": count == 1,
                "id": "django-mail" if count == 1 else "",
                "error": (
                    "" if count == 1
                    else "Email backend did not accept the message."
                ),
            }
        except Exception:
            logger.exception("Email provider request failed.")
            return {
                "ok": False,
                "error": "Email provider request failed; inspect server logs.",
            }

    return {
        "ok": False,
        "error": f"Unknown email backend: {backend}",
    }


def create_logs(campaign):
    # Never rebuild or replace a campaign's existing delivery history.
    existing_count = campaign.logs.count()
    if existing_count:
        return existing_count

    contacts = eligible_contacts(campaign)
    logs = []
    channels = (
        ["sms", "email"]
        if campaign.channel == Campaign.Channel.BOTH
        else [campaign.channel]
    )

    for contact in contacts.iterator():
        for channel in channels:
            destination = contact.phone if channel == "sms" else contact.email
            consent = (
                contact.sms_consent
                if channel == "sms"
                else contact.email_consent
            )

            if not destination or not consent:
                continue

            body = render_template(campaign.message, contact)
            subject = (
                render_template(campaign.subject, contact)
                if campaign.subject
                else ""
            )

            logs.append(
                MessageLog(
                    campaign=campaign,
                    contact=contact,
                    channel=channel,
                    destination=destination,
                    subject=subject,
                    rendered_message=body,
                )
            )

            if len(logs) >= 500:
                MessageLog.objects.bulk_create(logs)
                logs = []

    if logs:
        MessageLog.objects.bulk_create(logs)

    return campaign.logs.count()


def _current_contact_for_log(log):
    contact = getattr(log, "contact", None)
    contact_id = getattr(log, "contact_id", None)

    # Reload saved contacts so recent opt-outs, consent changes, and
    # destination changes are respected at delivery time.
    if contact_id:
        return Contact.objects.filter(pk=contact_id).first()

    # Supports isolated unit tests that use unsaved contact stand-ins.
    return contact


def _skip_log(log, reason):
    log.status = MessageLog.Status.SKIPPED
    log.provider_message_id = ""
    log.sent_at = None
    log.error_message = reason
    log.save(
        update_fields=[
            "status",
            "provider_message_id",
            "sent_at",
            "error_message",
        ]
    )


def send_campaign(campaign, retry_failed=False):
    if not _live_sending_enabled():
        logger.warning(
            "Campaign dispatch blocked because live sending is disabled."
        )
        return campaign

    if campaign.status == Campaign.Status.CANCELLED:
        return campaign

    if campaign.status in (
        Campaign.Status.COMPLETED,
        Campaign.Status.SIMULATED,
    ) and not retry_failed:
        return campaign

    if campaign.status == Campaign.Status.FAILED and not retry_failed:
        return campaign

    campaign.status = Campaign.Status.SENDING
    campaign.completed_at = None
    if not campaign.started_at:
        campaign.started_at = timezone.now()

    campaign.save(update_fields=["status", "started_at", "completed_at"])

    if retry_failed:
        qs = campaign.logs.filter(status=MessageLog.Status.FAILED)
    else:
        qs = campaign.logs.filter(status=MessageLog.Status.PENDING)

    for log in qs.select_related("contact").iterator():
        contact = _current_contact_for_log(log)

        if contact is None:
            _skip_log(log, "Skipped: contact record no longer exists.")
            continue

        if not contact.is_active:
            _skip_log(log, "Skipped: contact is inactive.")
            continue

        if contact.opted_out:
            _skip_log(log, "Skipped: contact has opted out.")
            continue

        if log.channel == "sms":
            if not contact.sms_consent:
                _skip_log(log, "Skipped: SMS consent is not recorded.")
                continue
            destination = (contact.phone or "").strip()
        else:
            if not contact.email_consent:
                _skip_log(log, "Skipped: email consent is not recorded.")
                continue
            destination = (contact.email or "").strip()

        if not destination:
            _skip_log(log, "Skipped: the current destination is missing.")
            continue

        # Use the latest saved destination rather than a stale snapshot.
        log.destination = destination
        log.attempts += 1

        if log.channel == "sms":
            result = _send_sms(destination, log.rendered_message)
        else:
            result = _send_email(
                destination, log.subject, log.rendered_message
            )

        if result.get("simulated") or result.get("blocked"):
            log.status = MessageLog.Status.SKIPPED
            log.provider_message_id = ""
            log.sent_at = None
            log.error_message = result.get(
                "error", "Delivery was blocked; no message was sent."
            )
        elif result.get("ok"):
            # Provider acceptance does not prove final device delivery.
            log.status = MessageLog.Status.SENT
            log.provider_message_id = result.get("id", "")
            log.sent_at = timezone.now()
            log.error_message = ""
        else:
            log.status = MessageLog.Status.FAILED
            log.provider_message_id = ""
            log.sent_at = None
            log.error_message = result.get(
                "error", "Unknown provider error."
            )

        log.save(
            update_fields=[
                "destination",
                "attempts",
                "status",
                "provider_message_id",
                "sent_at",
                "error_message",
            ]
        )

    campaign.sent_count = campaign.logs.filter(
        status=MessageLog.Status.SENT
    ).count()
    campaign.failed_count = campaign.logs.filter(
        status=MessageLog.Status.FAILED
    ).count()
    campaign.skipped_count = campaign.logs.filter(
        status=MessageLog.Status.SKIPPED
    ).count()
    pending = campaign.logs.filter(
        status=MessageLog.Status.PENDING
    ).exists()
    campaign.total_recipients = campaign.logs.count()

    if pending:
        campaign.status = Campaign.Status.SENDING
    elif campaign.failed_count and not campaign.sent_count:
        campaign.status = Campaign.Status.FAILED
    elif (
        campaign.skipped_count
        and not campaign.sent_count
        and not campaign.failed_count
    ):
        campaign.status = Campaign.Status.SIMULATED
    else:
        campaign.status = Campaign.Status.COMPLETED

    if not pending:
        campaign.completed_at = timezone.now()

    campaign.save(
        update_fields=[
            "sent_count",
            "failed_count",
            "skipped_count",
            "status",
            "completed_at",
            "total_recipients",
        ]
    )
    return campaign


def prepare_and_send(campaign):
    if not _live_sending_enabled():
        logger.warning(
            "Campaign preparation blocked because live sending is disabled."
        )
        return campaign

    # Never allow the normal send action to restart a terminal campaign.
    if campaign.status in (
        Campaign.Status.CANCELLED,
        Campaign.Status.COMPLETED,
        Campaign.Status.SIMULATED,
        Campaign.Status.FAILED,
    ):
        return campaign

    # Preserve any logs already prepared for this campaign.
    if campaign.logs.exists():
        campaign.total_recipients = campaign.logs.count()
    else:
        campaign.total_recipients = create_logs(campaign)

    campaign.save(update_fields=["total_recipients"])

    if not campaign.total_recipients:
        campaign.status = Campaign.Status.FAILED
        note = (
            "No eligible recipients: check active contacts, destinations, "
            "group membership, and recorded channel consent."
        )
        if note not in campaign.notes:
            campaign.notes = f"{campaign.notes}\n{note}".strip()
        campaign.save(update_fields=["status", "notes"])
        return campaign

    return send_campaign(campaign)
