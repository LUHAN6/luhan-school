import csv
import io
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .bulk_forms import ContactForm, ContactGroupForm, CampaignForm, TemplateForm, CSVImportForm
from .bulk_models import Contact, ContactGroup, Campaign, MessageLog, MessageTemplate
from .bulk_services import (
    _live_sending_enabled,
    eligible_contacts,
    prepare_and_send,
    send_campaign,
)
from .bulk_sync import sync_erp_contacts
from django.views.decorators.http import require_POST

def _staff_required(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _mask_destination(channel, destination):
    """Return a privacy-preserving recipient destination for preview screens."""
    value = (destination or "").strip()
    if not value:
        return "?"

    if channel == "sms":
        return "????" + value[-4:] if len(value) > 4 else "????"

    local, separator, domain = value.partition("@")
    if separator:
        visible = local[:1] if len(local) <= 2 else local[:2]
        return f"{visible}***@{domain}"

    return f"{value[:2]}***" if len(value) > 2 else "***"

def staff_required(view):
    @login_required
    def wrapped(request, *args, **kwargs):
        if not _staff_required(request.user):
            messages.error(request, "You do not have permission to manage messaging.")
            return redirect("messaging:bulk_dashboard")
        return view(request, *args, **kwargs)
    return wrapped

@staff_required
def dashboard(request):
    campaigns = Campaign.objects.all()[:6]
    context = {
        "contacts_count": Contact.objects.filter(is_active=True).count(),
        "groups_count": ContactGroup.objects.count(),
        "campaigns_count": Campaign.objects.count(),
        "sent_count": MessageLog.objects.filter(status=MessageLog.Status.SENT).count(),
        "failed_count": MessageLog.objects.filter(status=MessageLog.Status.FAILED).count(),
        "skipped_count": MessageLog.objects.filter(status=MessageLog.Status.SKIPPED).count(),
        "recent_campaigns": campaigns,
        "recent_logs": list(MessageLog.objects.select_related("campaign", "contact")[:8]),
    }
    for log in context["recent_logs"]:
        log.display_destination = _mask_destination(
            log.channel, log.destination
        )

    return render(request, "messaging/bulk/dashboard.html", context)

@staff_required
def contact_list(request):
    q = request.GET.get("q", "").strip()
    contacts = Contact.objects.all().prefetch_related("groups")
    if q:
        contacts = contacts.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q))
    page = Paginator(contacts, 25).get_page(request.GET.get("page"))
    return render(request, "messaging/bulk/contact_list.html", {"page": page, "q": q})

@staff_required
@require_POST
def contact_sync(request):
    result = sync_erp_contacts()
    messages.success(
        request,
        "ERP contact synchronization completed. "
        f"Parents: {result['created']} created, "
        f"{result['updated']} updated, "
        f"{result['grouped']} newly grouped; "
        f"{result['total']} in Parents / Guardians. "
        f"Staff: {result['staff_created']} created, "
        f"{result['staff_updated']} updated, "
        f"{result['staff_grouped']} newly grouped; "
        f"{result['staff_total']} in Staff. "
        "Consent and opt-out settings were preserved for existing contacts. "
        "No messages were sent."
    )
    return redirect("messaging:bulk_contacts")


