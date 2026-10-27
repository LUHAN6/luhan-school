import re
from collections import defaultdict

from django.db import transaction

from .bulk_models import Contact, ContactGroup


def _normal(value):
    return re.sub(r"\s+", " ", (value or "").strip()).casefold()


def _split_name(value):
    parts = (value or "").strip().split()
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


def _contact_for(name, phone, email="", external_id=""):
    first, last = _split_name(name)

    if external_id:
        contact = Contact.objects.filter(external_id=external_id).first()
        if contact:
            return contact, False

    # Match only ERP-managed contacts by name and phone.
    # A shared phone alone is not enough to merge two families.
    # Parent matching must never absorb an explicitly classified staff
    # or student contact merely because name and phone happen to match.
    candidates = Contact.objects.filter(
        source=Contact.Source.ERP,
        audience__in=[
            Contact.Audience.PARENT,
            Contact.Audience.UNCLASSIFIED,
        ],
    )
    if phone:
        candidates = candidates.filter(phone=phone)
    else:
        candidates = candidates.filter(phone="")
    candidates = candidates.filter(
        first_name__iexact=first,
        last_name__iexact=last,
    )
    contact = candidates.order_by("id").first()
    if contact:
        return contact, False

    contact = Contact(
        first_name=first or "Parent",
        last_name=last,
        phone=phone or "",
        email=email or "",
        external_id=external_id or "",
        source=Contact.Source.ERP,
        is_active=True,
        sms_consent=False,
        email_consent=False,
        opted_out=False,
    )
    contact.save()
    return contact, True


def _update_contact(contact, name, phone, email, external_id=""):
    first, last = _split_name(name)
    changed = []

    # Keep existing non-empty details unless ERP has a non-empty replacement.
    if first and contact.first_name != first:
        contact.first_name = first
        changed.append("first_name")
    if last and contact.last_name != last:
        contact.last_name = last
        changed.append("last_name")
    if phone and contact.phone != phone:
        contact.phone = phone
        changed.append("phone")
    if email and not contact.email:
        contact.email = email
        changed.append("email")
    if external_id and (
        not contact.external_id
        or contact.external_id.startswith(("student-parent:", "admission:"))
    ):
        if contact.external_id != external_id:
            contact.external_id = external_id
            changed.append("external_id")

    if changed:
        contact.save(update_fields=list(dict.fromkeys(changed + ["updated_at"])))
    return bool(changed)



def _classify_parent_contact(contact):
    """Classify only unclassified contacts; never overwrite an explicit type."""
    if contact.audience == Contact.Audience.UNCLASSIFIED:
        contact.audience = Contact.Audience.PARENT
        contact.save(update_fields=["audience", "updated_at"])
        return True
    return False

