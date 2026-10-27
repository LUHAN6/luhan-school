from accounts.views import user_has_role_permission
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import UserProfile
from parents.models import Parent
from accounts.views import (
    get_staff_subjects_for_class,
    get_staff_teacher,
    is_class_teacher_for,
)
from timetable.models import TimetableSubject
from timetable.advanced_models import TimetableTeacherTeachingAssignment
from students.models import Student

from .forms import WeeklyAssessmentReportForm
from .models import WeeklyAssessmentReport, WeeklyAssessmentWeek, WeeklyReportReply


def _profile(user):
    return UserProfile.objects.filter(user=user).first()


def _is_admin(user):
    profile = _profile(user)
    return user.is_superuser or (
        profile is not None and profile.role == "ADMIN"
    )


def _is_staff(user):
    profile = _profile(user)
    return profile is not None and profile.role == "STAFF"


def _has_weekly_report_permission(user, codename):
    if _is_admin(user):
        return True
    return user_has_role_permission(
        user,
        codename,
        "weekly_reports",
    )


def _staff_can_edit_target(user, student, subject):
    if _is_admin(user):
        return True

    teacher = get_staff_teacher(user)

    if not teacher:
        return False

    # Class teachers can WRITE reports for all subjects
    # in their assigned class.
    try:
        if is_class_teacher_for(user, student.class_name):
            return True
    except Exception:
        pass

    # Subject teachers can WRITE only subjects they are
    # actively assigned to teach for this class/stream.
    try:
        assignments = TimetableTeacherTeachingAssignment.objects.filter(
            teacher=teacher,
            subject=subject,
            class_name__iexact=student.class_name,
            is_active=True,
        )

        learner_stream = (student.stream or "").strip().lower()

        for assignment in assignments:
            assigned_stream = (assignment.stream or "").strip().lower()

            # Blank stream assignment applies to all streams.
            if not assigned_stream:
                return True

            if assigned_stream == learner_stream:
                return True

    except Exception:
        pass

    return False


def _staff_can_view_report(user, report):
    if _is_admin(user):
        return True

    teacher = get_staff_teacher(user)
    if not teacher:
        return False

    student = report.student
    subject = report.subject

    # Class teachers can view ALL subjects for learners
    # in their assigned class.
    try:
        if is_class_teacher_for(user, student.class_name):
            return True
    except Exception:
        pass

    # Subject teachers can view only subjects they are
    # actively assigned to teach for this class/stream.
    try:
        assignments = TimetableTeacherTeachingAssignment.objects.filter(
            teacher=teacher,
            subject=subject,
            class_name__iexact=student.class_name,
            is_active=True,
        )

        learner_stream = (student.stream or "").strip().lower()

        for assignment in assignments:
            assigned_stream = (assignment.stream or "").strip().lower()

            # Blank stream assignment applies to all streams.
            if not assigned_stream:
                return True

            if assigned_stream == learner_stream:
                return True

    except Exception:
        pass

    return False


def _student_can_view_report(user, report):
    profile = _profile(user)
    return bool(
        profile
        and profile.student_id
        and profile.student_id == report.student_id
        and report.is_published
    )


def _parent_can_view_report(user, report):
    profile = _profile(user)
    if not profile or not report.is_published:
        return False

    try:
        parent = Parent.objects.get(user=user)
        return parent.children.filter(
            pk=report.student_id,
            is_active=True,
        ).exists()
    except Parent.DoesNotExist:
        return False


def _can_view_report(user, report):
    if _is_admin(user):
        return True

    if _is_staff(user):
        return _staff_can_view_report(user, report)

    if _student_can_view_report(user, report):
        return True

    if _parent_can_view_report(user, report):
        return True

    return False


def _can_edit_report(user, report):
    if _is_admin(user):
        return True

    if not _is_staff(user):
        return False

    return _staff_can_edit_target(
        user,
        report.student,
        report.subject,
    )


def _accessible_students_for_staff(user):
    students = list(
        Student.objects.filter(
            is_active=True
        ).order_by(
            "class_name",
            "stream",
            "last_name",
            "first_name",
        )
    )

    result = []

    for student in students:
        if _is_admin(user):
            result.append(student)
            continue

        teacher = get_staff_teacher(user)
        if not teacher:
            continue

        try:
            if is_class_teacher_for(user, student.class_name):
                result.append(student)
                continue
        except Exception:
            pass

        try:
            subjects = get_staff_subjects_for_class(
                user,
                student.class_name,
            )
            if any(subject for subject in subjects):
                result.append(student)
        except Exception:
            pass

    return result


def _subjects_for_staff(user):
    if _is_admin(user):
        return TimetableSubject.objects.all().order_by("name")

    students = _accessible_students_for_staff(user)
    class_names = {
        student.class_name
        for student in students
        if student.class_name
    }

    subject_ids = set()

    for class_name in class_names:
        try:
            if is_class_teacher_for(user, class_name):
                subject_ids.update(
                    TimetableSubject.objects.values_list(
                        "pk",
                        flat=True,
                    )
                )
                break

            subjects = get_staff_subjects_for_class(
                user,
                class_name,
            )

            for subject in subjects:
                if getattr(subject, "pk", None):
                    subject_ids.add(subject.pk)

        except Exception:
            continue

    return TimetableSubject.objects.filter(
        pk__in=subject_ids
    ).order_by("name")


