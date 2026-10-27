
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from fees.models import AcademicYear, Term
from timetable.legacy_compat import Teacher, TeacherTeachingAssignment, Subject

from professional_documents.models import ProfessionalDocument
from weekly_reports.views import (
    _is_admin,
    _is_staff,
    get_staff_teacher,
)

from .models import TermlySubmissionRequirement


User = get_user_model()

def _teacher_user(teacher):
    """
    Resolve a timetable.TimetableTeacher to the Django User linked
    through Teacher -> Employee -> User.profile.employee.
    """
    if not teacher or not getattr(teacher, "employee_id", None):
        return None

    try:
        return User.objects.filter(
            profile__employee_id=teacher.employee_id
        ).first()
    except Exception:
        return None



# ============================================================
# HELPERS
# ============================================================

def _employee_number(obj):
    """
    Return the employee number from any supported staff/teacher object.

    Primary source:
        timetable.TimetableTeacher.employee_no

    Also supports:
        hr_payroll.Employee.employee_no
        hr_payroll.Employee.employee_number
        linked user/profile fields

    This keeps the module flexible when new teachers are added.
    """

    if obj is None:
        return ""

    # timetable.TimetableTeacher
    value = getattr(obj, "employee_no", None)
    if value:
        return str(value).strip()

    value = getattr(obj, "employee_number", None)
    if value:
        return str(value).strip()

    # Linked HR employee
    employee = getattr(obj, "employee", None)

    if employee is not None:
        for field in (
            "employee_no",
            "employee_number",
            "staff_number",
            "staff_no",
            "employee_id",
        ):
            value = getattr(employee, field, None)
            if value:
                return str(value).strip()

    # Linked Django user/profile
    for candidate in (
        getattr(obj, "user", None),
        getattr(obj, "profile", None),
        getattr(obj, "staff_profile", None),
        getattr(obj, "teacher_profile", None),
    ):
        if candidate is None:
            continue

        for field in (
            "employee_no",
            "employee_number",
            "employee_id",
            "staff_number",
            "staff_no",
        ):
            value = getattr(candidate, field, None)
            if value:
                return str(value).strip()

    return ""


def _teacher_label(user):
    name = user.get_full_name()

    if name:
        return f"{name} ({_employee_number(user)})"

    return f"{user.username} ({_employee_number(user)})"


def _staff_users():
    """
    Return active timetable.TimetableTeacher records that have active
    TeacherTeachingAssignment records.

    IMPORTANT:
    The timetable.TimetableTeacher model is the source of truth for
    teaching staff in this module.

    New teachers automatically appear as soon as they have:
        1. an active Teacher record
        2. an active teaching assignment

    No hard-coded teacher list is used.
    """

    teacher_ids = (
        TeacherTeachingAssignment.objects
        .filter(
            is_active=True,
            teacher__active=True,
        )
        .values_list("teacher_id", flat=True)
        .distinct()
    )

    return (
        Teacher.objects
        .filter(
            id__in=teacher_ids,
            is_active=True,
        )
        .select_related("employee")
        .order_by("name")
    )


def _teacher_assignments_for_teacher(teacher):
    """
    Return the active teaching assignments belonging to a
    timetable.TimetableTeacher.

    This is the source of truth for Termly Submission Requirements.
    """
    if teacher is None:
        return TeacherTeachingAssignment.objects.none()

    return (
        TeacherTeachingAssignment.objects
        .filter(
            teacher=teacher,
            teacher__is_active=True,
            is_active=True,
        )
        .select_related(
            "teacher",
            "subject",
        )
        .order_by(
            "class_name",
            "stream",
            "subject__name",
        )
    )


def _teacher_assignments_for_user(user):
    """
    Return active teaching assignments for the logged-in staff user.

    Staff users are resolved through the existing ERP staff-access
    mapping, which connects the login -> Employee -> Teacher.
    """

    teacher = get_staff_teacher(user)

    if teacher is None:
        return TeacherTeachingAssignment.objects.none()

    return (
        TeacherTeachingAssignment.objects
        .filter(
            teacher=teacher,
            teacher__is_active=True,
            is_active=True,
        )
        .select_related(
            "teacher",
            "subject",
        )
        .order_by(
            "class_name",
            "stream",
            "subject__name",
        )
    )


def _assignment_rows(user=None, teacher=None):
    """
    Build assignment rows directly from timetable.TimetableTeacher.

    Admin:
        teacher=selected Teacher

    Staff:
        user=logged-in user
    """

    if teacher is not None:
        queryset = (
            TeacherTeachingAssignment.objects
            .filter(
                teacher=teacher,
                teacher__is_active=True,
                is_active=True,
            )
            .select_related(
                "teacher",
                "subject",
            )
            .order_by(
                "class_name",
                "stream",
                "subject__name",
            )
        )
    else:
        queryset = _teacher_assignments_for_user(user)

    rows = []

    for assignment in queryset:
        teacher_obj = assignment.teacher

        rows.append({
            "teacher": teacher_obj,
            "teacher_name": teacher_obj.name,
            "employee_number": _employee_number(teacher_obj),
            "assignment": assignment,
            "class_name": assignment.class_name,
            "stream": assignment.stream or "",
            "subject": assignment.subject,
        })

    return rows


