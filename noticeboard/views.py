from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.views import user_has_role_permission
from accounts.staff_access import get_staff_teacher

from .models import Notice


def is_staff_user(user):
    """
    Returns True for a normal ERP Staff user.

    A staff member is identified from the existing UserProfile
    and the existing Teacher relationship. We do not create
    another staff-type system.
    """
    try:
        profile = user.profile
    except Exception:
        return False

    return (
        profile.role == "STAFF"
        and profile.employee_id is not None
    )


def is_support_staff(user):
    """
    Support Staff are ERP STAFF users who do not have
    an active timetable Teacher record.
    """
    return (
        is_staff_user(user)
        and get_staff_teacher(user) is None
    )


def is_teaching_staff(user):
    """
    Teaching Staff are ERP STAFF users who have an
    active timetable Teacher record.
    """
    return (
        is_staff_user(user)
        and get_staff_teacher(user) is not None
    )


def is_admin_user(user):
    """
    Admin users retain full administrative access.
    """
    if user.is_superuser:
        return True

    try:
        profile = user.profile
    except Exception:
        return False

    return profile.role == "ADMIN"


@login_required
def noticeboard_dashboard(request):
    """
    Staff Notice Board.

    Staff are strictly VIEW-ONLY.

    They can see:
        - published notices
        - notices for Everyone
        - notices for Staff

    They cannot create, edit, delete, publish or manage notices
    from this portal.
    """

    # ---------------------------------------------------------
    # ACCESS CONTROL
    # ---------------------------------------------------------

    staff_access = user_has_role_permission(
        request.user,
        "view_notice",
        "noticeboard",
    )

    if not (
        request.user.is_superuser
        or is_admin_user(request.user)
        or staff_access
    ):
        return redirect("accounts:staff_dashboard")

    # ---------------------------------------------------------
    # CURRENT TIME
    # ---------------------------------------------------------

    now = timezone.now()

    # ---------------------------------------------------------
    # STAFF / ADMIN NOTICE VISIBILITY
    # ---------------------------------------------------------

    if is_staff_user(request.user) and not is_admin_user(request.user):
        notices = (
            Notice.objects
            .filter(
                published=True,
                audience__in=[
                    "everyone",
                    "staff",
                ],
            )
            .filter(
                expiry_date__isnull=True
            )
            | Notice.objects.filter(
                published=True,
                audience__in=[
                    "everyone",
                    "staff",
                ],
                expiry_date__gte=now,
            )
        )

        notices = notices.distinct().order_by(
            "-publish_date"
        )

    else:
        # Admin can see all published notices.
        notices = (
            Notice.objects
            .filter(published=True)
            .filter(
                expiry_date__isnull=True
            )
            | Notice.objects.filter(
                published=True,
                expiry_date__gte=now,
            )
        )

        notices = notices.distinct().order_by(
            "-publish_date"
        )

    context = {
        "notices": notices,
        "is_notice_admin": is_admin_user(request.user),
        "is_notice_staff": is_staff_user(request.user),
        "is_support_staff": is_support_staff(request.user),
        "is_teaching_staff": is_teaching_staff(request.user),
    }

    return render(
        request,
        "noticeboard/noticeboard_dashboard.html",
        context,
    )


