from django.core.exceptions import ObjectDoesNotExist
from timetable.models import TimetableTeacher


def erp_permissions(request):
    """
    Expose the logged-in user's custom Role -> Permission access
    to templates.

    Usage:
        {% if erp_permission.view_hostel %}
        {% if erp_permission.view_room %}
        {% if erp_permission.add_hostelincident %}

    Superusers are allowed everything.
    Anonymous users have no permissions.
    """

    user = getattr(request, "user", None)

    if not user or not user.is_authenticated:
        return {
            "erp_permission": PermissionProxy(False, None),
        }

    if user.is_superuser:
        return {
            "erp_permission": PermissionProxy(True, None),
        }

    try:
        profile = user.profile
    except (AttributeError, ObjectDoesNotExist):
        return {
            "erp_permission": PermissionProxy(False, None),
        }

    role = getattr(profile, "custom_role", None)

    if not role or not role.is_active:
        return {
            "erp_permission": PermissionProxy(False, None),
        }

    permission_ids = set(
        role.permissions.values_list("id", flat=True)
    )

    return {
        "erp_permission": PermissionProxy(
            True,
            permission_ids,
        ),
    }


class PermissionProxy:
    """
    Template-friendly permission checker.

    Supports:
        erp_permission.view_hostel
        erp_permission.view_room

    The proxy receives a permission codename because the same
    codename can technically exist in different Django apps.
    """

    def __init__(self, unrestricted=False, permission_ids=None):
        self.unrestricted = unrestricted
        self.permission_ids = permission_ids or set()

    def __getattr__(self, codename):
        if self.unrestricted:
            return True

        if not self.permission_ids:
            return False

        from django.contrib.auth.models import Permission

        return Permission.objects.filter(
            id__in=self.permission_ids,
            codename=codename,
        ).exists()

def portal_capabilities(request):
    """
    Centralized portal feature visibility.

    Staff capabilities continue to come from Role -> Permission.
    Student and Parent capabilities are tied to their portal role
    and do not use staff custom roles.
    """

    user = getattr(request, "user", None)

    capabilities = {
        "portal_is_admin": False,
        "portal_is_staff": False,
        "portal_is_student": False,
        "portal_is_parent": False,

        "portal_view_academic": False,
        "portal_view_fees": False,
        "portal_view_timetable": False,
        "portal_view_assignments": False,
        "portal_view_learning": False,
        "portal_view_attendance": False,
        "portal_view_announcements": False,
        "portal_view_library": False,
        "portal_view_messaging": False,
        "portal_view_weekly_reports": False,
        "portal_view_hostel": False,
    }

    if not user or not user.is_authenticated:
        return {"portal_capabilities": capabilities}

    if user.is_superuser:
        capabilities.update({
            "portal_is_admin": True,
            "portal_is_staff": True,
            "portal_view_academic": True,
            "portal_view_fees": True,
            "portal_view_timetable": True,
            "portal_view_assignments": True,
            "portal_view_learning": True,
            "portal_view_attendance": True,
            "portal_view_announcements": True,
            "portal_view_library": True,
            "portal_view_messaging": True,
            "portal_view_weekly_reports": True,
            "portal_view_hostel": True,
        })
        return {"portal_capabilities": capabilities}

    try:
        profile = user.profile
    except Exception:
        return {"portal_capabilities": capabilities}

    role = getattr(profile, "role", "")

    if role == "ADMIN":
        capabilities.update({
            "portal_is_admin": True,
            "portal_is_staff": True,
            "portal_view_academic": True,
            "portal_view_fees": True,
            "portal_view_timetable": True,
            "portal_view_assignments": True,
            "portal_view_learning": True,
            "portal_view_attendance": True,
            "portal_view_announcements": True,
            "portal_view_library": True,
            "portal_view_messaging": True,
            "portal_view_weekly_reports": True,
            "portal_view_hostel": True,
        })

    elif role == "STAFF":
        capabilities["portal_is_staff"] = True

        role_obj = getattr(profile, "custom_role", None)

        if role_obj and role_obj.is_active:
            permission_ids = set(
                role_obj.permissions.values_list("id", flat=True)
            )

            from django.contrib.auth.models import Permission

            def has_permission(codename, app_label=None):
                qs = Permission.objects.filter(
                    id__in=permission_ids,
                    codename=codename,
                )

                if app_label:
                    qs = qs.filter(
                        content_type__app_label=app_label
                    )

                return qs.exists()

            capabilities.update({
                "portal_view_academic":
                    has_permission(
                        "view_academicrecord",
                        "academic",
                    ),

                "portal_view_fees":
                    has_permission(
                        "view_feerecord",
                        "fees",
                    ),

                "portal_view_timetable":
                    has_permission(
                        "view_timetablelesson",
                        "timetable",
                    ),

                "portal_view_announcements":
                    has_permission(
                        "view_notice",
                        "noticeboard",
                    ),

                "portal_view_library":
                    has_permission(
                        "view_librarymember",
                        "library",
                    ),

                "portal_view_messaging":
                    has_permission(
                        "view_message",
                        "messaging",
                    ),

                "portal_view_weekly_reports":
                    has_permission(
                        "view_weeklyassessmentreport",
                        "weekly_reports",
                    ),

                "portal_view_hostel":
                    has_permission(
                        "view_hostel",
                        "hostel",
                    ),
            })

            # Teaching staff receive academic navigation only when
            # they actually have an active Teacher record.
            try:
                

                has_teacher = TimetableTeacher.objects.filter(
                    employee=getattr(profile, "employee", None),
                    active=True,
                ).exists()

            except Exception:
                has_teacher = False

            if not has_teacher:
                capabilities["portal_view_academic"] = False
                capabilities["portal_view_timetable"] = False

    elif role == "STUDENT":
        capabilities.update({
            "portal_is_student": True,
            "portal_view_academic": True,
            "portal_view_fees": True,
            "portal_view_timetable": True,
            "portal_view_assignments": True,
            "portal_view_learning": True,
            "portal_view_attendance": True,
            "portal_view_announcements": True,
            "portal_view_library": True,
            "portal_view_messaging": True,
            "portal_view_weekly_reports": True,
            "portal_view_hostel": True,
        })

    elif role == "PARENT":
        capabilities.update({
            "portal_is_parent": True,
            "portal_view_academic": True,
            "portal_view_fees": True,
            "portal_view_timetable": True,
            "portal_view_assignments": True,
            "portal_view_learning": True,
            "portal_view_attendance": True,
            "portal_view_announcements": True,
            "portal_view_library": True,
            "portal_view_messaging": True,
            "portal_view_weekly_reports": True,
            "portal_view_hostel": True,
        })

    return {
        "portal_capabilities": capabilities,
    }