def _apply_common_filters(request, queryset):
    """
    Apply filters shared by Admin, Teaching Staff,
    Student and Parent report-list views.

    Assessment Week is authoritative when supplied.
    The legacy `week` parameter remains supported as
    a fallback for older links/forms.
    """

    student_id = request.GET.get("student", "").strip()
    subject_id = request.GET.get("subject", "").strip()
    class_name = request.GET.get("class", "").strip()

    assessment_week_id = request.GET.get(
        "assessment_week",
        "",
    ).strip()

    legacy_week = request.GET.get(
        "week",
        "",
    ).strip()

    date_from = request.GET.get(
        "date_from",
        "",
    ).strip()

    date_to = request.GET.get(
        "date_to",
        "",
    ).strip()

    if student_id.isdigit():
        queryset = queryset.filter(
            student_id=int(student_id)
        )

    if subject_id.isdigit():
        queryset = queryset.filter(
            subject_id=int(subject_id)
        )

    if class_name:
        queryset = queryset.filter(
            class_name__iexact=class_name
        )

    # Assessment Week is the authoritative week filter.
    if assessment_week_id.isdigit():
        queryset = queryset.filter(
            week_id=int(assessment_week_id)
        )

    # Backward compatibility for older links/forms
    # that still send `week=<week_number>`.
    elif legacy_week.isdigit():
        queryset = queryset.filter(
            week_number=int(legacy_week)
        )

    if date_from:
        try:
            queryset = queryset.filter(
                week_start__gte=date.fromisoformat(date_from)
            )
        except ValueError:
            pass

    if date_to:
        try:
            queryset = queryset.filter(
                week_end__lte=date.fromisoformat(date_to)
            )
        except ValueError:
            pass

    return queryset


def _decorate_reports(reports):
    for report in reports:
        report.display_percentage = report.percentage
    return reports


from django.db.models import Avg



def _build_weekly_expected_matrix(
    week,
    user=None,
    students=None,
    include_all_admin=False,
):
    """
    Authoritative weekly assessment expectation matrix.

    One expected report:
        active learner + subject assigned to the learner's
        class/stream.

    Permissions:
        Admin:
            All active class/stream subject assignments.

        Class Teacher:
            All subjects assigned to the class/stream they are
            class teacher for.

        Ordinary Teaching Staff:
            Only their own active teaching assignments.

    The same matrix is used for dashboard completion and the
    weekly assessment writing workspace.
    """


    if not week:
        return {
            "expected": 0,
            "completed": 0,
            "pending": 0,
            "completion_percentage": 0,
            "rows": [],
        }

    if students is None:
        students_qs = Student.objects.filter(
            is_active=True,
        )
    else:
        students_qs = students

    students_list = list(
        students_qs.order_by(
            "class_name",
            "stream",
            "last_name",
            "first_name",
        )
    )

    assignments = list(
        TimetableTeacherTeachingAssignment.objects
        .filter(is_active=True)
        .select_related(
            "subject",
            "teacher",
        )
        .order_by(
            "class_name",
            "stream",
            "subject__name",
        )
    )

    is_admin = bool(
        user is not None and _is_admin(user)
    )

    teacher = None

    if user is not None and not is_admin:
        teacher = get_staff_teacher(user)

    # ---------------------------------------------------------
    # Build the permitted class/stream + subject map.
    # ---------------------------------------------------------
    assignment_map = {}

    for assignment in assignments:

        assignment_class = (
            assignment.class_name or ""
        ).strip()

        assignment_stream = (
            assignment.stream or ""
        ).strip()

        if not assignment_class:
            continue

        allowed = False

        if is_admin and include_all_admin:
            allowed = True

        elif teacher is not None:

            # Class teachers may enter all subjects actually
            # assigned to their class/stream.
            try:
                if is_class_teacher_for(
                    user,
                    assignment_class,
                    assignment_stream,
                ):
                    allowed = True
            except Exception:
                pass

            # Ordinary teachers may enter only their own
            # active assignment.
            if assignment.teacher_id == teacher.pk:
                allowed = True

        if not allowed:
            continue

        class_key = (
            assignment_class.lower(),
            assignment_stream.lower(),
        )

        assignment_map.setdefault(
            class_key,
            {},
        )

        # One subject per class/stream is one expected
        # weekly assessment slot, regardless of lessons_per_week.
        assignment_map[class_key][
            assignment.subject_id
        ] = assignment

    # ---------------------------------------------------------
    # Existing reports for this week.
    # ---------------------------------------------------------
    completed_keys = set(
        WeeklyAssessmentReport.objects
        .filter(
            week=week,
            student__is_active=True,
        )
        .values_list(
            "student_id",
            "subject_id",
        )
    )

    rows = []

    for student in students_list:

        class_key = (
            (student.class_name or "").strip().lower(),
            (student.stream or "").strip().lower(),
        )

        subject_assignments = assignment_map.get(
            class_key,
            {},
        )

        for assignment in subject_assignments.values():

            key = (
                student.pk,
                assignment.subject_id,
            )

            completed = key in completed_keys

            rows.append({
                "student": student,
                "subject": assignment.subject,
                "assignment": assignment,
                "completed": completed,
                "pending": not completed,
            })

    expected = len(rows)

    completed = sum(
        1
        for row in rows
        if row["completed"]
    )

    pending = expected - completed

    completion_percentage = (
        round(
            (completed / expected) * 100,
            1,
        )
        if expected
        else 0
    )

    return {
        "expected": expected,
        "completed": completed,
        "pending": pending,
        "completion_percentage": completion_percentage,
        "rows": rows,
    }