def _approved_count(
    teacher,
    academic_year,
    term,
    document_type,
    class_name,
    stream,
    subject,
):
    """
    Count ONLY APPROVED professional documents.

    Termly requirements use timetable.TimetableTeacher.
    ProfessionalDocument.teacher uses Django User.
    """
    teacher_user = _teacher_user(teacher)

    if not teacher_user:
        return 0

    qs = ProfessionalDocument.objects.filter(
        teacher=teacher_user,
        academic_year=academic_year,
        term=term,
        document_type=document_type,
        class_name=class_name,
        subject=subject,
        status=ProfessionalDocument.STATUS_APPROVED,
    )

    if stream:
        qs = qs.filter(stream=stream)
    else:
        qs = qs.filter(stream__in=["", None])

    return qs.count()

def _build_report(
    teacher,
    academic_year,
    term,
):
    requirements = TermlySubmissionRequirement.objects.filter(
        teacher=teacher,
        academic_year=academic_year,
        term=term,
    ).select_related(
        "subject",
    )

    rows = []

    total_expected = 0
    total_approved = 0

    for requirement in requirements:

        schemes = _approved_count(
            teacher,
            academic_year,
            term,
            ProfessionalDocument.TYPE_SCHEME,
            requirement.class_name,
            requirement.stream,
            requirement.subject,
        )

        records = _approved_count(
            teacher,
            academic_year,
            term,
            ProfessionalDocument.TYPE_RECORD,
            requirement.class_name,
            requirement.stream,
            requirement.subject,
        )

        lessons = _approved_count(
            teacher,
            academic_year,
            term,
            ProfessionalDocument.TYPE_LESSON,
            requirement.class_name,
            requirement.stream,
            requirement.subject,
        )

        expected = (
            requirement.expected_schemes
            + requirement.expected_records
            + requirement.expected_lesson_plans
        )

        approved = schemes + records + lessons

        outstanding = max(
            expected - approved,
            0,
        )

        percentage = (
            (approved / expected) * 100
            if expected
            else 100
        )

        total_expected += expected
        total_approved += approved

        rows.append({
            "requirement": requirement,

            "schemes_approved": schemes,
            "records_approved": records,
            "lessons_approved": lessons,

            "expected": expected,
            "approved": approved,
            "outstanding": outstanding,

            "percentage": round(
                percentage,
                2,
            ),
        })

    overall_percentage = (
        (total_approved / total_expected) * 100
        if total_expected
        else 100
    )

    return {
        "rows": rows,
        "total_expected": total_expected,
        "total_approved": total_approved,
        "total_outstanding": max(
            total_expected - total_approved,
            0,
        ),
        "overall_percentage": round(
            overall_percentage,
            2,
        ),
    }


# ============================================================
# STAFF REPORT
# ============================================================

@login_required
def staff_report(request):

    if not _is_staff(request.user) or _is_admin(request.user):
        return HttpResponseForbidden("Access denied.")

    year_id = request.GET.get("academic_year")
    term_id = request.GET.get("term")

    years = AcademicYear.objects.all().order_by("-year")
    terms = Term.objects.all().order_by("-id")

    if year_id:
        academic_year = get_object_or_404(
            AcademicYear,
            pk=year_id,
        )
    else:
        academic_year = years.first()

    if term_id:
        term = get_object_or_404(
            Term,
            pk=term_id,
        )
    else:
        term = terms.first()

    report = None

    if academic_year and term:

        teacher = get_staff_teacher(request.user)

        report = _build_report(
            teacher,
            academic_year,
            term,
        )

    return render(
        request,
        "termly_submission/staff_report.html",
        {
            "academic_years": years,
            "terms": terms,
            "selected_year": academic_year,
            "selected_term": term,
            "report": report,
            "employee_number": _employee_number(request.user),
            "teacher_name": _teacher_label(request.user),
        },
    )


# ============================================================
# ADMIN REQUIREMENTS
# ============================================================

