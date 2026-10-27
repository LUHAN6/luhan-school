from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render

from students.models import Student
from timetable.models import TimetableSubject
from timetable.advanced_models import TimetableTeacherTeachingAssignment

from .models import (
    WeeklyAssessmentReport,
    WeeklyAssessmentWeek,
)

from .views import (
    _is_staff,
    _is_admin,
    get_staff_teacher,
    is_class_teacher_for,
)


def _parse_class(value):
    parts = (value or "").split("||", 1)

    class_name = parts[0].strip()

    stream = (
        parts[1].strip()
        if len(parts) > 1
        else ""
    )

    return class_name, stream


def _teacher_classes(user):
    """
    Return only class/stream combinations the teacher
    is actually authorized to work with.

    Class teachers:
        Their class/stream.

    Ordinary teachers:
        Their active teaching assignments.
    """

    teacher = get_staff_teacher(user)

    if not teacher:
        return []

    assignments = list(
        TimetableTeacherTeachingAssignment.objects
        .filter(
            teacher=teacher,
            is_active=True,
        )
        .order_by(
            "class_name",
            "stream",
        )
    )

    seen = set()
    result = []

    # ---------------------------------------------------------
    # Direct teaching assignments.
    # ---------------------------------------------------------
    for assignment in assignments:

        class_name = (
            assignment.class_name or ""
        ).strip()

        stream = (
            assignment.stream or ""
        ).strip()

        if not class_name:
            continue

        key = (
            class_name.lower(),
            stream.lower(),
        )

        if key in seen:
            continue

        seen.add(key)

        result.append({
            "value": f"{class_name}||{stream}",
            "class_name": class_name,
            "stream": stream,
            "label": (
                f"{class_name} — {stream}"
                if stream
                else class_name
            ),
        })

    # ---------------------------------------------------------
    # Class-teacher assignments may exist separately from
    # teaching assignments, so inspect active learner groups.
    # ---------------------------------------------------------
    students = (
        Student.objects
        .filter(is_active=True)
        .values_list(
            "class_name",
            "stream",
        )
        .distinct()
        .order_by(
            "class_name",
            "stream",
        )
    )

    for class_name, stream in students:

        class_name = (
            class_name or ""
        ).strip()

        stream = (
            stream or ""
        ).strip()

        if not class_name:
            continue

        try:
            class_teacher = is_class_teacher_for(
                user,
                class_name,
                stream,
            )
        except Exception:
            class_teacher = False

        if not class_teacher:
            continue

        key = (
            class_name.lower(),
            stream.lower(),
        )

        if key in seen:
            continue

        seen.add(key)

        result.append({
            "value": f"{class_name}||{stream}",
            "class_name": class_name,
            "stream": stream,
            "label": (
                f"{class_name} — {stream}"
                if stream
                else class_name
            ),
        })

    result.sort(
        key=lambda item: (
            item["class_name"].lower(),
            item["stream"].lower(),
        )
    )

    return result


def _teacher_can_class(
    user,
    class_name,
    stream="",
):
    """
    Server-side authorization for a class/stream.
    """

    teacher = get_staff_teacher(user)

    if not teacher or not class_name:
        return False

    class_name = class_name.strip()
    stream = stream.strip()

    try:
        if is_class_teacher_for(
            user,
            class_name,
            stream,
        ):
            return True
    except Exception:
        pass

    return TimetableTeacherTeachingAssignment.objects.filter(
        teacher=teacher,
        class_name__iexact=class_name,
        stream__iexact=stream,
        is_active=True,
    ).exists()


def _teacher_subjects(
    user,
    class_name,
    stream="",
):
    """
    Return subjects the teacher may write for this
    exact class/stream.

    Class teacher:
        All subjects actually assigned to that class/stream.

    Ordinary teacher:
        Only their own active assignments.
    """

    if not class_name:
        return TimetableSubject.objects.none()

    teacher = get_staff_teacher(user)

    if not teacher:
        return TimetableSubject.objects.none()

    class_name = class_name.strip()
    stream = stream.strip()

    # ---------------------------------------------------------
    # Class teacher: use actual assignments for the class.
    # Never use TimetableSubject.objects.all().
    # ---------------------------------------------------------
    try:
        if is_class_teacher_for(
            user,
            class_name,
            stream,
        ):
            subject_ids = (
                TimetableTeacherTeachingAssignment.objects
                .filter(
                    class_name__iexact=class_name,
                    stream__iexact=stream,
                    is_active=True,
                )
                .values_list(
                    "subject_id",
                    flat=True,
                )
                .distinct()
            )

            return TimetableSubject.objects.filter(
                pk__in=subject_ids,
            ).order_by("name")
    except Exception:
        pass

    # ---------------------------------------------------------
    # Ordinary teacher: only their assignments.
    # ---------------------------------------------------------
    subject_ids = (
        TimetableTeacherTeachingAssignment.objects
        .filter(
            teacher=teacher,
            class_name__iexact=class_name,
            stream__iexact=stream,
            is_active=True,
        )
        .values_list(
            "subject_id",
            flat=True,
        )
        .distinct()
    )

    return TimetableSubject.objects.filter(
        pk__in=subject_ids,
    ).order_by("name")


