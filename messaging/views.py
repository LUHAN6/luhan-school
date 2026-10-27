from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.utils import timezone

from .models import Message
from accounts.models import UserProfile
from accounts.views import user_has_role_permission
from parents.models import Parent
from students.models import Student


# =========================================================
# ROLE / PERMISSION HELPERS
# =========================================================

def is_admin_user(user):
    return user.is_staff or user.is_superuser


def is_teaching_staff(user):
    """
    A STAFF user is teaching staff when their linked HR employee
    has a corresponding timetable Teacher record.

    We use a subquery instead of traversing the reverse OneToOne
    relation through UserProfile.employee, which is not supported
    reliably by Django in this lookup path.
    """
    if not user.is_authenticated:
        return False

    try:
        from timetable.models import TimetableTeacher

        profile = UserProfile.objects.filter(
            user=user,
            role="STAFF",
            employee__isnull=False,
        ).first()

        if not profile or not profile.employee_id:
            return False

        return TimetableTeacher.objects.filter(
            employee_id=profile.employee_id
        ).exists()

    except Exception:
        return False


def is_support_staff(user):
    """
    A STAFF user is support/non-teaching staff when they have an
    HR employee record but no corresponding timetable Teacher record.
    """
    if not user.is_authenticated:
        return False

    try:
        from timetable.models import TimetableTeacher

        profile = UserProfile.objects.filter(
            user=user,
            role="STAFF",
            employee__isnull=False,
        ).first()

        if not profile or not profile.employee_id:
            return False

        return not TimetableTeacher.objects.filter(
            employee_id=profile.employee_id
        ).exists()

    except Exception:
        return False


def can_access_staff_messaging(user):
    return (
        is_admin_user(user)
        or user_has_role_permission(
        user,
        "view_message",
        "messaging",
    )
    )


def can_compose_messages(user):
    return (
        is_admin_user(user)
        or (
            is_teaching_staff(user)
            and user_has_role_permission(
            user,
            "add_message",
            "messaging",
        )
        )
    )


def requires_message_approval(user):
    return (
        is_teaching_staff(user)
        and not is_admin_user(user)
    )


def can_manage_message_approvals(user):
    return is_admin_user(user)


def can_reply_to_announcement(user, message):
    """
    Teaching and Support Staff may reply to approved
    announcement messages.

    They cannot create or manage announcements here.
    """
    return (
        (is_teaching_staff(user) or is_support_staff(user))
        and message.approval_status == "approved"
        and message.announcement_id is not None
    )


# Keep compatibility with the existing messaging system.
def is_staff_user(user):
    return is_admin_user(user)


# =========================================================
# MESSAGING DASHBOARD
# =========================================================

@login_required
def messaging_dashboard(request):

    if not can_access_staff_messaging(request.user):
        return redirect("messaging:portal_messages")

    received_messages = Message.objects.filter(
        recipient=request.user,
        approval_status="approved",
    ).select_related(
        "sender",
        "announcement",
    )

    sent_messages = Message.objects.filter(
        sender=request.user
    ).select_related(
        "recipient",
        "announcement",
    )

    unread_count = received_messages.filter(
        is_read=False
    ).count()

    pending_approval_count = 0

    if can_manage_message_approvals(request.user):
        pending_approval_count = Message.objects.filter(
            approval_status="pending"
        ).count()

    context = {
        "received_messages": received_messages,
        "sent_messages": sent_messages,
        "unread_count": unread_count,
        "pending_approval_count": pending_approval_count,
        "is_admin": is_admin_user(request.user),
        "is_teaching_staff": is_teaching_staff(request.user),
        "is_support_staff": is_support_staff(request.user),
        "can_compose": can_compose_messages(request.user),
    }

    return render(
        request,
        "messaging/messaging_dashboard.html",
        context,
    )


# =========================================================
# RECIPIENT LOOKUP
# =========================================================