def _build_weekly_analysis(
    reports,
    trend_reports=None,
    expected_total=None,
):
    """
    Build dashboard-ready analysis data from WeeklyAssessmentReport records.

    This function does not change permissions or database structure.
    """

    reports = list(reports or [])
    trend_reports = list(
        trend_reports if trend_reports is not None else reports
    )

    scored_reports = [
        report
        for report in reports
        if report.percentage is not None
    ]

    percentages = [
        float(report.percentage)
        for report in scored_reports
    ]

    total_reports = len(reports)

    learners = {
        report.student_id
        for report in reports
        if report.student_id
    }

    subjects = {
        report.subject_id
        for report in reports
        if report.subject_id
    }

    classes = {
        (report.class_name or "").strip()
        for report in reports
        if (report.class_name or "").strip()
    }

    average_score = (
        round(sum(percentages) / len(percentages), 1)
        if percentages
        else 0
    )

    highest_score = max(percentages) if percentages else 0
    lowest_score = min(percentages) if percentages else 0

    completion_percentage = (
        round((total_reports / expected_total) * 100, 1)
        if expected_total
        else 0
    )

    if completion_percentage > 100:
        completion_percentage = 100

    # ---------------------------------------------------------
    # PERFORMANCE BY SUBJECT
    # ---------------------------------------------------------

    subject_groups = {}

    for report in scored_reports:
        subject_name = getattr(
            report.subject,
            "name",
            str(report.subject),
        )

        subject_groups.setdefault(
            subject_name,
            [],
        ).append(float(report.percentage))

    subject_performance = []

    for subject_name, values in subject_groups.items():
        subject_performance.append({
            "name": subject_name,
            "average": round(
                sum(values) / len(values),
                1,
            ),
            "count": len(values),
        })

    subject_performance.sort(
        key=lambda item: item["average"],
        reverse=True,
    )

    # ---------------------------------------------------------
    # PERFORMANCE BY CLASS
    # ---------------------------------------------------------

    class_groups = {}

    for report in scored_reports:
        class_name = (
            report.class_name
            or getattr(report.student, "class_name", "")
            or "Unassigned"
        )

        class_groups.setdefault(
            class_name,
            [],
        ).append(float(report.percentage))

    class_performance = []

    for class_name, values in class_groups.items():
        class_performance.append({
            "name": class_name,
            "average": round(
                sum(values) / len(values),
                1,
            ),
            "count": len(values),
        })

    class_performance.sort(
        key=lambda item: item["average"],
        reverse=True,
    )

    # ---------------------------------------------------------
    # WEEKLY PERFORMANCE TREND
    # ---------------------------------------------------------

    week_groups = {}

    for report in trend_reports:
        if report.percentage is None:
            continue

        week_key = (
            report.week_number,
            report.week_start,
            report.week_end,
        )

        week_groups.setdefault(
            week_key,
            [],
        ).append(float(report.percentage))

    weekly_trend = []

    for (
        week_number,
        week_start,
        week_end,
    ), values in sorted(
        week_groups.items(),
        key=lambda item: item[0][1],
    ):
        weekly_trend.append({
            "label": f"Week {week_number}",
            "week_number": week_number,
            "start": week_start.strftime("%d %b %Y"),
            "end": week_end.strftime("%d %b %Y"),
            "average": round(
                sum(values) / len(values),
                1,
            ),
            "count": len(values),
        })

    # ---------------------------------------------------------
    # SCORE DISTRIBUTION
    # ---------------------------------------------------------

    score_bands = [
        {
            "label": "80â€“100%",
            "min": 80,
            "max": 100,
            "count": 0,
        },
        {
            "label": "60â€“79%",
            "min": 60,
            "max": 79.99,
            "count": 0,
        },
        {
            "label": "40â€“59%",
            "min": 40,
            "max": 59.99,
            "count": 0,
        },
        {
            "label": "0â€“39%",
            "min": 0,
            "max": 39.99,
            "count": 0,
        },
    ]

    for percentage in percentages:
        for band in score_bands:
            if band["min"] <= percentage <= band["max"]:
                band["count"] += 1
                break

    # ---------------------------------------------------------
    # SUBMISSION STATUS
    # ---------------------------------------------------------

    submitted = total_reports

    if expected_total is None:
        expected_total = submitted

    pending = max(
        int(expected_total) - submitted,
        0,
    )

    submission_status = [
        {
            "label": "Submitted",
            "value": submitted,
        },
        {
            "label": "Pending",
            "value": pending,
        },
    ]

    return {
        "total_reports": total_reports,
        "learners_assessed": len(learners),
        "subjects_assessed": len(subjects),
        "classes_assessed": len(classes),
        "average_score": average_score,
        "highest_score": round(highest_score, 1),
        "lowest_score": round(lowest_score, 1),
        "completion_percentage": completion_percentage,
        "expected_total": int(expected_total or 0),
        "submitted_total": submitted,
        "pending_total": pending,
        "subject_performance": subject_performance,
        "class_performance": class_performance,
        "weekly_trend": weekly_trend,
        "score_bands": score_bands,
        "submission_status": submission_status,
    }