@transaction.atomic
def sync_erp_contacts():
    from parents.models import Parent
    from students.models import Student, OnlineApplication
    from hr_payroll.models import Employee

    group, _ = ContactGroup.objects.get_or_create(
        name="Parents / Guardians",
        defaults={"description": "Parent and guardian contacts synchronised from school records."},
    )
    staff_group, _ = ContactGroup.objects.get_or_create(
        name="Staff",
        defaults={"description": "Employee contacts synchronised from HR and Payroll."},
    )

    created = 0
    updated = 0
    linked = 0
    staff_created = 0
    staff_updated = 0
    staff_linked = 0

    # Consolidate duplicate Parent records only when both name and phone match.
    grouped_parents = defaultdict(list)
    for parent in Parent.objects.prefetch_related("children").order_by("id"):
        key = (_normal(parent.full_name), _normal(parent.phone))
        if key[0] and key[1]:
            grouped_parents[key].append(parent)
        else:
            grouped_parents[(key[0], key[1] + f"|parent:{parent.pk}")].append(parent)

    for parent_group in grouped_parents.values():
        parent = parent_group[0]
        parent_ids = [p.pk for p in parent_group]
        external_id = f"parent:{min(parent_ids)}"
        emails = [p.email.strip().lower() for p in parent_group if p.email and p.email.strip()]
        email = emails[0] if emails else ""
        contact, was_created = _contact_for(
            parent.full_name, parent.phone, email, external_id
        )
        if was_created:
            created += 1
        elif _update_contact(contact, parent.full_name, parent.phone, email, external_id):
            updated += 1
        _classify_parent_contact(contact)
        before = contact.groups.filter(pk=group.pk).exists()
        contact.groups.add(group)
        if not before:
            linked += 1

    # Use student admission parent fields when no Parent account is linked.
    for student in Student.objects.all().iterator():
        if student.parents.exists():
            continue
        name = (student.parent_name or "").strip()
        phone = (student.parent_phone or "").strip()
        if not name or not phone:
            continue
        external_id = f"student-parent:{student.pk}"
        contact, was_created = _contact_for(name, phone, "", external_id)
        if was_created:
            created += 1
        elif _update_contact(contact, name, phone, "", external_id):
            updated += 1
        _classify_parent_contact(contact)
        before = contact.groups.filter(pk=group.pk).exists()
        contact.groups.add(group)
        if not before:
            linked += 1

    # Admitted applications may have parent email addresses missing from Parent.
    for application in OnlineApplication.objects.filter(status="Admitted").iterator():
        name = (application.parent_name or "").strip()
        phone = (application.parent_phone or "").strip()
        email = (application.parent_email or "").strip().lower()
        if not name or not (phone or email):
            continue

        # First look for a matching ERP contact by name and phone.
        contact = None
        if phone:
            first, last = _split_name(name)
            contact = Contact.objects.filter(
                source=Contact.Source.ERP,
                phone=phone,
                first_name__iexact=first,
                last_name__iexact=last,
            ).order_by("id").first()

        if contact:
            if _update_contact(contact, name, phone, email):
                updated += 1
        else:
            external_id = f"admission:{application.application_no}"
            contact, was_created = _contact_for(name, phone, email, external_id)
            if was_created:
                created += 1
            elif _update_contact(contact, name, phone, email, external_id):
                updated += 1

        _classify_parent_contact(contact)
        before = contact.groups.filter(pk=group.pk).exists()
        contact.groups.add(group)
        if not before:
            linked += 1

    # Synchronize staff using the stable HR employee number.
    # Never match staff to parent contacts by a shared name or phone number.
    # Existing consent and opt-out values are deliberately not modified.
    for employee in Employee.objects.all().iterator():
        employee_number = (employee.employee_number or "").strip()
        full_name = (employee.full_name or "").strip()

        if not employee_number or not full_name:
            continue

        external_id = f"employee:{employee_number}"
        phone = (employee.phone or "").strip()
        email = (employee.email or "").strip().lower()

        contact = Contact.objects.filter(
            source=Contact.Source.ERP,
            external_id=external_id,
        ).first()

        # Keep contacts for employees who are on leave, but don't treat
        # suspended or departed employees as eligible active recipients.
        employment_status = (employee.employment_status or "").upper()
        contact_is_active = (
            employee.is_active
            and employment_status in ("ACTIVE", "ON_LEAVE")
        )

        if contact is None:
            contact = Contact.objects.create(
                first_name=full_name.split()[0],
                last_name=" ".join(full_name.split()[1:]),
                phone=phone,
                email=email,
                external_id=external_id,
                audience=Contact.Audience.STAFF,
                source=Contact.Source.ERP,
                is_active=contact_is_active,
                sms_consent=False,
                email_consent=False,
                opted_out=False,
            )
            staff_created += 1
        else:
            changed = []

            name_parts = full_name.split()
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:])

            if contact.first_name != first_name:
                contact.first_name = first_name
                changed.append("first_name")

            if contact.last_name != last_name:
                contact.last_name = last_name
                changed.append("last_name")

            # Refresh contact details only when HR has supplied a value.
            if phone and contact.phone != phone:
                contact.phone = phone
                changed.append("phone")

            if email and contact.email != email:
                contact.email = email
                changed.append("email")

            if contact.audience != Contact.Audience.STAFF:
                contact.audience = Contact.Audience.STAFF
                changed.append("audience")

            if contact.is_active != contact_is_active:
                contact.is_active = contact_is_active
                changed.append("is_active")

            if changed:
                contact.save(
                    update_fields=list(dict.fromkeys(changed + ["updated_at"]))
                )
                staff_updated += 1

        was_linked = contact.groups.filter(pk=staff_group.pk).exists()
        contact.groups.add(staff_group)
        if not was_linked:
            staff_linked += 1

    return {
        # Preserve the existing parent-sync result keys.
        "created": created,
        "updated": updated,
        "grouped": linked,
        "total": Contact.objects.filter(groups=group).distinct().count(),

        # Additional staff-sync results.
        "staff_created": staff_created,
        "staff_updated": staff_updated,
        "staff_grouped": staff_linked,
        "staff_total": Contact.objects.filter(
            groups=staff_group
        ).distinct().count(),
    }
