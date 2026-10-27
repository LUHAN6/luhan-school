import secrets
import string

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render

from students.models import Student
from hr_payroll.models import Employee

from .models import (
    UserProfile,
    Department,
    Role,
)

from timetable.models import TimetableSubject, TimetableTeacher
from timetable.advanced_models import TimetableTeacherSubject, TimetableTeacherClassAssignment, TimetableTeacherTeachingAssignment


# ============================================================
# ACCESS
# ============================================================

def _is_admin(request):
    user = request.user

    return (
        user.is_authenticated
        and (
            user.is_superuser
            or user.is_staff
            or getattr(
                getattr(user, "profile", None),
                "role",
                ""
            ) == "ADMIN"
        )
    )


def _deny(request, message):
    messages.error(request, message)

    if request.user.is_authenticated:
        return redirect("accounts:staff_management")

    return redirect("accounts:login")


# ============================================================
# CREDENTIALS
# ============================================================

def _generate_employee_number():

    highest = 0

    existing = set(
        Employee.objects
        .exclude(employee_number__isnull=True)
        .exclude(employee_number="")
        .values_list("employee_number", flat=True)
    )

    existing_profiles = set(
        UserProfile.objects
        .exclude(employee_number__isnull=True)
        .exclude(employee_number="")
        .values_list("employee_number", flat=True)
    )

    existing.update(existing_profiles)

    for value in existing:

        if not value.startswith("EMPLUH"):
            continue

        suffix = value[6:]

        if suffix.isdigit():
            highest = max(
                highest,
                int(suffix)
            )

    return f"EMPLUH{highest + 1:03d}"


def _generate_password(username="", first_name="", last_name="", email=""):

    alphabet = (
        string.ascii_uppercase
        + string.ascii_lowercase
        + string.digits
        + "!@#$%^&*-_"
    )
    candidate_user = User(
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=email,
    )

    for _ in range(50):
        candidate = "".join(
            secrets.choice(alphabet)
            for _ in range(24)
        )
        try:
            validate_password(candidate, user=candidate_user)
        except ValidationError:
            continue
        return candidate

    raise RuntimeError(
        "Could not generate a password satisfying configured validators."
    )


def _generate_staff_credentials():

    while True:

        employee_number = _generate_employee_number()

        exists = (
            Employee.objects.filter(
                employee_number=employee_number
            ).exists()
            or UserProfile.objects.filter(
                employee_number=employee_number
            ).exists()
            or User.objects.filter(
                username=employee_number
            ).exists()
        )

        if not exists:

            return (
                employee_number,
                employee_number,
                _generate_password(),
            )


# ============================================================
# COMMON DATA
# ============================================================

def _departments():
    return (
        Department.objects
        .filter(is_active=True)
        .order_by("name")
    )


def _roles():
    return (
        Role.objects
        .filter(is_active=True)
        .order_by("name")
    )


def _subjects():
    return (
        TimetableSubject.objects
        .filter(is_active=True)
        .order_by("name")
    )


def _class_pairs():

    return list(
        Student.objects
        .values_list(
            "class_name",
            "stream"
        )
        .distinct()
        .order_by(
            "class_name",
            "stream"
        )
    )


# ============================================================
# START
# ============================================================

@login_required
def start(request):

    if not _is_admin(request):
        return _deny(
            request,
            "You do not have permission to add staff."
        )

    request.session.pop("fresh_staff_wizard", None)
    request.session.pop("fresh_staff_created", None)

    request.session.modified = True

    return render(
        request,
        "accounts/fresh_staff_type_selection.html"
    )


# ============================================================
# TEACHING DETAILS
# ============================================================