@login_required
def compose_recipient_lookup(request):

    if not can_compose_messages(request.user):
        return JsonResponse(
            {"results": []},
            status=403,
        )

    query = request.GET.get(
        "q",
        "",
    ).strip()

    recipient_mode = request.GET.get(
        "mode",
        "learner",
    ).strip()

    if not query:
        return JsonResponse(
            {"results": []},
        )

    results = []

    # -----------------------------------------------------
    # PARENT ONLY
    # Search using learner admission number.
    # Return linked parent account(s) only.
    # -----------------------------------------------------

    if recipient_mode == "parent_only":

        students = (
            Student.objects
            .filter(
                admission_no__icontains=query,
            )
            .prefetch_related(
                "parents__user",
            )
            .order_by(
                "admission_no",
            )[:20]
        )

        for student in students:

            full_name = (
                f"{student.first_name} "
                f"{student.middle_name} "
                f"{student.last_name}"
            ).replace(
                "  ",
                " ",
            ).strip()

            for parent in student.parents.filter(
                user__is_active=True,
            ):

                results.append({
                    "id": parent.user.id,
                    "username": parent.user.username,
                    "number": student.admission_no,
                    "name": parent.full_name,
                    "type": "parent",
                    "label": (
                        f"{student.admission_no} - "
                        f"{full_name} -> "
                        f"{parent.full_name}"
                    ),
                })

        return JsonResponse({
            "results": results,
        })

    # -----------------------------------------------------
    # TEACHING STAFF
    #
    # Teaching Staff may message students/parents.
    # They cannot use individual staff recipients.
    # Admin may still see/use staff recipients.
    # -----------------------------------------------------

    if is_admin_user(request.user):

        profiles = (
            UserProfile.objects
            .filter(
                employee_number__icontains=query,
                user__is_active=True,
            )
            .select_related(
                "user",
                "employee",
            )
            .order_by(
                "employee_number",
            )[:20]
        )

        for profile in profiles:

            results.append({
                "id": profile.user.id,
                "username": profile.user.username,
                "number": profile.employee_number,
                "name": (
                    profile.user.get_full_name()
                    or profile.user.username
                ),
                "type": "staff",
                "label": (
                    f"{profile.employee_number} - "
                    f"{profile.user.get_full_name() or profile.user.username}"
                ),
            })

    # -----------------------------------------------------
    # LEARNER LOOKUP
    # -----------------------------------------------------

    students = (
        Student.objects
        .filter(
            admission_no__icontains=query,
            user_account__isnull=False,
            user_account__user__is_active=True,
        )
        .select_related(
            "user_account__user",
        )
        .order_by(
            "admission_no",
        )[:20]
    )

    for student in students:

        full_name = (
            f"{student.first_name} "
            f"{student.middle_name} "
            f"{student.last_name}"
        ).replace(
            "  ",
            " ",
        ).strip()

        results.append({
            "id": student.user_account.user.id,
            "username": student.user_account.user.username,
            "number": student.admission_no,
            "name": full_name,
            "type": "student",
            "label": (
                f"{student.admission_no} - "
                f"{full_name}"
            ),
        })

    return JsonResponse({
        "results": results,
    })


# =========================================================
# COMPOSE MESSAGE
# =========================================================