@login_required
def admin_requirements(request):

    if not _is_admin(request.user):
        return HttpResponseForbidden("Access denied.")

    years = AcademicYear.objects.all().order_by("-year")
    terms = Term.objects.all().order_by("-id")
    teachers = _staff_users()

    selected_year_id = request.GET.get("academic_year")
    selected_term_id = request.GET.get("term")
    selected_teacher_id = request.GET.get("teacher")

    selected_year = (
        get_object_or_404(
            AcademicYear,
            pk=selected_year_id,
        )
        if selected_year_id
        else years.first()
    )

    selected_term = (
        get_object_or_404(
            Term,
            pk=selected_term_id,
        )
        if selected_term_id
        else terms.first()
    )

    selected_teacher = (
        get_object_or_404(
            Teacher,
            pk=selected_teacher_id,
        )
        if selected_teacher_id
        else None
    )

    rows = []

    if selected_year and selected_term and selected_teacher:

        assignments = _teacher_assignments_for_teacher(
            selected_teacher
        )

        for assignment in assignments:

            requirement, created = (
                TermlySubmissionRequirement.objects.get_or_create(
                    teacher=selected_teacher,
                    academic_year=selected_year,
                    term=selected_term,
                    class_name=assignment.class_name,
                    stream=assignment.stream or "",
                    subject=assignment.subject,
                    defaults={
                        "expected_schemes": 0,
                        "expected_records": 0,
                        "expected_lesson_plans": 0,
                    },
                )
            )

            rows.append(requirement)

    if request.method == "POST":

        academic_year = get_object_or_404(
            AcademicYear,
            pk=request.POST.get("academic_year"),
        )

        term = get_object_or_404(
            Term,
            pk=request.POST.get("term"),
        )

        teacher = get_object_or_404(
            Teacher,
            pk=request.POST.get("teacher"),
        )

        requirement_id = request.POST.get(
            "requirement_id"
        )

        requirement = get_object_or_404(
            TermlySubmissionRequirement,
            pk=requirement_id,
            teacher=teacher,
            academic_year=academic_year,
            term=term,
        )

        requirement.expected_schemes = max(
            int(request.POST.get("expected_schemes") or 0),
            0,
        )

        requirement.expected_records = max(
            int(request.POST.get("expected_records") or 0),
            0,
        )

        requirement.expected_lesson_plans = max(
            int(
                request.POST.get(
                    "expected_lesson_plans"
                )
                or 0
            ),
            0,
        )

        requirement.admin_feedback = request.POST.get(
            "admin_feedback",
            "",
        ).strip()

        requirement.feedback_updated_at = timezone.now()

        requirement.save()

        messages.success(
            request,
            "Submission requirement updated successfully.",
        )

        return redirect(
            request.get_full_path()
        )

    return render(
        request,
        "termly_submission/admin_requirements.html",
        {
            "academic_years": years,
            "terms": terms,
            "teachers": teachers,
            "selected_year": selected_year,
            "selected_term": selected_term,
            "selected_teacher": selected_teacher,
            "rows": rows,
            "employee_number": (
                _employee_number(selected_teacher)
                if selected_teacher
                else ""
            ),
        },
    )


# ============================================================
# ADMIN VIEW SUBMISSION
# ============================================================

@login_required
def admin_report(request):

    if not _is_admin(request.user):
        return HttpResponseForbidden("Access denied.")

    years = AcademicYear.objects.all().order_by("-year")
    terms = Term.objects.all().order_by("-id")
    teachers = _staff_users()

    year_id = request.GET.get("academic_year")
    term_id = request.GET.get("term")
    employee = (
        request.GET.get("employee_number", "")
        .strip()
    )

    selected_year = (
        get_object_or_404(
            AcademicYear,
            pk=year_id,
        )
        if year_id
        else years.first()
    )

    selected_term = (
        get_object_or_404(
            Term,
            pk=term_id,
        )
        if term_id
        else terms.first()
    )

    selected_teacher = None

    if employee:

        for teacher in teachers:

            if (
                _employee_number(teacher).lower()
                == employee.lower()
            ):
                selected_teacher = teacher
                break

        if selected_teacher is None:

            messages.error(
                request,
                "No teaching employee was found with that employee number.",
            )

    report = None

    if (
        selected_teacher
        and selected_year
        and selected_term
    ):

        report = _build_report(
            selected_teacher,
            selected_year,
            selected_term,
        )

    if request.method == "POST" and selected_teacher:

        feedback = request.POST.get(
            "general_feedback",
            "",
        ).strip()

        requirements = TermlySubmissionRequirement.objects.filter(
            teacher=selected_teacher,
            academic_year=selected_year,
            term=selected_term,
        )

        for requirement in requirements:
            requirement.admin_feedback = feedback
            requirement.feedback_updated_at = timezone.now()
            requirement.save(
                update_fields=[
                    "admin_feedback",
                    "feedback_updated_at",
                    "updated_at",
                ]
            )

        messages.success(
            request,
            "Admin feedback saved successfully.",
        )

        report = _build_report(
            selected_teacher,
            selected_year,
            selected_term,
        )

    general_feedback = ""

    if selected_teacher and selected_year and selected_term:

        general_feedback = (
            TermlySubmissionRequirement.objects.filter(
                teacher=selected_teacher,
                academic_year=selected_year,
                term=selected_term,
            )
            .exclude(admin_feedback="")
            .values_list(
                "admin_feedback",
                flat=True,
            )
            .first()
            or ""
        )

    return render(
        request,
        "termly_submission/admin_report.html",
        {
            "academic_years": years,
            "terms": terms,
            "teachers": teachers,
            "selected_year": selected_year,
            "selected_term": selected_term,
            "selected_teacher": selected_teacher,
            "employee_number": employee,
            "report": report,
            "general_feedback": general_feedback,
        },
    )



