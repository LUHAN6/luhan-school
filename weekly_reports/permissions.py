from timetable.advanced_models import (
    TimetableTeacherClassAssignment,
    TimetableTeacherTeachingAssignment,
)
from timetable.staff_utils import (
    get_staff_teacher,
    get_staff_subjects_for_class,
    is_class_teacher_for,
)


def is_admin(user):
    if not user or not user.is_authenticated:
        return False

    try:
        profile = user.userprofile
        return profile.role == "ADMIN"
    except Exception:
        return user.is_superuser


def get_teacher(user):
    try:
        return get_staff_teacher(user)
    except Exception:
        return None


def can_manage_report(user, report):
    if is_admin(user):
        return True

    teacher = get_teacher(user)

    if teacher is None:
        return False

    if is_class_teacher_for(
        user,
        report.class_name,
        report.stream,
    ):
        return True

    for assessment in report.assessments.all():
        if assessment.teacher_id == user.id:
            return True

    return False


def can_manage_learning_area(
    user,
    class_name,
    stream,
    subject,
):
    if is_admin(user):
        return True

    if is_class_teacher_for(
        user,
        class_name,
        stream,
    ):
        return True

    subjects = get_staff_subjects_for_class(
        user,
        class_name,
        stream=stream,
    )

    subject_ids = {
        getattr(x, "id", None)
        for x in subjects
    }

    return subject.id in subject_ids