def _students_for_class(
    user,
    class_name,
    stream="",
):
    if not _teacher_can_class(
        user,
        class_name,
        stream,
    ):
        return Student.objects.none()

    qs = Student.objects.filter(
        is_active=True,
        class_name__iexact=class_name,
    )

    if stream:
        qs = qs.filter(
            stream__iexact=stream,
        )

    return qs.order_by(
        "last_name",
        "first_name",
        "middle_name",
    )


def _authorized_subject(
    user,
    class_name,
    stream,
    subject_id,
):
    if not str(subject_id).isdigit():
        return None

    allowed = _teacher_subjects(
        user,
        class_name,
        stream,
    )

    return allowed.filter(
        pk=int(subject_id),
    ).first()


def _write_rows(
    user,
    week,
    class_name,
    stream,
    subject,
):
    """
    Build the learner rows used by the class workspace.

    Existing reports are preloaded.
    Missing reports are marked Pending.
    """

    students = _students_for_class(
        user,
        class_name,
        stream,
    )

    existing = {
        report.student_id: report
        for report in (
            WeeklyAssessmentReport.objects
            .filter(
                week=week,
                subject=subject,
                student__in=students,
            )
            .select_related(
                "student",
            )
        )
    }

    rows = []

    for student in students:

        report = existing.get(
            student.pk
        )

        rows.append({
            "student": student,
            "report": report,
            "completed": report is not None,
            "pending": report is None,
        })

    return rows


@login_required
def staff_write(request):

    if not _is_staff(request.user):
        return HttpResponseForbidden(
            "Teaching staff access required."
        )

    weeks = (
        WeeklyAssessmentWeek.objects
        .filter(is_locked=False)
        .select_related(
            "academic_year",
            "term",
        )
        .order_by(
            "-week_start",
            "-week_number",
        )
    )

    classes = _teacher_classes(
        request.user
    )

    mode = request.GET.get(
        "mode",
        "",
    )

    context = {
        "portal": "staff",
        "mode": mode,
        "weeks": weeks,
        "classes": classes,
        "students": [],
        "subjects": TimetableSubject.objects.none(),
        "rows": [],
        "selected_class": "",
        "selected_stream": "",
        "selected_week": "",
        "selected_subject": "",
        "selected_week_object": None,
        "can_use_all_subjects": False,
        "all_subjects": False,
        "all_subject_rows": [],
        "selected_subject_object": None,
        "selected_student": None,
        "individual_all_subject_rows": [],
    }

    class_value = request.GET.get(
        "class",
        "",
    )

    class_name, stream = _parse_class(
        class_value
    )

    week_id = request.GET.get(
        "week",
        "",
    )

    subject_id = request.GET.get(
        "subject",
        "",
    )

    student_id = request.GET.get(
        "student",
        "",
    )

    selected_is_class_teacher = False

    if class_name:
        try:
            selected_is_class_teacher = is_class_teacher_for(
                request.user,
                class_name,
                stream,
            )
        except Exception:
            selected_is_class_teacher = False

    all_subjects = subject_id.lower() == "all"

    context["selected_class"] = class_name
    context["selected_stream"] = stream
    context["selected_week"] = week_id
    context["selected_subject"] = subject_id
    context["can_use_all_subjects"] = selected_is_class_teacher
    context["all_subjects"] = all_subjects
    context["all_subjects"] = all_subjects
    context["all_subject_rows"] = []

    if all_subjects and not selected_is_class_teacher:
        all_subjects = False
        context["all_subjects"] = False

    if class_name and _teacher_can_class(
        request.user,
        class_name,
        stream,
    ):

        context["subjects"] = _teacher_subjects(
            request.user,
            class_name,
            stream,
        )

        context["students"] = _students_for_class(
            request.user,
            class_name,
            stream,
        )

        if student_id.isdigit():
            context["selected_student"] = (
                context["students"]
                .filter(pk=int(student_id))
                .first()
            )

    if week_id.isdigit():

        week = WeeklyAssessmentWeek.objects.filter(
            pk=int(week_id)
        ).first()

        context["selected_week_object"] = week

        if (
            week
            and all_subjects
            and context.get("selected_student") is not None
        ):
            selected_student = context["selected_student"]

            subjects = list(
                _teacher_subjects(
                    request.user,
                    class_name,
                    stream,
                )
            )

            existing_reports = {
                report.subject_id: report
                for report in WeeklyAssessmentReport.objects.filter(
                    week=week,
                    student=selected_student,
                    is_published=True,
                    subject__in=subjects,
                )
            }

            context["individual_all_subject_rows"] = [
                {
                    "subject": subject,
                    "report": existing_reports.get(subject.pk),
                    "score": (
                        existing_reports[subject.pk].score
                        if subject.pk in existing_reports
                        else ""
                    ),
                    "max_score": (
                        existing_reports[subject.pk].max_score
                        if subject.pk in existing_reports
                        else 100
                    ),
                    "teacher_report": (
                        existing_reports[subject.pk].teacher_report
                        if subject.pk in existing_reports
                        else ""
                    ),
                }
                for subject in subjects
            ]

        if week and all_subjects:
            subjects = list(
                _teacher_subjects(
                    request.user,
                    class_name,
                    stream,
                )
            )

            context["selected_subject_object"] = None

            context["all_subject_rows"] = [
                {
                    "subject": subject,
                    "rows": _write_rows(
                        request.user,
                        week,
                        class_name,
                        stream,
                        subject,
                    ),
                }
                for subject in subjects
            ]

        elif week and subject_id.isdigit():

            subject = _authorized_subject(
                request.user,
                class_name,
                stream,
                subject_id,
            )

            context["selected_subject_object"] = subject

            if subject:
                context["rows"] = _write_rows(
                    request.user,
                    week,
                    class_name,
                    stream,
                    subject,
                )

    return render(
        request,
        "weekly_reports/staff_write.html",
        context,
    )


