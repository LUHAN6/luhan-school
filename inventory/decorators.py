from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect


def inventory_access_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)
        profile = getattr(request.user, "userprofile", None)
        role = getattr(profile, "role", "") if profile else ""
        custom_role = getattr(profile, "custom_role", None) if profile else None

        role_permission = False
        if custom_role and custom_role.is_active:
            role_permission = custom_role.permissions.filter(
                codename="view_inventoryitem",
                content_type__app_label="inventory",
            ).exists()

        allowed = (
            request.user.is_superuser
            or role == "ADMIN"
            or role_permission
        )
        if not allowed:
            messages.error(request, "You do not have permission to access Inventory.")
            return redirect("/")
        return view_func(request, *args, **kwargs)
    return wrapper