@login_required
def message_compose(request):

    if not can_compose_messages(request.user):
        messages.warning(
            request,
            "You are not allowed to compose a new message. "
            "Support Staff can reply to announcement messages only."
        )
        return redirect("messaging:messaging_dashboard")

    users = User.objects.filter(
        is_active=True
    ).exclude(
        id=request.user.id
    ).order_by(
        "username"
    )

    grade_options = (
        Student.objects
        .filter(
            user_account__isnull=False
        )
        .exclude(
            class_name=""
        )
        .values_list(
            "class_name",
            flat=True
        )
        .distinct()
        .order_by(
            "class_name"
        )
    )

    if request.method == "POST":

        recipient_type = request.POST.get(
            "recipient_type",
            "individual"
        )

        subject = request.POST.get(
            "subject",
            ""
        ).strip()

        message_text = request.POST.get(
            "message",
            ""
        ).strip()

        message_type = request.POST.get(
            "message_type",
            "general"
        )

        if not subject or not message_text:
            messages.warning(
                request,
                "Please provide both a subject and message."
            )
            return redirect(
                "messaging:compose"
            )

        recipients = User.objects.none()

        # =================================================
        # INDIVIDUAL
        # =================================================

        if recipient_type == "individual":

            recipient_id = request.POST.get(
                "recipient"
            )

            individual_mode = request.POST.get(
                "individual_recipient_mode",
                "learner",
            ).strip()

            if not recipient_id:
                messages.warning(
                    request,
                    "Please select an individual recipient."
                )
                return redirect(
                    "messaging:compose"
                )

            selected_recipient = User.objects.filter(
                id=recipient_id,
                is_active=True,
            ).exclude(
                id=request.user.id
            ).first()

            if not selected_recipient:
                messages.warning(
                    request,
                    "The selected recipient could not be found."
                )
                return redirect(
                    "messaging:compose"
                )

            # -------------------------------------------------
            # Teaching Staff may only individually message
            # learners or parents.
            # -------------------------------------------------

            if is_teaching_staff(request.user):

                selected_student = UserProfile.objects.filter(
                    user=selected_recipient,
                    student__isnull=False,
                ).select_related(
                    "student",
                ).first()

                selected_parent = Parent.objects.filter(
                    user=selected_recipient,
                ).first()

                if not selected_student and not selected_parent:
                    messages.warning(
                        request,
                        "Teaching Staff may only message students or parents."
                    )
                    return redirect(
                        "messaging:compose"
                    )

            recipient_ids = set()

            # -------------------------------------------------
            # LEARNER ONLY
            # -------------------------------------------------

            if individual_mode == "learner":

                selected_student = UserProfile.objects.filter(
                    user=selected_recipient,
                    student__isnull=False,
                ).select_related(
                    "student",
                ).first()

                if not selected_student:
                    messages.warning(
                        request,
                        "Learner Only requires a learner recipient."
                    )
                    return redirect(
                        "messaging:compose"
                    )

                recipient_ids.add(
                    selected_recipient.id
                )

            # -------------------------------------------------
            # LEARNER + PARENT
            # -------------------------------------------------

            elif individual_mode == "learner_parent":

                selected_student = UserProfile.objects.filter(
                    user=selected_recipient,
                    student__isnull=False,
                ).select_related(
                    "student",
                ).first()

                if not selected_student or not selected_student.student:
                    messages.warning(
                        request,
                        "Learner + Parent requires a learner recipient."
                    )
                    return redirect(
                        "messaging:compose"
                    )

                recipient_ids.add(
                    selected_recipient.id
                )

                parent_user_ids = (
                    selected_student.student.parents
                    .filter(
                        user__is_active=True,
                    )
                    .exclude(
                        user=request.user,
                    )
                    .values_list(
                        "user_id",
                        flat=True,
                    )
                )

                recipient_ids.update(
                    parent_user_ids
                )

            # -------------------------------------------------
            # PARENT ONLY
            #
            # The lookup returns the parent account based
            # on the learner admission number.
            # -------------------------------------------------

            elif individual_mode == "parent_only":

                selected_parent = Parent.objects.filter(
                    user=selected_recipient,
                ).first()

                if not selected_parent:
                    messages.warning(
                        request,
                        "Parent Only requires a parent recipient."
                    )
                    return redirect(
                        "messaging:compose"
                    )

                recipient_ids.add(
                    selected_recipient.id
                )

            else:

                messages.warning(
                    request,
                    "Please select a valid delivery option."
                )
                return redirect(
                    "messaging:compose"
                )

            recipients = User.objects.filter(
                id__in=recipient_ids,
                is_active=True,
            ).exclude(
                id=request.user.id
            )

        # =================================================
        # GROUP
        # =================================================

        elif recipient_type == "group":

            group_type = request.POST.get(
                "group_type"
            )

            # -------------------------------------------------
            # Teaching Staff:
            # allowed groups = Parents, Students, Grade/Class
            # -------------------------------------------------

            if is_teaching_staff(request.user):

                allowed_groups = {
                    "parents",
                    "students",
                    "grade",
                }

                if group_type not in allowed_groups:
                    messages.warning(
                        request,
                        "Teaching Staff may only message Parents, Students, or a Grade/Class."
                    )
                    return redirect(
                        "messaging:compose"
                    )

            # -------------------------------------------------
            # Admin: all groups
            # -------------------------------------------------

            if group_type == "teaching":

                if not is_admin_user(request.user):
                    messages.warning(
                        request,
                        "Only Admin can message the Teaching Staff group."
                    )
                    return redirect(
                        "messaging:compose"
                    )

                recipients = User.objects.filter(
                    is_active=True,
                    profile__employee__timetable_teacher__isnull=False,
                ).exclude(
                    id=request.user.id
                )

            elif group_type == "support":

                if not is_admin_user(request.user):
                    messages.warning(
                        request,
                        "Only Admin can message the Support Staff group."
                    )
                    return redirect(
                        "messaging:compose"
                    )

                recipients = User.objects.filter(
                    is_active=True,
                    profile__role="STAFF",
                    profile__employee__isnull=False,
                    profile__employee__timetable_teacher__isnull=True,
                ).exclude(
                    id=request.user.id
                )

            # AUDIENCE_REPAIR_20261018: administrator-only staff and school-wide groups
            elif group_type == "staff":

                if not is_admin_user(request.user):
                    messages.warning(
                        request,
                        "Only Admin can message all staff."
                    )
                    return redirect("messaging:compose")

                recipients = User.objects.filter(
                    is_active=True,
                    profile__employee__isnull=False,
                ).exclude(
                    id=request.user.id
                )

            elif group_type == "everyone":

                if not is_admin_user(request.user):
                    messages.warning(
                        request,
                        "Only Admin can send a message to everyone."
                    )
                    return redirect("messaging:compose")

                recipients = User.objects.filter(
                    is_active=True,
                ).filter(
                    Q(parent__isnull=False)
                    | Q(profile__student__isnull=False)
                    | Q(profile__employee__isnull=False)
                ).exclude(
                    id=request.user.id
                )

            elif group_type == "parents":

                recipients = User.objects.filter(
                    is_active=True,
                    parent__isnull=False,
                ).exclude(
                    id=request.user.id
                )

            elif group_type == "students":

                recipients = User.objects.filter(
                    is_active=True,
                    profile__student__isnull=False,
                ).exclude(
                    id=request.user.id
                )

            elif group_type == "grade":

                class_name = request.POST.get(
                    "class_name",
                    ""
                ).strip()

                if not class_name:
                    messages.warning(
                        request,
                        "Please select a grade/class."
                    )
                    return redirect(
                        "messaging:compose"
                    )

                recipients = User.objects.filter(
                    is_active=True,
                    profile__student__class_name=class_name,
                ).exclude(
                    id=request.user.id
                )

            else:

                messages.warning(
                    request,
                    "Please select a valid recipient group."
                )
                return redirect(
                    "messaging:compose"
                )

        else:

            messages.warning(
                request,
                "Please select a valid recipient type."
            )
            return redirect(
                "messaging:compose"
            )

        recipients = recipients.distinct()

        if not recipients.exists():
            messages.warning(
                request,
                "No active recipients were found for your selection."
            )
            return redirect(
                "messaging:compose"
            )

        recipient_count = recipients.count()

        # =================================================
        # APPROVAL
        # =================================================

        if requires_message_approval(request.user):

            approval_status = "pending"
            approval_message = (
                f"Message submitted for Admin approval "
                f"to {recipient_count} recipient(s)."
            )

        else:

            approval_status = "approved"
            approval_message = (
                f"Message sent successfully to "
                f"{recipient_count} recipient(s)."
            )

        Message.objects.bulk_create(
            [
                Message(
                    sender=request.user,
                    recipient=recipient,
                    subject=subject,
                    message=message_text,
                    message_type=message_type,
                    approval_status=approval_status,
                )
                for recipient in recipients
            ]
        )

        messages.success(
            request,
            approval_message,
        )

        # Stay on compose so the green success popup can
        # be displayed by the existing compose template.
        return redirect(
            "messaging:compose"
        )

    context = {
        "users": users,
        "message_types": Message.MESSAGE_TYPES,
        "grade_options": grade_options,
        "is_admin": is_admin_user(request.user),
        "is_teaching_staff": is_teaching_staff(request.user),
        "is_support_staff": is_support_staff(request.user),
        "requires_approval": requires_message_approval(request.user),
    }

    return render(
        request,
        "messaging/message_compose.html",
        context,
    )