@login_required
def teaching_details(request):

    if not _is_admin(request):
        return _deny(
            request,
            "You do not have permission to add staff."
        )

    if request.method == "POST":

        first_name = request.POST.get(
            "first_name",
            ""
        ).strip()

        last_name = request.POST.get(
            "last_name",
            ""
        ).strip()

        email = request.POST.get(
            "email",
            ""
        ).strip()

        phone = request.POST.get(
            "phone",
            ""
        ).strip()

        job_title = request.POST.get(
            "job_title",
            ""
        ).strip()

        department = request.POST.get(
            "department",
            ""
        ).strip()

        if not first_name or not last_name:

            messages.error(
                request,
                "First name and last name are required."
            )

            return render(
                request,
                "accounts/fresh_teaching_details.html",
                {
                    "departments": _departments(),
                }
            )

        employee_number, username, password = (
            _generate_staff_credentials()
        )

        request.session["fresh_staff_wizard"] = {
            "staff_type": "TEACHING",
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "job_title": job_title,
            "department": department,
            "employee_number": employee_number,
            "username": username,
            "password": password,
        }

        request.session.modified = True

        return redirect(
            "accounts:fresh_staff_role"
        )

    return render(
        request,
        "accounts/fresh_teaching_details.html",
        {
            "departments": _departments(),
        }
    )


# ============================================================
# SUPPORT DETAILS
# ============================================================

@login_required
def support_details(request):

    if not _is_admin(request):
        return _deny(
            request,
            "You do not have permission to add staff."
        )

    if request.method == "POST":

        first_name = request.POST.get(
            "first_name",
            ""
        ).strip()

        last_name = request.POST.get(
            "last_name",
            ""
        ).strip()

        email = request.POST.get(
            "email",
            ""
        ).strip()

        phone = request.POST.get(
            "phone",
            ""
        ).strip()

        job_title = request.POST.get(
            "job_title",
            ""
        ).strip()

        department = request.POST.get(
            "department",
            ""
        ).strip()

        if not first_name or not last_name:

            messages.error(
                request,
                "First name and last name are required."
            )

            return render(
                request,
                "accounts/fresh_support_details.html",
                {
                    "departments": _departments(),
                }
            )

        employee_number, username, password = (
            _generate_staff_credentials()
        )

        request.session["fresh_staff_wizard"] = {
            "staff_type": "SUPPORT",
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "job_title": job_title,
            "department": department,
            "employee_number": employee_number,
            "username": username,
            "password": password,
        }

        request.session.modified = True

        return redirect(
            "accounts:fresh_staff_role"
        )

    return render(
        request,
        "accounts/fresh_support_details.html",
        {
            "departments": _departments(),
        }
    )


# ============================================================
# ROLE
# ============================================================

@login_required
def role(request):

    if not _is_admin(request):
        return _deny(
            request,
            "You do not have permission to add staff."
        )

    data = request.session.get(
        "fresh_staff_wizard"
    )

    if not data:

        messages.error(
            request,
            "Staff details were not found. Please start again."
        )

        return redirect(
            "accounts:fresh_staff_start"
        )

    if request.method == "POST":

        role_id = request.POST.get(
            "custom_role"
        )

        selected_role = (
            Role.objects
            .filter(
                id=role_id,
                is_active=True
            )
            .first()
        )

        if not selected_role:

            messages.error(
                request,
                "Please select a valid staff role."
            )

            return render(
                request,
                "accounts/fresh_staff_role.html",
                {
                    "data": data,
                    "roles": _roles(),
                }
            )

        data["custom_role"] = selected_role.id
        data["custom_role_name"] = selected_role.name

        request.session["fresh_staff_wizard"] = data
        request.session.modified = True

        if data.get("staff_type") == "TEACHING":

            return redirect(
                "accounts:fresh_staff_subjects"
            )

        return _create_staff_account(
            request,
            data
        )

    return render(
        request,
        "accounts/fresh_staff_role.html",
        {
            "data": data,
            "roles": _roles(),
        }
    )


# ============================================================
# SUBJECTS
# ============================================================