@login_required
def staff_write_individual(request):

    if not _is_staff(request.user):
        return HttpResponseForbidden(
            "Teaching staff access required."
        )

    if request.method != "POST":
        return redirect(
            "weekly_reports:staff_write"
        )

    class_value = request.POST.get(
        "class",
        "",
    )

    week_id = request.POST.get(
        "week",
        "",
    )

    student_id = request.POST.get(
        "student",
        "",
    )

    subject_id = request.POST.get(
        "subject",
        "",
    )

    all_subjects = subject_id.lower() == "all"

    class_name, stream = _parse_class(
        class_value
    )

    if not _teacher_can_class(
        request.user,
        class_name,
        stream,
    ):
        return HttpResponseForbidden(
            "You are not assigned to this class and stream."
        )

    week = get_object_or_404(
        WeeklyAssessmentWeek,
        pk=week_id,
    )

    if week.is_locked:
        return HttpResponseForbidden(
            "This assessment week is locked."
        )

    student = get_object_or_404(
        Student,
        pk=student_id,
        is_active=True,
        class_name__iexact=class_name,
    )

    if stream and (
        (student.stream or "").strip().lower()
        != stream.lower()
    ):
        return HttpResponseForbidden(
            "This learner is not in the selected stream."
        )

    if all_subjects:

        subjects = list(
            _teacher_subjects(
                request.user,
                class_name,
                stream,
            )
        )

        saved = 0

        with transaction.atomic():

            for subject in subjects:

                score_text = request.POST.get(
                    f"score_{subject.pk}",
                    "",
                ).strip()

                if score_text == "":
                    continue

                max_score_text = request.POST.get(
                    f"max_score_{subject.pk}",
                    "100",
                ).strip()

                teacher_report = request.POST.get(
                    f"report_{subject.pk}",
                    "",
                ).strip()

                try:
                    score = float(score_text)
                    max_score = float(max_score_text)

                    if max_score <= 0:
                        continue

                    if score < 0 or score > max_score:
                        continue

                except (TypeError, ValueError):
                    continue

                WeeklyAssessmentReport.objects.update_or_create(
                    student=student,
                    subject=subject,
                    week_start=week.week_start,
                    week_end=week.week_end,
                    defaults={
                        "week": week,
                        "class_name": student.class_name or "",
                        "stream": student.stream or "",
                        "week_number": week.week_number,
                        "score": score,
                        "max_score": max_score,
                        "teacher_report": teacher_report,
                        "created_by": request.user,
                        "updated_by": request.user,
                    },
                )

                saved += 1

        messages.success(
            request,
            f"{saved} weekly assessment reports saved for {student}.",
        )

        return redirect(
            f"/weekly-reports/staff/write/"
            f"?mode=individual"
            f"&class={class_value}"
            f"&week={week_id}"
            f"&student={student_id}"
            f"&subject=all"
        )

    subject = _authorized_subject(
        request.user,
        class_name,
        stream,
        subject_id,
    )

    if subject is None:
        return HttpResponseForbidden(
            "You are not assigned to this subject."
        )

    score_text = request.POST.get(
        "score",
        "",
    ).strip()

    max_score_text = request.POST.get(
        "max_score",
        "100",
    ).strip()

    teacher_report = request.POST.get(
        "teacher_report",
        "",
    ).strip()

    try:
        score = float(score_text)
        max_score = float(max_score_text)

        if max_score <= 0:
            raise ValueError

        if score < 0 or score > max_score:
            raise ValueError

    except (TypeError, ValueError):

        messages.error(
            request,
            "Enter a valid score within the maximum score.",
        )

        return redirect(
            f"/weekly-reports/staff/write/"
            f"?mode=individual"
            f"&class={class_value}"
            f"&week={week_id}"
            f"&student={student_id}"
            f"&subject={subject_id}"
        )

    WeeklyAssessmentReport.objects.update_or_create(
        student=student,
        subject=subject,
        week_start=week.week_start,
        week_end=week.week_end,
        defaults={
            "week": week,
            "class_name": student.class_name or "",
            "stream": student.stream or "",
            "week_number": week.week_number,
            "score": score,
            "max_score": max_score,
            "teacher_report": teacher_report,
            "created_by": request.user,
            "updated_by": request.user,
        },
    )

    messages.success(
        request,
        f"Weekly report saved for {student}.",
    )

    return redirect(
        f"/weekly-reports/staff/write/"
        f"?mode=individual"
        f"&class={class_value}"
        f"&week={week_id}"
        f"&student={student_id}"
        f"&subject={subject_id}"
    )