# =========================================================
# MESSAGE DETAIL
# =========================================================

@login_required
def message_detail(request, message_id):

    message = get_object_or_404(
        Message.objects.select_related(
            "sender",
            "recipient",
            "announcement",
        ),
        id=message_id,
        recipient=request.user,
    )

    # Pending messages must never be visible to portal users.
    if (
        message.approval_status != "approved"
        and not can_access_staff_messaging(request.user)
    ):
        messages.warning(
            request,
            "This message is not available yet."
        )
        return redirect(
            "messaging:portal_messages"
        )

    if not message.is_read:
        message.is_read = True
        message.save(
            update_fields=["is_read"]
        )

    can_reply = False

    # -----------------------------------------------------
    # Teaching/Support can reply to approved announcements.
    # -----------------------------------------------------

    if can_reply_to_announcement(
        request.user,
        message,
    ):
        can_reply = True

    # -----------------------------------------------------
    # Portal users can still reply to approved school
    # messages sent by Admin/School accounts.
    # -----------------------------------------------------

    elif (
        not can_access_staff_messaging(request.user)
        and message.approval_status == "approved"
        and is_admin_user(message.sender)
    ):
        can_reply = True

    return render(
        request,
        "messaging/message_detail.html",
        {
            "message": message,
            "can_reply": can_reply,
            "is_admin": is_admin_user(request.user),
            "is_teaching_staff": is_teaching_staff(request.user),
            "is_support_staff": is_support_staff(request.user),
        },
    )