# ============================================================
# WEEK MANAGEMENT
# ============================================================

@login_required
def manage_weeks(request):
    if not _is_admin(request.user):
        return HttpResponseForbidden("Administrator access required.")

    weeks = WeeklyAssessmentWeek.objects.select_related(
        "academic_year",
        "term",
        "created_by",
        "locked_by",
    ).order_by("-week_start", "-week_number")

    return render(
        request,
        "weekly_reports/manage_weeks.html",
        {
            "weeks": weeks,
            "portal_title": "Manage Assessment Weeks",
        },
    )


@login_required
def week_create(request):
    if not _is_admin(request.user):
        return HttpResponseForbidden("Administrator access required.")

    from fees.models import AcademicYear, Term

    if request.method == "POST":
        academic_year_id = request.POST.get("academic_year")
        term_id = request.POST.get("term")
        week_number = request.POST.get("week_number")
        title = request.POST.get("title", "").strip()
        week_start = request.POST.get("week_start")
        week_end = request.POST.get("week_end")
        description = request.POST.get("description", "").strip()

        try:
            week = WeeklyAssessmentWeek(
                academic_year_id=academic_year_id,
                term_id=term_id,
                week_number=int(week_number),
                title=title,
                week_start=week_start,
                week_end=week_end,
                description=description,
                created_by=request.user,
            )
            week.full_clean()
            week.save()
            messages.success(request, f"{week.display_title} created successfully.")
            return redirect("weekly_reports:manage_weeks")
        except Exception as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "weekly_reports/week_form.html",
        {
            "academic_years": AcademicYear.objects.all().order_by("-year"),
            "terms": Term.objects.all().order_by("-id"),
            "week": None,
            "portal_title": "Add Assessment Week",
        },
    )


@login_required
def week_edit(request, pk):
    if not _is_admin(request.user):
        return HttpResponseForbidden("Administrator access required.")

    from fees.models import AcademicYear, Term

    week = get_object_or_404(WeeklyAssessmentWeek, pk=pk)

    if week.is_locked:
        messages.warning(
            request,
            "This week is locked. Unlock it before editing."
        )
        return redirect("weekly_reports:manage_weeks")

    if request.method == "POST":
        week.academic_year_id = request.POST.get("academic_year")
        week.term_id = request.POST.get("term")
        week.week_number = int(request.POST.get("week_number"))
        week.title = request.POST.get("title", "").strip()
        week.week_start = request.POST.get("week_start")
        week.week_end = request.POST.get("week_end")
        week.description = request.POST.get("description", "").strip()

        try:
            week.full_clean()
            week.save()
            messages.success(request, "Assessment week updated successfully.")
            return redirect("weekly_reports:manage_weeks")
        except Exception as exc:
            messages.error(request, str(exc))

    return render(
        request,
        "weekly_reports/week_form.html",
        {
            "academic_years": AcademicYear.objects.all().order_by("-year"),
            "terms": Term.objects.all().order_by("-id"),
            "week": week,
            "portal_title": "Edit Assessment Week",
        },
    )


@login_required
def week_lock(request, pk):
    if not _is_admin(request.user):
        return HttpResponseForbidden("Administrator access required.")

    week = get_object_or_404(WeeklyAssessmentWeek, pk=pk)

    if request.method != "POST":
        return redirect("weekly_reports:manage_weeks")

    week.is_locked = True
    week.locked_by = request.user
    week.locked_at = timezone.now()
    week.save(update_fields=["is_locked", "locked_by", "locked_at", "updated_at"])

    messages.success(
        request,
        f"{week.display_title} has been locked. Teachers can no longer enter or edit reports for this week.",
    )
    return redirect("weekly_reports:manage_weeks")


@login_required
def week_unlock(request, pk):
    if not _is_admin(request.user):
        return HttpResponseForbidden("Administrator access required.")

    week = get_object_or_404(WeeklyAssessmentWeek, pk=pk)

    if request.method != "POST":
        return redirect("weekly_reports:manage_weeks")

    week.is_locked = False
    week.locked_by = None
    week.locked_at = None
    week.save(update_fields=["is_locked", "locked_by", "locked_at", "updated_at"])

    messages.success(
        request,
        f"{week.display_title} has been unlocked.",
    )
    return redirect("weekly_reports:manage_weeks")