@login_required
def subjects(request):

    if not _is_admin(request):
        return _deny(
            request,
            "You do not have permission to assign subjects."
        )

    data = request.session.get(
        "fresh_staff_wizard"
    )

    if not data or data.get("staff_type") != "TEACHING":

        messages.error(
            request,
            "Teaching staff details were not found."
        )

        return redirect(
            "accounts:fresh_staff_start"
        )

    available_subjects = _subjects()

    if request.method == "POST":

        selected_ids = request.POST.getlist(
            "subjects"
        )

        valid_ids = list(
            available_subjects
            .filter(
                id__in=selected_ids
            )
            .values_list(
                "id",
                flat=True
            )
        )

        if not valid_ids:

            messages.error(
                request,
                "Select at least one subject."
            )

            return render(
                request,
                "accounts/fresh_staff_subjects.html",
                {
                    "data": data,
                    "subjects": available_subjects,
                }
            )

        data["subject_ids"] = valid_ids
        data["subject_names"] = list(
            available_subjects
            .filter(
                id__in=valid_ids
            )
            .values_list(
                "name",
                flat=True
            )
        )

        request.session["fresh_staff_wizard"] = data
        request.session.modified = True

        return redirect(
            "accounts:fresh_staff_classes"
        )

    return render(
        request,
        "accounts/fresh_staff_subjects.html",
        {
            "data": data,
            "subjects": available_subjects,
        }
    )


# ============================================================
# CLASSES + CLASS TEACHER
# ============================================================

@login_required
def classes(request):

    if not _is_admin(request):
        return _deny(
            request,
            "You do not have permission to assign classes."
        )

    data = request.session.get(
        "fresh_staff_wizard"
    )

    if not data or data.get("staff_type") != "TEACHING":

        messages.error(
            request,
            "Teaching staff details were not found."
        )

        return redirect(
            "accounts:fresh_staff_start"
        )

    subject_ids = data.get(
        "subject_ids",
        []
    )

    selected_subjects = (
        _subjects()
        .filter(id__in=subject_ids)
        .order_by("name")
    )

    class_pairs = _class_pairs()

    if request.method == "POST":

        selected_assignments = request.POST.getlist(
            "teaching_assignments"
        )

        selected_class_teachers = request.POST.getlist(
            "class_teachers"
        )

        valid_pairs = {
            (
                str(class_name),
                str(stream or "")
            )
            for class_name, stream in class_pairs
        }

        assignments = []
        seen_assignments = set()

        for value in selected_assignments:

            parts = value.split(
                "|",
                2
            )

            if len(parts) != 3:
                continue

            subject_id, class_name, stream = parts

            try:
                subject_id = int(subject_id)
            except (
                TypeError,
                ValueError
            ):
                continue

            if not selected_subjects.filter(
                id=subject_id
            ).exists():
                continue

            pair = (
                str(class_name),
                str(stream or "")
            )

            if pair not in valid_pairs:
                continue

            key = (
                subject_id,
                pair[0],
                pair[1]
            )

            if key in seen_assignments:
                continue

            seen_assignments.add(key)

            assignments.append({
                "subject_id": subject_id,
                "class_name": pair[0],
                "stream": pair[1],
            })

        if not assignments:

            messages.error(
                request,
                "Assign at least one subject to at least one class."
            )

            return render(
                request,
                "accounts/fresh_staff_classes.html",
                {
                    "data": data,
                    "subjects": selected_subjects,
                    "class_pairs": class_pairs,
                }
            )

        class_teachers = []

        for value in selected_class_teachers:

            parts = value.split(
                "|",
                1
            )

            if len(parts) != 2:
                continue

            class_name, stream = parts

            pair = (
                str(class_name),
                str(stream or "")
            )

            if pair not in valid_pairs:
                continue

            class_teachers.append({
                "class_name": pair[0],
                "stream": pair[1],
            })

        data["teaching_assignments"] = assignments
        data["class_teachers"] = class_teachers

        request.session["fresh_staff_wizard"] = data
        request.session.modified = True

        return _create_staff_account(
            request,
            data
        )

    return render(
        request,
        "accounts/fresh_staff_classes.html",
        {
            "data": data,
            "subjects": selected_subjects,
            "class_pairs": class_pairs,
        }
    )