# =========================================================
# REPLY TO MESSAGE
# =========================================================

@login_required
def message_reply(request, message_id):

    original_message = get_object_or_404(
        Message.objects.select_related(
            "sender",
            "recipient",
            "announcement",
        ),
        id=message_id,
        recipient=request.user,
    )

    # Only approved messages may receive replies.
    if original_message.approval_status != "approved":
        messages.warning(
            request,
            "You cannot reply to a message that has not been approved."
        )
        return redirect(
            "messaging:message_detail",
            message_id=original_message.id,
        )

    # -----------------------------------------------------
    # Staff announcement reply
    # -----------------------------------------------------

    staff_announcement_reply = can_reply_to_announcement(
        request.user,
        original_message,
    )

    # -----------------------------------------------------
    # Portal reply to Admin/School message
    # -----------------------------------------------------

    portal_reply = (
        not can_access_staff_messaging(request.user)
        and is_admin_user(original_message.sender)
    )

    if not staff_announcement_reply and not portal_reply:
        messages.warning(
            request,
            "You are not allowed to reply to this message."
        )
        return redirect(
            "messaging:message_detail",
            message_id=original_message.id,
        )

    if request.method != "POST":
        return redirect(
            "messaging:message_detail",
            message_id=original_message.id,
        )

    reply_text = request.POST.get(
        "message",
        "",
    ).strip()

    if not reply_text:
        messages.warning(
            request,
            "Please write a message before sending your reply."
        )
        return redirect(
            "messaging:message_detail",
            message_id=original_message.id,
        )

    subject = original_message.subject

    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    Message.objects.create(
        sender=request.user,
        recipient=original_message.sender,
        subject=subject,
        message=reply_text,
        message_type=original_message.message_type,
        approval_status="approved",
        announcement=original_message.announcement,
    )

    messages.success(
        request,
        "Your reply has been sent successfully."
    )

    return redirect(
        "messaging:message_detail",
        message_id=original_message.id,
    )