@login_required
def reports_dashboard(request):
    """
    Route the old shared Weekly Reports dashboard link
    to the correct portal.
    """
    if _is_admin(request.user):
        return redirect("weekly_reports:admin_reports")

    if _is_staff(request.user):
        return redirect("weekly_reports:staff_reports")

    profile = _profile(request.user)

    if profile and profile.student_id:
        return redirect("weekly_reports:student_reports")

    try:
        if profile:
            parent = Parent.objects.get(user=request.user)
            if parent.children.filter(is_active=True).exists():
                return redirect("weekly_reports:parent_reports")
    except Parent.DoesNotExist:
        pass

    return HttpResponseForbidden(
        "Your account is not configured for Weekly Assessment Reports."
    )


@login_required
def admin_reports(request):
    if not _is_admin(request.user):
        return HttpResponseForbidden(
            "Administrator access required."
        )

    weeks = (
        WeeklyAssessmentWeek.objects
        .select_related("academic_year", "term")
        .order_by("-week_start", "-week_number")
    )

    selected_week_id = request.GET.get(
        "assessment_week",
        ""
    ).strip()

    selected_week = None

    if selected_week_id:
        selected_week = weeks.filter(
            pk=selected_week_id
        ).first()

    queryset = (
        WeeklyAssessmentReport.objects
        .select_related(
            "student",
            "subject",
            "created_by",
            "updated_by",
            "week",
        )
        .prefetch_related(
            "replies__author",
        )
    )

    # Assessment Week is the primary filter.
    if selected_week:
        queryset = queryset.filter(
            week=selected_week
        )
    elif selected_week_id:
        # Prevent an invalid week id from silently
        # returning unrelated reports.
        queryset = queryset.none()

    # Explicit Admin class filter.
    selected_class = request.GET.get(
        "class",
        ""
    ).strip()

    if selected_class:
        queryset = queryset.filter(
            class_name__iexact=selected_class
        )

    # Explicit Admin subject filter.
    selected_subject_id = request.GET.get(
        "subject",
        ""
    ).strip()

    if selected_subject_id:
        try:
            queryset = queryset.filter(
                subject_id=int(selected_subject_id)
            )
        except (TypeError, ValueError):
            queryset = queryset.none()

    # Preserve the remaining common filters.
    queryset = _apply_common_filters(
        request,
        queryset,
    )

    reports = _decorate_reports(
        list(queryset)
    )

    # ---------------------------------------------------------
    # Dashboard analysis data
    # ---------------------------------------------------------
    admin_trend_queryset = (
        WeeklyAssessmentReport.objects
        .select_related(
            "student",
            "subject",
            "week",
        )
    )

    admin_trend_queryset = _apply_common_filters(
        request,
        admin_trend_queryset,
    )

    trend_reports = _decorate_reports(
        list(admin_trend_queryset)
    )

    students = (
        Student.objects
        .filter(is_active=True)
        .order_by(
            "class_name",
            "stream",
            "last_name",
            "first_name",
        )
    )

    subjects = (
        TimetableSubject.objects
        .all()
        .order_by("name")
    )

    classes = (
        Student.objects
        .filter(is_active=True)
        .values_list(
            "class_name",
            flat=True,
        )
        .distinct()
        .order_by("class_name")
    )

    active_weeks = weeks.filter(
        is_locked=False
    )

    submission_stats = []

    if selected_week:
        matrix = _build_weekly_expected_matrix(
            selected_week,
            user=request.user,
            students=Student.objects.filter(
                is_active=True,
            ),
            include_all_admin=True,
        )

        grouped = {}

        for row in matrix["rows"]:
            student = row["student"]

            class_name = (
                student.class_name or "Unassigned"
            ).strip()

            stream = (
                student.stream or ""
            ).strip()

            key = (
                class_name.lower(),
                stream.lower(),
            )

            if key not in grouped:
                grouped[key] = {
                    "class_name": class_name,
                    "stream": stream,
                    "learners": set(),
                    "expected": 0,
                    "submitted": 0,
                }

            grouped[key]["learners"].add(
                student.pk
            )

            grouped[key]["expected"] += 1

            if row["completed"]:
                grouped[key]["submitted"] += 1

        for item in sorted(
            grouped.values(),
            key=lambda x: (
                x["class_name"],
                x["stream"],
            ),
        ):
            expected = item["expected"]
            submitted = item["submitted"]
            pending = expected - submitted

            percentage = (
                round(
                    (submitted / expected) * 100,
                    1,
                )
                if expected
                else 0
            )

            submission_stats.append({
                "class_name": item["class_name"],
                "stream": item["stream"],
                "learners": len(item["learners"]),
                "expected": expected,
                "submitted": submitted,
                "pending": pending,
                "percentage": percentage,
            })

    return render(
        request,
        "weekly_reports/report_list.html",
        {
            "reports": reports,
            "students": students,
            "subjects": subjects,
            "classes": classes,
            "weeks": weeks,
            "active_weeks": active_weeks,
            "selected_week": selected_week,

            "selected_class": selected_class,
            "selected_subject_id": selected_subject_id,

            "submission_stats": submission_stats,

            "analysis": _build_weekly_analysis(
                reports,
                trend_reports=trend_reports,
                expected_total=(
                    sum(
                        item["expected"]
                        for item in submission_stats
                    )
                    if selected_week
                    else None
                ),
            ),

            "portal": "admin",
            "portal_title": "Weekly Assessment Reports",
            "can_create": True,
            "can_edit": True,
        },
    )