@staff_required
def contact_create(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Contact saved.")
        return redirect("messaging:bulk_contacts")
    return render(request, "messaging/bulk/form.html", {"form": form, "title": "Add contact", "back_url": "messaging:bulk_contacts"})

@staff_required
def contact_edit(request, pk):
    obj = get_object_or_404(Contact, pk=pk)
    form = ContactForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Contact updated.")
        return redirect("messaging:bulk_contacts")
    return render(request, "messaging/bulk/form.html", {"form": form, "title": "Edit contact", "back_url": "messaging:bulk_contacts"})

@staff_required
def contact_delete(request, pk):
    obj = get_object_or_404(Contact, pk=pk)
    if request.method == "POST":
        obj.delete()
        messages.success(request, "Contact deleted.")
        return redirect("messaging:bulk_contacts")
    return render(request, "messaging/bulk/confirm_delete.html", {"object": obj, "title": "Delete contact"})

@staff_required
def contact_import(request):
    form = CSVImportForm(request.POST or None, request.FILES or None)
    imported = 0
    if request.method == "POST" and form.is_valid():
        reader = csv.DictReader(io.StringIO(form.cleaned_data["file"].read().decode("utf-8-sig")))
        for row in reader:
            first = (row.get("first_name") or "").strip()
            if not first:
                continue

            phone = (row.get("phone") or "").strip()
            email = (row.get("email") or "").strip().lower()

            defaults = {
                "first_name": first,
                "last_name": (row.get("last_name") or "").strip(),
                "phone": phone,
                "email": email,
                "source": Contact.Source.CSV,
                "is_active": True,
            }

            # Missing, blank, or unrecognized consent values must never
            # erase existing consent or grant consent to a new contact.
            true_values = {"1", "true", "yes", "y"}
            false_values = {"0", "false", "no", "n"}

            for field_name in ("sms_consent", "email_consent"):
                raw_value = row.get(field_name)
                value = (raw_value or "").strip().lower()

                if value in true_values:
                    defaults[field_name] = True
                elif value in false_values:
                    defaults[field_name] = False
                # Otherwise omit this field from defaults:
                # existing values remain unchanged and new contacts
                # receive the model's default False.

            contact, _ = Contact.objects.update_or_create(
                email=email or None,
                phone=phone or None,
                defaults=defaults,
            )

            group_names = [
                name.strip()
                for name in (row.get("groups") or "").split(";")
                if name.strip()
            ]
            for name in group_names:
                group, _ = ContactGroup.objects.get_or_create(name=name)
                contact.groups.add(group)

            imported += 1
        messages.success(request, f"Imported or updated {imported} contacts.")
        return redirect("messaging:bulk_contacts")
    return render(request, "messaging/bulk/form.html", {"form": form, "title": "Import contacts from CSV", "back_url": "messaging:bulk_contacts"})

@staff_required
def contact_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="school_contacts.csv"'
    writer = csv.writer(response)
    writer.writerow(["first_name", "last_name", "phone", "email", "groups", "sms_consent", "email_consent", "opted_out", "is_active"])
    for c in Contact.objects.prefetch_related("groups"):
        writer.writerow([c.first_name, c.last_name, c.phone, c.email, ";".join(g.name for g in c.groups.all()), c.sms_consent, c.email_consent, c.opted_out, c.is_active])
    return response

@staff_required
def group_list(request):
    groups = ContactGroup.objects.annotate(contact_count=Count("contacts")).all()
    return render(request, "messaging/bulk/group_list.html", {"groups": groups})

@staff_required
def group_create(request):
    form = ContactGroupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Contact group created.")
        return redirect("messaging:bulk_groups")
    return render(request, "messaging/bulk/form.html", {"form": form, "title": "Create contact group", "back_url": "messaging:bulk_groups"})

@staff_required
def campaign_list(request):
    campaigns = Campaign.objects.all()
    return render(request, "messaging/bulk/campaign_list.html", {"campaigns": campaigns})

@staff_required
def campaign_create(request):
    allowed_audiences = {choice[0] for choice in Campaign.Audience.choices}
    requested_audience = request.GET.get("audience", "").strip().lower()
    initial = {}
    if requested_audience in allowed_audiences:
        initial["audience"] = requested_audience
    form = CampaignForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.created_by = request.user

        # Creation never dispatches messages or activates the scheduler.
        campaign.status = Campaign.Status.DRAFT
        campaign.save()
        form.save_m2m()

        messages.success(
            request,
            "Campaign saved as a draft. Review its recipients before sending or scheduling.",
        )
        return redirect("messaging:bulk_campaign_preview", pk=campaign.pk)

    return render(
        request,
        "messaging/bulk/form.html",
        {
            "form": form,
            "title": "Create campaign",
            "back_url": "messaging:bulk_campaigns",
            "campaign_form": True,
        },
    )


@staff_required
def campaign_preview(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    contacts = eligible_contacts(campaign)
    contact_count = contacts.count()

    channels = (
        ["sms", "email"]
        if campaign.channel == Campaign.Channel.BOTH
        else [campaign.channel]
    )

    stats = []
    for channel in channels:
        if channel == "sms":
            ready = contacts.filter(phone__gt="", sms_consent=True).count()
            missing_destination = contacts.filter(phone="").count()
            missing_consent = contacts.filter(
                phone__gt="", sms_consent=False
            ).count()
            label = "SMS"
        else:
            ready = contacts.filter(email__gt="", email_consent=True).count()
            missing_destination = contacts.filter(email="").count()
            missing_consent = contacts.filter(
                email__gt="", email_consent=False
            ).count()
            label = "Email"

        stats.append({
            "label": label,
            "ready": ready,
            "missing_destination": missing_destination,
            "missing_consent": missing_consent,
        })

    preview_rows = []
    for contact in contacts[:30]:
        for channel in channels:
            destination = contact.phone if channel == "sms" else contact.email
            consent = (
                contact.sms_consent if channel == "sms"
                else contact.email_consent
            )
            if not destination:
                status = "Missing destination"
            elif not consent:
                status = "Consent not recorded"
            else:
                status = "Ready"
            preview_rows.append({
                "name": contact.full_name,
                "channel": channel.upper(),
                "destination": _mask_destination(channel, destination),
                "status": status,
                "ready": bool(destination and consent),
            })

    if request.method == "POST":
        action = request.POST.get("action", "")
        if (
            action in ("send", "retry_failed", "schedule")
            and not _live_sending_enabled()
        ):
            messages.warning(
                request,
                "Live messaging is disabled. Sending, retrying, and "
                "scheduling are blocked; no campaign records were changed.",
            )
            return redirect("messaging:bulk_campaign_preview", pk=pk)


        if campaign.status == Campaign.Status.CANCELLED:
            messages.error(request, "A cancelled campaign cannot be dispatched.")
            return redirect("messaging:bulk_campaign_preview", pk=pk)

        if action == "schedule":
            if not campaign.scheduled_at or campaign.scheduled_at <= timezone.now():
                messages.error(
                    request,
                    "Choose a future scheduled date and time before confirming scheduling.",
                )
                return redirect("messaging:bulk_campaign_preview", pk=pk)

            if campaign.status not in (
                Campaign.Status.DRAFT,
                Campaign.Status.SCHEDULED,
            ):
                messages.error(
                    request,
                    "Only a draft or already scheduled campaign can be scheduled here.",
                )
                return redirect("messaging:bulk_campaign_preview", pk=pk)

            campaign.status = Campaign.Status.SCHEDULED
            campaign.save(update_fields=["status"])
            messages.success(
                request,
                "Campaign scheduled. Delivery depends on the scheduled-campaign command and configured safety controls.",
            )
            return redirect("messaging:bulk_campaign_detail", pk=pk)

        if action == "send":
            if campaign.status not in (
                Campaign.Status.DRAFT,
                Campaign.Status.SCHEDULED,
            ):
                messages.error(
                    request,
                    "This campaign is not eligible for a new send attempt. Review its status.",
                )
                return redirect("messaging:bulk_campaign_preview", pk=pk)

            campaign.scheduled_at = None
            campaign.status = Campaign.Status.DRAFT
            campaign.save(update_fields=["scheduled_at", "status"])

            # The service's existing live-send gate remains authoritative.
            prepare_and_send(campaign)
            messages.info(
                request,
                "Send attempt processed. Check campaign status and delivery logs; live delivery remains subject to the existing safety gate.",
            )
            return redirect("messaging:bulk_campaign_detail", pk=pk)

        if action == "retry_failed":
            if not campaign.failed_count:
                messages.error(request, "There are no failed messages to retry.")
                return redirect("messaging:bulk_campaign_preview", pk=pk)

            send_campaign(campaign, retry_failed=True)
            messages.info(
                request,
                "Retry attempt processed. Review the delivery log for the result.",
            )
            return redirect("messaging:bulk_campaign_detail", pk=pk)

        messages.error(request, "Choose a valid campaign action.")
        return redirect("messaging:bulk_campaign_preview", pk=pk)

    return render(
        request,
        "messaging/bulk/campaign_preview.html",
        {
            "campaign": campaign,
        "live_sending_enabled": _live_sending_enabled(),
            "contact_count": contact_count,
            "stats": stats,
            "preview_rows": preview_rows,
            "preview_limit": min(contact_count, 30),
        },
    )


@staff_required
def campaign_detail(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    logs = Paginator(
        campaign.logs.select_related("contact"), 50
    ).get_page(request.GET.get("page"))

    # Mask personal destinations before rendering the detail page.
    # Keep the original destination unchanged for backend processing.
    for log in logs.object_list:
        log.display_destination = _mask_destination(
            log.channel, log.destination
        )

    return render(
        request,
        "messaging/bulk/campaign_detail.html",
        {"campaign": campaign, "logs": logs},
    )


@staff_required
@require_POST
def campaign_send(request, pk):
    # Keep the legacy URL, but do not allow it to bypass the preview workflow.
    get_object_or_404(Campaign, pk=pk)
    messages.info(request, "Review the campaign preview before choosing an action.")
    return redirect("messaging:bulk_campaign_preview", pk=pk)


@staff_required
@require_POST
def campaign_retry(request, pk):
    # Retries are now confirmed from the preview page.
    get_object_or_404(Campaign, pk=pk)
    messages.info(request, "Review the campaign preview before retrying failed messages.")
    return redirect("messaging:bulk_campaign_preview", pk=pk)


@staff_required
@require_POST
def campaign_cancel(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    if campaign.status in (
        Campaign.Status.DRAFT,
        Campaign.Status.SCHEDULED,
        Campaign.Status.QUEUED,
    ):
        campaign.status = Campaign.Status.CANCELLED
        campaign.save(update_fields=["status"])
        messages.success(request, "Campaign cancelled.")
    return redirect("messaging:bulk_campaign_detail", pk=pk)


@staff_required
def template_list(request):
    return render(request, "messaging/bulk/template_list.html", {"templates": MessageTemplate.objects.all()})

@staff_required
def template_create(request):
    form = TemplateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Template saved.")
        return redirect("messaging:bulk_templates")
    return render(request, "messaging/bulk/form.html", {"form": form, "title": "Create message template", "back_url": "messaging:bulk_templates"})

@staff_required
def logs_list(request):
    qs = MessageLog.objects.select_related("campaign", "contact")
    status = request.GET.get("status")
    channel = request.GET.get("channel")
    if status:
        qs = qs.filter(status=status)
    if channel:
        qs = qs.filter(channel=channel)
    page = Paginator(qs, 50).get_page(request.GET.get("page"))

    for log in page.object_list:
        log.display_destination = _mask_destination(
            log.channel, log.destination
        )

    return render(
        request,
        "messaging/bulk/logs.html",
        {"page": page, "status": status, "channel": channel},
    )