# =========================================================
# SENT MESSAGE DETAIL
# =========================================================

@login_required
def sent_message_detail(request, message_id):

    message = get_object_or_404(
        Message.objects.select_related(
            "sender",
            "recipient",
            "announcement",
        ),
        id=message_id,
        sender=request.user,
    )

    return render(
        request,
        "messaging/message_detail.html",
        {
            "message": message,
            "can_reply": False,
            "is_admin": is_admin_user(request.user),
            "is_teaching_staff": is_teaching_staff(request.user),
            "is_support_staff": is_support_staff(request.user),
        },
    )


# =========================================================
# PORTAL RECEIVED MESSAGES
# =========================================================

@login_required
def portal_messages(request):

    messages_received = Message.objects.filter(
        recipient=request.user,
        approval_status="approved",
    ).select_related(
        "sender",
        "announcement",
    )

    unread_count = messages_received.filter(
        is_read=False
    ).count()

    return render(
        request,
        "messaging/portal_messages.html",
        {
            "messages_received": messages_received,
            "unread_count": unread_count,
        }
    )


# =========================================================
# PORTAL SENT MESSAGES
# =========================================================

@login_required
def portal_sent_messages(request):

    messages_sent = Message.objects.filter(
        sender=request.user
    ).select_related(
        "recipient",
        "announcement",
    ).order_by(
        "-created_at"
    )

    return render(
        request,
        "messaging/portal_sent_messages.html",
        {
            "messages_sent": messages_sent,
        }
    )


# =========================================================
# ADMIN APPROVAL QUEUE
# =========================================================

@login_required
def pending_approvals(request):

    if not can_manage_message_approvals(request.user):
        raise PermissionDenied(
            "Only Admin can manage message approvals."
        )

    pending_messages = Message.objects.filter(
        approval_status="pending",
    ).select_related(
        "sender",
        "recipient",
        "announcement",
    ).order_by(
        "-created_at"
    )

    return render(
        request,
        "messaging/pending_approvals.html",
        {
            "pending_messages": pending_messages,
            "pending_count": pending_messages.count(),
        },
    )


# =========================================================
# APPROVE MESSAGE
# =========================================================

@login_required
def approve_message(request, message_id):

    if not can_manage_message_approvals(request.user):
        raise PermissionDenied(
            "Only Admin can approve messages."
        )

    message = get_object_or_404(
        Message,
        id=message_id,
        approval_status="pending",
    )

    if request.method != "POST":
        return redirect(
            "messaging:pending_approvals"
        )

    message.approval_status = "approved"
    message.approved_by = request.user
    message.approved_at = timezone.now()
    message.rejection_reason = ""

    message.save(
        update_fields=[
            "approval_status",
            "approved_by",
            "approved_at",
            "rejection_reason",
        ]
    )

    messages.success(
        request,
        f"Message to {message.recipient.get_full_name() or message.recipient.username} has been approved."
    )

    return redirect(
        "messaging:pending_approvals"
    )


# =========================================================
# REJECT MESSAGE
# =========================================================

@login_required
def reject_message(request, message_id):

    if not can_manage_message_approvals(request.user):
        raise PermissionDenied(
            "Only Admin can reject messages."
        )

    message = get_object_or_404(
        Message,
        id=message_id,
        approval_status="pending",
    )

    if request.method != "POST":
        return redirect(
            "messaging:pending_approvals"
        )

    rejection_reason = request.POST.get(
        "rejection_reason",
        "",
    ).strip()

    message.approval_status = "rejected"
    message.approved_by = request.user
    message.approved_at = timezone.now()
    message.rejection_reason = rejection_reason

    message.save(
        update_fields=[
            "approval_status",
            "approved_by",
            "approved_at",
            "rejection_reason",
        ]
    )

    messages.success(
        request,
        f"Message to {message.recipient.get_full_name() or message.recipient.username} has been rejected."
    )

    return redirect(
        "messaging:pending_approvals"
    )


