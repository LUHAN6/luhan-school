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

from .views import _is_admin


def _parse_class(value):
    parts = (value or "").split("||", 1)

    class_name = parts[0].strip()

    stream = (
        parts[1].strip()
        if len(parts) > 1
        else ""
    )

    return class_name, stream


def _admin_classes():
    """
    All active learner class/stream combinations.
    """

    rows = (
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

    result = []
    seen = set()

    for class_name, stream in rows:

        class_name = (
            class_name or ""
        ).strip()

        stream = (
            stream or ""
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

    return result


def _admin_students(
    class_name="",
    stream="",
):
    qs = Student.objects.filter(
        is_active=True,
    )

    if class_name:
        qs = qs.filter(
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


def _admin_subjects(
    class_name="",
    stream="",
):
    """
    Return subjects actually assigned to the selected
    class/stream.

    This deliberately does NOT return every Subject in
    the database.
    """

    if not class_name:
        return TimetableSubject.objects.none()

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


def _authorized_subject(
    class_name,
    stream,
    subject_id,
):
    if not str(subject_id).isdigit():
        return None

    return _admin_subjects(
        class_name,
        stream,
    ).filter(
        pk=int(subject_id),
    ).first()


def _write_rows(
    week,
    class_name,
    stream,
    subject,
):
    """
    Build the administrative learner matrix.

    Existing reports are loaded automatically.
    Missing reports are marked Pending.
    """

    students = _admin_students(
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
def admin_write(request):

    if not _is_admin(request.user):
        return HttpResponseForbidden(
            "Administrator access required."
        )

    weeks = (
        WeeklyAssessmentWeek.objects
        .select_related(
            "academic_year",
            "term",
        )
        .order_by(
            "-week_start",
            "-week_number",
        )
    )

    classes = _admin_classes()

    mode = request.GET.get(
        "mode",
        "",
    )

    context = {
        "portal": "admin",
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

    context["selected_class"] = class_name
    context["selected_stream"] = stream
    context["selected_week"] = week_id
    context["selected_subject"] = subject_id

    all_subjects = subject_id.lower() == "all"
    context["all_subjects"] = all_subjects
    context["can_use_all_subjects"] = True
    context["all_subject_rows"] = []

    if class_name:

        context["students"] = _admin_students(
            class_name,
            stream,
        )

        context["subjects"] = _admin_subjects(
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
            pk=int(week_id),
        ).first()

        context["selected_week_object"] = week

        if (
            week
            and all_subjects
            and context.get("selected_student") is not None
        ):
            selected_student = context["selected_student"]

            permitted_subjects = list(
                _admin_subjects(
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
                    subject__in=permitted_subjects,
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
                for subject in permitted_subjects
            ]

        if week:

            if all_subjects:

                permitted_subjects = list(
                    _admin_subjects(
                        class_name,
                        stream,
                    )
                )

                context["all_subject_rows"] = [
                    {
                        "subject": subject,
                        "rows": _write_rows(
                            week,
                            class_name,
                            stream,
                            subject,
                        ),
                    }
                    for subject in permitted_subjects
                ]

            elif subject_id.isdigit():

                subject = _authorized_subject(
                    class_name,
                    stream,
                    subject_id,
                )

                context["selected_subject_object"] = subject

                if subject:

                    context["rows"] = _write_rows(
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
def admin_write_individual(request):

    if not _is_admin(request.user):
        return HttpResponseForbidden(
            "Administrator access required."
        )

    if request.method != "POST":
        return redirect(
            "weekly_reports:admin_write"
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

    print("\n=== INDIVIDUAL ADMIN POST DEBUG ===")
    print("Authenticated user:", request.user.pk, request.user.username)
    print("Class:", class_value)
    print("Week:", week_id)
    print("Student:", student_id)
    print("Subject:", subject_id)
    print("All subjects:", all_subjects)
    print("POST keys:")
    print(sorted(request.POST.keys()))

    class_name, stream = _parse_class(
        class_value
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
            _admin_subjects(
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

                    print("Parsed score:", score)
                    print("Parsed max score:", max_score)

                    if max_score <= 0:
                        continue

                    if score < 0 or score > max_score:
                        continue

                except (TypeError, ValueError):
                    continue


                try:
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
                except Exception as exc:
                    print("\n=== INDIVIDUAL ADMIN ALL SUBJECTS ERROR ===")
                    print("Student ID:", student.pk)
                    print("Week ID:", week.pk)
                    print("Subject ID:", subject.pk)
                    print("Subject:", getattr(subject, "name", ""))
                    print("Exception type:", type(exc).__name__)
                    print("Exception:", repr(exc))
                    raise

                saved += 1

        messages.success(
            request,
            f"{saved} weekly assessment reports saved for {student}.",
        )

        return redirect(
            f"/weekly-reports/admin/write/"
            f"?mode=individual"
            f"&class={class_value}"
            f"&week={week_id}"
            f"&student={student_id}"
            f"&subject=all"
        )

    subject = _authorized_subject(
        class_name,
        stream,
        subject_id,
    )

    if subject is None:
        return HttpResponseForbidden(
            "This subject is not assigned to the selected class and stream."
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
            f"/weekly-reports/admin/write/"
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
        f"Weekly assessment saved for {student}.",
    )

    return redirect(
        f"/weekly-reports/admin/write/"
        f"?mode=individual"
        f"&class={class_value}"
        f"&week={week_id}"
        f"&student={student_id}"
        f"&subject={subject_id}"
    )


@login_required
def admin_write_class(request):

    if not _is_admin(request.user):
        return HttpResponseForbidden(
            "Administrator access required."
        )

    if request.method != "POST":
        return redirect(
            "weekly_reports:admin_write"
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

    week = get_object_or_404(
        WeeklyAssessmentWeek,
        pk=week_id,
    )

    if week.is_locked:
        return HttpResponseForbidden(
            "This assessment week is locked."
        )

    students = _admin_students(
        class_name,
        stream,
    )

    saved = 0

    with transaction.atomic():

        if all_subjects:

            subjects = list(
                _admin_subjects(
                    class_name,
                    stream,
                )
            )

            for subject in subjects:

                for student in students:

                    score_text = request.POST.get(
                        f"score_{subject.pk}_{student.pk}",
                        "",
                    ).strip()

                    if score_text == "":
                        continue

                    max_score_text = request.POST.get(
                        f"max_score_{subject.pk}_{student.pk}",
                        "100",
                    ).strip()

                    teacher_report = request.POST.get(
                        f"report_{subject.pk}_{student.pk}",
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

        else:

            subject = _authorized_subject(
                class_name,
                stream,
                subject_id,
            )

            if subject is None:
                return HttpResponseForbidden(
                    "This subject is not assigned to the selected class and stream."
                )

            for student in students:

                score_text = request.POST.get(
                    f"score_{student.pk}",
                    "",
                ).strip()

                if score_text == "":
                    continue

                max_score_text = request.POST.get(
                    f"max_score_{student.pk}",
                    "100",
                ).strip()

                teacher_report = request.POST.get(
                    f"report_{student.pk}",
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
        f"/weekly-reports/admin/write/"
        f"?mode=class"
        f"&class={class_value}"
        f"&week={week_id}"
        f"&subject={subject_id}"
    )