@login_required
def staff_reports(request):
    # Module access is controlled by:
    # Admin Portal -> Custom Role -> Django Permission.
    if not _has_weekly_report_permission(
        request.user,
        "view_weeklyassessmentreport",
    ):
        return HttpResponseForbidden(
            "You do not have permission to access Weekly Reports."
        )

    if not _is_staff(request.user):
        return HttpResponseForbidden("Teaching staff access required.")

    # Only assessment weeks created by Admin are used.
    weeks = (
        WeeklyAssessmentWeek.objects
        .select_related("academic_year", "term")
        .order_by("-week_start", "-week_number")
    )

    selected_week_id = request.GET.get("assessment_week", "").strip()

    selected_week = None

    if selected_week_id:
        selected_week = weeks.filter(pk=selected_week_id).first()

    # Default to the latest active/unlocked week.
    if not selected_week:
        selected_week = (
            weeks
            .filter(is_locked=False)
            .order_by("-week_start", "-week_number")
            .first()
        )

    # Teacher's permitted learners and subjects.
    students = _accessible_students_for_staff(request.user)
    subjects = _subjects_for_staff(request.user)

    classes = sorted(
        {
            student.class_name
            for student in students
            if student.class_name
        }
    )

    # Optional filters.
    selected_class = request.GET.get("class", "").strip()
    selected_subject_id = request.GET.get("subject", "").strip()

    if selected_class:
        students = [student for student in students if (student.class_name or "").lower() == selected_class.lower()]

    if selected_subject_id:
        try:
            subjects = subjects.filter(pk=int(selected_subject_id))
        except (TypeError, ValueError):
            selected_subject_id = ""

    # Reports visible to this teacher.
    queryset = (
        WeeklyAssessmentReport.objects
        .select_related(
            "student",
            "subject",
            "created_by",
            "week",
        )
    )

    if selected_week:
        queryset = queryset.filter(
            week=selected_week
        )

    queryset = _apply_common_filters(
        request,
        queryset,
    )

    reports = [
        report
        for report in queryset
        if _staff_can_view_report(request.user, report)
    ]

    reports = _decorate_reports(reports)

    # ---------------------------------------------------------
    # Permission-safe historical trend data.
    # ---------------------------------------------------------
    staff_trend_queryset = (
        WeeklyAssessmentReport.objects
        .select_related(
            "student",
            "subject",
            "week",
        )
    )

    staff_trend_queryset = _apply_common_filters(
        request,
        staff_trend_queryset,
    )

    staff_trend_reports = [
        report
        for report in staff_trend_queryset
        if _staff_can_view_report(
            request.user,
            report,
        )
    ]

    # ---------------------------------------------------------
    # Submission statistics by subject and class.
    # ---------------------------------------------------------
    submission_stats = []

    if selected_week:
        teacher_student_ids = [student.id for student in students]

        teacher_subject_ids = list(subjects.values_list("id", flat=True))

        for subject in subjects:

            subject_students = students

            expected = len(subject_students)

            submitted = WeeklyAssessmentReport.objects.filter(
                week=selected_week,
                subject=subject,
                student_id__in=teacher_student_ids,
            ).count()

            percentage = (
                round((submitted / expected) * 100, 1)
                if expected
                else 0
            )

            submission_stats.append({
                "subject": subject,
                "class_name": selected_class or "All Classes",
                "learners": expected,
                "expected": expected,
                "submitted": submitted,
                "percentage": percentage,
            })

    # ---------------------------------------------------------
    # Class + subject breakdown.
    # This lets a teacher see completion separately for each
    # class they teach rather than mixing all classes together.
    # ---------------------------------------------------------
    class_subject_stats = []

    if selected_week:
        for class_name in classes:

            if selected_class and (
                class_name.lower() != selected_class.lower()
            ):
                continue

            class_students = [student for student in students if (student.class_name or "").lower() == class_name.lower()]

            for subject in subjects:

                expected = len(class_students)

                if expected == 0:
                    continue

                submitted = WeeklyAssessmentReport.objects.filter(
                    week=selected_week,
                    subject=subject,
                    student_id__in=[student.id for student in class_students],
                ).count()

                percentage = round(
                    (submitted / expected) * 100,
                    1,
                )

                class_subject_stats.append({
                    "class_name": class_name,
                    "subject": subject,
                    "learners": expected,
                    "expected": expected,
                    "submitted": submitted,
                    "percentage": percentage,
                })

    return render(
        request,
        "weekly_reports/report_list.html",
        {
            "reports": reports,
            "students": students,
            "subjects": subjects,
            "classes": classes,

            "weeks": weeks,
            "active_weeks": weeks.filter(is_locked=False),
            "selected_week": selected_week,

            "submission_stats": submission_stats,
            "class_subject_stats": class_subject_stats,

            "analysis": _build_weekly_analysis(
                reports,
                trend_reports=staff_trend_reports,
                expected_total=(
                    sum(
                        item["expected"]
                        for item in submission_stats
                    )
                    if selected_week
                    else None
                ),
            ),

            "selected_class": selected_class,
            "selected_subject_id": selected_subject_id,

            "portal": "staff",
            "portal_title": "Weekly Assessment Reports",
            "can_create": True,
            "can_edit": True,
        },
    )