@login_required
def staff_write_class(request):

    if not _is_staff(request.user):
        return HttpResponseForbidden(
            "Teaching staff access required."
        )

    if request.method != "POST":
        return redirect(
            "weekly_reports:staff_write"
        )

    class_value = request.POST.get(
        "class",
        "",
    )

    week_id = request.POST.get(
        "week",
        "",
    )

    subject_id = request.POST.get(
        "subject",
        "",
    )

    all_subjects = subject_id.lower() == "all"

    class_name, stream = _parse_class(
        class_value
    )

    if not _teacher_can_class(
        request.user,
        class_name,
        stream,
    ):
        return HttpResponseForbidden(
            "You are not assigned to this class and stream."
        )

    week = get_object_or_404(
        WeeklyAssessmentWeek,
        pk=week_id,
    )

    if week.is_locked:
        return HttpResponseForbidden(
            "This assessment week is locked."
        )

    subjects = []

    if all_subjects:
        subjects = list(
            _teacher_subjects(
                request.user,
                class_name,
                stream,
            )
        )

        if not subjects:
            return HttpResponseForbidden(
                "No subjects are assigned to this class and stream."
            )
    else:
        subject = _authorized_subject(
            request.user,
            class_name,
            stream,
            subject_id,
        )

        if subject is None:
            return HttpResponseForbidden(
                "You are not assigned to this subject."
            )

        subjects = [subject]

    students = _students_for_class(
        request.user,
        class_name,
        stream,
    )

    saved = 0

    with transaction.atomic():

        for subject in subjects:

            for student in students:

                score_text = request.POST.get(
                    f"score_{subject.pk}_{student.pk}"
                    if all_subjects
                    else f"score_{student.pk}",
                    "",
                ).strip()

                if score_text == "":
                    continue

                max_score_text = request.POST.get(
                    f"max_score_{subject.pk}_{student.pk}"
                    if all_subjects
                    else f"max_score_{student.pk}",
                    "100",
                ).strip()

                teacher_report = request.POST.get(
                    f"report_{subject.pk}_{student.pk}"
                    if all_subjects
                    else f"report_{student.pk}",
                    "",
                ).strip()

                try:
                    score = float(score_text)
                    max_score = float(max_score_text)

                    if max_score <= 0:
                        continue

                    if score < 0 or score > max_score:
                        continue

                except (TypeError, ValueError):
                    continue

                WeeklyAssessmentReport.objects.update_or_create(
                    student=student,
                    subject=subject,
                    week_start=week.week_start,
                    week_end=week.week_end,
                    defaults={
                        "week": week,
                        "class_name": student.class_name or "",
                        "stream": student.stream or "",
                        "week_number": week.week_number,
                        "score": score,
                        "max_score": max_score,
                        "teacher_report": teacher_report,
                        "created_by": request.user,
                        "updated_by": request.user,
                    },
                )

                saved += 1

    messages.success(
        request,
        f"{saved} weekly assessment reports saved.",
    )

    return redirect(
        f"/weekly-reports/staff/write/"
        f"?mode=class"
        f"&class={class_value}"
        f"&week={week_id}"
        f"&subject={subject_id}"
    )

