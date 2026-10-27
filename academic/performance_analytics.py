from django.db.models import Avg, Count

from accounts.staff_access import (
    can_view_class,
    get_staff_students,
    get_staff_subjects_for_class,
)
from fees.models import Term
from .models import Assessment, AssessmentType


def _stream_name(student):
    value = getattr(student, "stream", "")
    return getattr(value, "name", str(value or ""))


def build_performance_analytics(
    user,
    selected_year,
    selected_term,
    selected_assessment_type,
    selected_class,
    selected_stream="",
):
    """Build comparison data using only the user's permitted cohort and subjects."""

    result = {
        "assessment_comparison": [],
        "term_comparison": [],
        "subject_comparison": [],
        "learner_progress": [],
        "assessment_coverage": {
            "expected": 0,
            "recorded": 0,
            "percentage": 0,
            "basis": "No cohort selected",
        },
        "comparison_previous_term": None,
    }

    if not (
        selected_year
        and selected_term
        and selected_term.academic_year_id == selected_year.id
        and selected_class
        and can_view_class(user, selected_class, selected_stream)
    ):
        return result

    students = list(
        get_staff_students(user).filter(class_name=selected_class)
    )

    if selected_stream:
        students = [
            student for student in students
            if _stream_name(student) == selected_stream
        ]

    if not students:
        return result

    permitted_subjects = get_staff_subjects_for_class(
        user, selected_class, selected_stream
    )
    subject_ids = list(permitted_subjects.values_list("id", flat=True))

    if not subject_ids:
        return result

    cohort = Assessment.objects.filter(
        student_id__in=[student.id for student in students],
        academic_year=selected_year,
        term__academic_year=selected_year,
        subject_id__in=subject_ids,
    ).select_related("student", "subject", "term", "assessment_type")

    # Compare assessment types within the selected term.
    current_term_marks = cohort.filter(term=selected_term)
    types = AssessmentType.objects.filter(is_active=True).order_by(
        "order", "name"
    )

    for assessment_type in types:
        rows = current_term_marks.filter(
            assessment_type=assessment_type
        )
        stats = rows.aggregate(
            average=Avg("score"),
            marks=Count("id"),
            learners=Count("student_id", distinct=True),
            subjects=Count("subject_id", distinct=True),
        )
        result["assessment_comparison"].append({
            "name": assessment_type.name,
            "average": round(float(stats["average"]), 2)
                if stats["average"] is not None else None,
            "marks": stats["marks"],
            "learners": stats["learners"],
            "subjects": stats["subjects"],
        })

    # Compare terms in the selected academic year.
    term_marks = cohort
    if selected_assessment_type:
        term_marks = term_marks.filter(
            assessment_type=selected_assessment_type
        )

    term_stats = list(
        term_marks.values("term_id").annotate(
            average=Avg("score"),
            marks=Count("id"),
            learners=Count("student_id", distinct=True),
        )
    )
    stats_by_term = {item["term_id"]: item for item in term_stats}
    terms_by_id = {
        term.id: term
        for term in Term.objects.filter(
            id__in=stats_by_term.keys()
        )
    }

    for term_id, stats in stats_by_term.items():
        term = terms_by_id.get(term_id)
        if term is None:
            continue
        result["term_comparison"].append({
            "term_id": term.id,
            "name": str(term),
            "order": term.order,
            "average": round(float(stats["average"]), 2)
                if stats["average"] is not None else None,
            "marks": stats["marks"],
            "learners": stats["learners"],
        })

    result["term_comparison"].sort(
        key=lambda item: (item["order"], item["name"])
    )

    # Subject comparison for the selected term and optional assessment type.
    subject_marks = current_term_marks
    if selected_assessment_type:
        subject_marks = subject_marks.filter(
            assessment_type=selected_assessment_type
        )

    subject_stats = list(
        subject_marks.values("subject_id", "subject__name").annotate(
            average=Avg("score"),
            marks=Count("id"),
            learners=Count("student_id", distinct=True),
        ).order_by("subject__name")
    )

    result["subject_comparison"] = [
        {
            "subject_id": item["subject_id"],
            "name": item["subject__name"],
            "average": round(float(item["average"]), 2)
                if item["average"] is not None else None,
            "marks": item["marks"],
            "learners": item["learners"],
        }
        for item in subject_stats
    ]

    # Use the latest earlier term by order as the comparison term.
    previous_term = (
        Term.objects.filter(
            academic_year=selected_year,
            order__lt=selected_term.order,
        )
        .order_by("-order", "-id")
        .first()
    )
    result["comparison_previous_term"] = previous_term

    previous_marks = None
    if previous_term:
        previous_marks = term_marks.filter(term=previous_term)

    # Keep current and previous learner averages on the same assessment type.
    progress_current_marks = current_term_marks
    if selected_assessment_type:
        progress_current_marks = progress_current_marks.filter(
            assessment_type=selected_assessment_type
        )

    current_by_student = {
        item["student_id"]: item["average"]
        for item in progress_current_marks.values("student_id").annotate(
            average=Avg("score")
        )
    }

    previous_by_student = {}
    if previous_marks is not None:
        previous_by_student = {
            item["student_id"]: item["average"]
            for item in previous_marks.values("student_id").annotate(
                average=Avg("score")
            )
        }

    student_by_id = {student.id: student for student in students}
    for student_id, current_average in current_by_student.items():
        student = student_by_id.get(student_id)
        if student is None or current_average is None:
            continue

        previous_average = previous_by_student.get(student_id)
        current_value = round(float(current_average), 2)
        previous_value = (
            round(float(previous_average), 2)
            if previous_average is not None else None
        )

        result["learner_progress"].append({
            "student": student,
            "current_average": current_value,
            "previous_average": previous_value,
            "change": round(current_value - previous_value, 2)
                if previous_value is not None else None,
        })

    result["learner_progress"].sort(
        key=lambda item: item["current_average"], reverse=True
    )

    # Estimated coverage: only subjects with at least one recorded mark
    # are counted in the expected slots. This is not a definitive missing-
    # marks report until subject expectations are mapped to each class.
    coverage_marks = current_term_marks
    if selected_assessment_type:
        coverage_marks = coverage_marks.filter(
            assessment_type=selected_assessment_type
        )

    observed_subject_ids = list(
        coverage_marks.order_by().values_list(
            "subject_id", flat=True
        ).distinct()
    )
    recorded_pairs = coverage_marks.values(
        "student_id", "subject_id"
    ).distinct().count()

    expected_slots = len(students) * len(observed_subject_ids)
    result["assessment_coverage"] = {
        "expected": expected_slots,
        "recorded": recorded_pairs,
        "percentage": round(
            recorded_pairs * 100 / expected_slots, 1
        ) if expected_slots else 0,
        "basis": (
            "Estimated from subjects with at least one recorded mark; "
            "not a definitive missing-marks count."
        ),
    }

    return result