@login_required
def student_reports(request):
    profile = _profile(request.user)

    if not profile or not profile.student_id:
        return HttpResponseForbidden(
            "Student account is not linked to a learner."
        )

    weeks = (
        WeeklyAssessmentWeek.objects
        .select_related("academic_year", "term")
        .filter(is_locked=False)
        .order_by("-week_start", "-week_number")
    )

    selected_week_id = request.GET.get(
        "assessment_week",
        ""
    ).strip()

    selected_week = None

    if selected_week_id:
        selected_week = weeks.filter(
            pk=selected_week_id
        ).first()

    queryset = WeeklyAssessmentReport.objects.filter(
        student_id=profile.student_id,
        is_published=True,
    ).select_related(
        "student",
        "subject",
        "created_by",
        "week",
    )

    if selected_week:
        queryset = queryset.filter(
            week=selected_week
        )

    queryset = _apply_common_filters(
        request,
        queryset,
    )

    reports = _decorate_reports(list(queryset))

    subjects = TimetableSubject.objects.filter(
        weekly_assessment_reports__student_id=profile.student_id,
        weekly_assessment_reports__is_published=True,
    ).distinct().order_by("name")

    # ---------------------------------------------------------
    # Student historical analysis.
    # Only this learner's published reports from unlocked
    # assessment weeks are included.
    # ---------------------------------------------------------
    student_trend_queryset = (
        WeeklyAssessmentReport.objects
        .filter(
            student_id=profile.student_id,
            is_published=True,
            week__is_locked=False,
        )
        .select_related(
            "student",
            "subject",
            "week",
        )
    )

    student_trend_reports = _decorate_reports(
        list(student_trend_queryset)
    )

    analysis = _build_weekly_analysis(
        reports,
        trend_reports=student_trend_reports,
        expected_total=(
            subjects.count()
            if selected_week
            else None
        ),
    )

    return render(
        request,
        "weekly_reports/report_list.html",
        {
            "reports": reports,
            "students": [],
            "subjects": subjects,
            "classes": [],
            "weeks": weeks,
            "active_weeks": weeks,
            "selected_week": selected_week,
            "selected_subject_id": request.GET.get(
                "subject",
                ""
            ),
            "analysis": analysis,

            "portal": "student",
            "portal_title": "My Weekly Assessment Reports",
            "can_create": False,
            "can_edit": False,
        },
    )


@login_required
def parent_reports(request):
    profile = _profile(request.user)

    if not profile:
        return HttpResponseForbidden(
            "Parent account not found."
        )

    try:
        parent = Parent.objects.get(
            user=request.user
        )

        children = parent.children.filter(
            is_active=True
        ).order_by(
            "class_name",
            "stream",
            "last_name",
            "first_name",
        )

    except Parent.DoesNotExist:
        return HttpResponseForbidden(
            "Parent account not found."
        )

    child_ids = list(
        children.values_list(
            "pk",
            flat=True,
        )
    )

    weeks = (
        WeeklyAssessmentWeek.objects
        .select_related("academic_year", "term")
        .filter(is_locked=False)
        .order_by("-week_start", "-week_number")
    )

    selected_week_id = request.GET.get(
        "assessment_week",
        ""
    ).strip()

    selected_week = None

    if selected_week_id:
        selected_week = weeks.filter(
            pk=selected_week_id
        ).first()

    queryset = WeeklyAssessmentReport.objects.filter(
        student_id__in=child_ids,
        is_published=True,
    ).select_related(
        "student",
        "subject",
        "created_by",
        "week",
    )

    if selected_week:
        queryset = queryset.filter(
            week=selected_week
        )

    queryset = _apply_common_filters(
        request,
        queryset,
    )

    reports = _decorate_reports(list(queryset))

    subjects = TimetableSubject.objects.filter(
        weekly_assessment_reports__student_id__in=child_ids,
        weekly_assessment_reports__is_published=True,
    ).distinct().order_by("name")

    # ---------------------------------------------------------
    # Parent historical analysis.
    # Only published reports belonging to the parent's
    # active children from unlocked weeks are included.
    # ---------------------------------------------------------
    parent_trend_queryset = (
        WeeklyAssessmentReport.objects
        .filter(
            student_id__in=child_ids,
            is_published=True,
            week__is_locked=False,
        )
        .select_related(
            "student",
            "subject",
            "week",
        )
    )

    parent_trend_reports = _decorate_reports(
        list(parent_trend_queryset)
    )

    analysis = _build_weekly_analysis(
        reports,
        trend_reports=parent_trend_reports,
        expected_total=(
            subjects.count() * len(children)
            if selected_week
            else None
        ),
    )

    return render(
        request,
        "weekly_reports/report_list.html",
        {
            "reports": reports,
            "students": children,
            "subjects": subjects,
            "classes": [],
            "weeks": weeks,
            "active_weeks": weeks,
            "selected_week": selected_week,
            "selected_subject_id": request.GET.get(
                "subject",
                ""
            ),
            "analysis": analysis,

            "portal": "parent",
            "portal_title": "Weekly Assessment Reports",
            "can_create": False,
            "can_edit": False,
        },
    )