# ============================================================
# CREATE ACCOUNT
# ============================================================

def _create_staff_account(
    request,
    data
):

    custom_role = (
        Role.objects
        .filter(
            id=data.get("custom_role"),
            is_active=True
        )
        .first()
    )

    if not custom_role:

        messages.error(
            request,
            "The selected staff role is no longer available."
        )

        return redirect(
            "accounts:fresh_staff_role"
        )

    username = data.get(
        "username"
    )

    password = data.get(
        "password"
    )

    employee_number = data.get(
        "employee_number"
    )

    try:
        validate_password(
            password or "",
            user=User(
                username=username or "",
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
                email=data.get("email", ""),
            ),
        )
    except ValidationError as exc:
        messages.error(
            request,
            "The staff password failed the configured security rules. "
            "Restart staff registration and try again."
        )
        return redirect("accounts:fresh_staff_role")

    try:

        with transaction.atomic():

            if User.objects.filter(
                username=username
            ).exists():

                raise IntegrityError(
                    f"Username {username} already exists."
                )

            if Employee.objects.filter(
                employee_number=employee_number
            ).exists():

                raise IntegrityError(
                    f"Employee number {employee_number} already exists."
                )

            if UserProfile.objects.filter(
                employee_number=employee_number
            ).exists():

                raise IntegrityError(
                    f"Employee number {employee_number} already exists."
                )

            department = None

            department_id = data.get(
                "department"
            )

            if department_id:

                department = (
                    Department.objects
                    .filter(
                        id=department_id,
                        is_active=True
                    )
                    .first()
                )

            user = User.objects.create_user(
                username=username,
                password=password,
                first_name=data.get(
                    "first_name",
                    ""
                ),
                last_name=data.get(
                    "last_name",
                    ""
                ),
                email=data.get(
                    "email",
                    ""
                )
            )

            user.is_active = True
            user.save(
                update_fields=[
                    "is_active"
                ]
            )

            employee = Employee.objects.create(
                employee_number=employee_number,
                first_name=data.get(
                    "first_name",
                    ""
                ),
                last_name=data.get(
                    "last_name",
                    ""
                ),

                email=data.get(
                    "email",
                    ""
                ),
                is_active=True
            )

            UserProfile.objects.create(
                user=user,
                role="STAFF",
                custom_role=custom_role,
                employee=employee,
                employee_number=employee_number,

                job_title=data.get(
                    "job_title",
                    ""
                ),
                department=department,
                is_active=True
            )

            teacher = None
            assigned_subject_names = []
            assigned_class_names = []
            class_teacher_names = []

            if data.get("staff_type") == "TEACHING":

                teacher = TimetableTeacher.objects.create(
                    employee=employee,
                    name=(
                        f"{data.get('first_name', '')} "
                        f"{data.get('last_name', '')}"
                    ).strip(),
                    employee_no=employee_number,

                    email=data.get(
                        "email",
                        ""
                    ),
                    is_active=True
                )

                subject_ids = data.get(
                    "subject_ids",
                    []
                )

                selected_subjects = (
                    TimetableSubject.objects
                    .filter(
                        id__in=subject_ids,
                        is_active=True
                    )
                    .order_by("name")
                )

                for subject in selected_subjects:

                    TimetableTeacherSubject.objects.get_or_create(
                        teacher=teacher,
                        subject=subject,
                        defaults={
                            "is_active": True
                        }
                    )

                    assigned_subject_names.append(
                        subject.name
                    )

                # -----------------------------------------
                # SUBJECT + CLASS
                # -----------------------------------------

                for assignment in data.get(
                    "teaching_assignments",
                    []
                ):

                    subject = (
                        TimetableSubject.objects
                        .filter(
                            id=assignment.get(
                                "subject_id"
                            ),
                            is_active=True
                        )
                        .first()
                    )

                    class_name = (
                        assignment.get(
                            "class_name",
                            ""
                        )
                        or ""
                    ).strip()

                    stream = (
                        assignment.get(
                            "stream",
                            ""
                        )
                        or ""
                    ).strip()

                    if not subject or not class_name:
                        continue

                    TimetableTeacherTeachingAssignment.objects.get_or_create(
                        teacher=teacher,
                        subject=subject,
                        class_name=class_name,
                        stream=stream or None,
                        defaults={
                            "is_active": True
                        }
                    )

                    TimetableTeacherClassAssignment.objects.get_or_create(
                        teacher=teacher,
                        class_name=class_name,
                        stream=stream or None,
                        defaults={
                            "is_class_teacher": False,
                            "is_active": True
                        }
                    )

                    display_class = class_name

                    if stream:
                        display_class = (
                            f"{class_name} - {stream}"
                        )

                    assigned_class_names.append(
                        f"{subject.name} → {display_class}"
                    )

                # -----------------------------------------
                # CLASS TEACHER
                # -----------------------------------------

                for assignment in data.get(
                    "class_teachers",
                    []
                ):

                    class_name = (
                        assignment.get(
                            "class_name",
                            ""
                        )
                        or ""
                    ).strip()

                    stream = (
                        assignment.get(
                            "stream",
                            ""
                        )
                        or ""
                    ).strip()

                    if not class_name:
                        continue

                    # One active class teacher per class/stream.
                    TimetableTeacherClassAssignment.objects.filter(
                        class_name=class_name,
                        stream=stream or None,
                        is_class_teacher=True,
                        is_active=True
                    ).exclude(
                        teacher=teacher
                    ).update(
                        is_class_teacher=False
                    )

                    class_assignment, created = (
                        TimetableTeacherClassAssignment.objects.get_or_create(
                            teacher=teacher,
                            class_name=class_name,
                            stream=stream or None,
                            defaults={
                                "is_class_teacher": True,
                                "is_active": True
                            }
                        )
                    )

                    if not created:

                        class_assignment.is_class_teacher = True
                        class_assignment.is_active = True

                        class_assignment.save(
                            update_fields=[
                                "is_class_teacher",
                                "is_active"
                            ]
                        )

                    display_class = class_name

                    if stream:
                        display_class = (
                            f"{class_name} - {stream}"
                        )

                    class_teacher_names.append(
                        display_class
                    )

            result = {
                "first_name": data.get(
                    "first_name",
                    ""
                ),
                "last_name": data.get(
                    "last_name",
                    ""
                ),
                "staff_type": data.get(
                    "staff_type",
                    ""
                ),
                "role": custom_role.name,
                "employee_number": employee_number,
                "username": username,
                "password": password,
                "subjects": assigned_subject_names,
                "classes": assigned_class_names,
                "class_teachers": class_teacher_names,
            }

            request.session[
                "fresh_staff_created"
            ] = result

            request.session.pop(
                "fresh_staff_wizard",
                None
            )

            request.session.modified = True

        messages.success(
            request,
            "Staff account created successfully."
        )

        return redirect(
            "accounts:fresh_staff_success"
        )

    except IntegrityError as exc:

        messages.error(
            request,
            str(exc)
        )

        return redirect(
            "accounts:fresh_staff_role"
        )


# ============================================================
# SUCCESS
# ============================================================

@login_required
def success(request):

    if not _is_admin(request):
        return _deny(
            request,
            "You do not have permission to view this page."
        )

    staff = request.session.pop(
        "fresh_staff_created", None
    )

    if not staff:

        messages.info(
            request,
            "No recent staff account creation was found."
        )

        return redirect(
            "accounts:staff_management"
        )

    response = render(
        request,
        "accounts/fresh_staff_success.html",
        {
            "staff": staff,
        }
    )

    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"

    return response