@login_required
def report_create(request):
    if _is_admin(request.user):
        pass
    elif _is_staff(request.user):
        if not _has_weekly_report_permission(
            request.user,
            "add_weeklyassessmentreport",
        ):
            return HttpResponseForbidden(
                "You do not have permission to create reports."
            )
    else:
        return HttpResponseForbidden(
            "You do not have permission to create reports."
        )

    if request.method == "POST":
        form = WeeklyAssessmentReportForm(
            request.user,
            request.POST,
        )

        if form.is_valid():
            report = form.save(commit=False)

            report.class_name = (
                report.student.class_name or ""
            )
            report.stream = (
                report.student.stream or ""
            )

            report.created_by = request.user
            report.updated_by = request.user
            report.save()

            messages.success(
                request,
                "Weekly assessment report saved successfully.",
            )

            return redirect(
                "weekly_reports:detail",
                pk=report.pk,
            )
    else:
        form = WeeklyAssessmentReportForm(
            request.user
        )

    return render(
        request,
        "weekly_reports/report_form.html",
        {
            "form": form,
            "mode": "create",
            "portal": "admin" if _is_admin(request.user) else "staff",
            "title": "Write Weekly Assessment Report",
        },
    )


@login_required
def report_edit(request, pk):
    report = get_object_or_404(
        WeeklyAssessmentReport.objects.select_related(
            "student",
            "subject",
        ),
        pk=pk,
    )

    if _is_admin(request.user):
        can_edit = True
    elif _is_staff(request.user):
        can_edit = (
            _has_weekly_report_permission(
                request.user,
                "change_weeklyassessmentreport",
            )
            and _can_edit_report(request.user, report)
        )
    else:
        can_edit = False

    if not can_edit:
        return HttpResponseForbidden(
            "You do not have permission to edit this report."
        )

    if request.method == "POST":
        form = WeeklyAssessmentReportForm(
            request.user,
            request.POST,
            instance=report,
        )

        if form.is_valid():
            updated = form.save(commit=False)

            # Preserve the historical class snapshot.
            updated.class_name = report.class_name
            updated.stream = report.stream
            updated.updated_by = request.user
            updated.save()

            messages.success(
                request,
                "Weekly assessment report updated successfully.",
            )

            return redirect(
                "weekly_reports:detail",
                pk=report.pk,
            )
    else:
        form = WeeklyAssessmentReportForm(
            request.user,
            instance=report,
        )

    return render(
        request,
        "weekly_reports/report_form.html",
        {
            "form": form,
            "mode": "edit",
            "portal": "admin" if _is_admin(request.user) else "staff",
            "title": "Edit Weekly Assessment Report",
            "report": report,
        },
    )


@login_required
def report_detail(request, pk):
    report = get_object_or_404(
        WeeklyAssessmentReport.objects.select_related(
            "student",
            "subject",
            "created_by",
            "updated_by",
        ),
        pk=pk,
    )

    if _is_admin(request.user):
        can_view = True
    elif _is_staff(request.user):
        can_view = (
            _has_weekly_report_permission(
                request.user,
                "view_weeklyassessmentreport",
            )
            and _staff_can_view_report(
                request.user,
                report,
            )
        )
    else:
        can_view = _can_view_report(request.user, report)

    if not can_view:
        return HttpResponseForbidden(
            "You do not have permission to view this report."
        )

    replies = report.replies.select_related(
        "author"
    ).all()

    can_reply = (
        _is_admin(request.user)
        or (
            _is_staff(request.user)
            and _staff_can_view_report(
                request.user,
                report,
            )
        )
        or _student_can_view_report(
            request.user,
            report,
        )
        or _parent_can_view_report(
            request.user,
            report,
        )
    )

    return render(
        request,
        "weekly_reports/report_detail.html",
        {
            "report": report,
            "replies": replies,
            "can_reply": can_reply,
            "can_edit": _can_edit_report(
                request.user,
                report,
            ),
            "is_admin": _is_admin(request.user),
            "is_staff": _is_staff(request.user),
        },
    )


@login_required
def report_reply(request, pk):
    report = get_object_or_404(
        WeeklyAssessmentReport,
        pk=pk,
    )

    can_reply = (
        _is_admin(request.user)
        or (
            _is_staff(request.user)
            and _staff_can_view_report(
                request.user,
                report,
            )
        )
        or _student_can_view_report(
            request.user,
            report,
        )
        or _parent_can_view_report(
            request.user,
            report,
        )
    )

    if not can_reply:
        return HttpResponseForbidden(
            "You do not have permission to reply to this report."
        )

    if request.method != "POST":
        return redirect(
            "weekly_reports:detail",
            pk=pk,
        )

    message = request.POST.get(
        "message",
        "",
    ).strip()

    if not message:
        messages.error(
            request,
            "Please enter a reply.",
        )
        return redirect(
            "weekly_reports:detail",
            pk=pk,
        )

    WeeklyReportReply.objects.create(
        report=report,
        author=request.user,
        message=message,
    )

    messages.success(
        request,
        "Your reply has been added.",
    )

    return redirect(
        "weekly_reports:detail",
        pk=pk,
    )














