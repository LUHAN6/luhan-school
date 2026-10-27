from timetable.models import TimetableTeacher
from timetable.advanced_models import (
    TimetableTeacherClassAssignment,
    TimetableTeacherTeachingAssignment,
)


def is_admin(user):
    if not user or not user.is_authenticated:
        return False

    if getattr(user, "is_superuser", False):
        return True

    try:
        return user.profile.role == "ADMIN"
    except Exception:
        return False


def get_timetable_teacher(user):
    if not user or not user.is_authenticated:
        return None

    try:
        profile = user.profile
        employee = profile.employee

        if not employee:
            return None

        teacher = employee.timetable_teacher

        if teacher and teacher.active:
            return teacher

    except Exception:
        return None

    return None


def _same_class(class_name, assignment_class):
    if not class_name or not assignment_class:
        return False

    return str(class_name).strip().casefold() == str(
        assignment_class
    ).strip().casefold()


def _same_stream(stream, assignment_stream):
    """
    A blank assignment stream means the teacher covers
    the whole class.
    """

    if not assignment_stream:
        return True

    if not stream:
        return False

    return str(stream).strip().casefold() == str(
        assignment_stream
    ).strip().casefold()


def is_class_teacher_for(user, class_name, stream=None):
    if is_admin(user):
        return True

    teacher = get_timetable_teacher(user)

    if not teacher:
        return False

    assignments = TimetableTeacherClassAssignment.objects.filter(
        teacher=teacher,
        is_active=True,
    )

    for assignment in assignments:
        if _same_class(class_name, assignment.class_name):
            if _same_stream(stream, assignment.stream):
                if assignment.is_class_teacher:
                    return True

    return False


def can_enter_marks(user, class_name, stream, subject):
    """
    Permission hierarchy:

    ADMIN
        -> everything

    CLASS TEACHER
        -> all subjects for assigned class

    SUBJECT TEACHER
        -> only subjects/classes explicitly assigned

    SUBJECT MATCHING
        -> academic.Subject is matched to timetable.TimetableSubject
           by subject code, not database ID.
    """

    if is_admin(user):
        return True

    if not class_name or not subject:
        return False

    if is_class_teacher_for(user, class_name, stream):
        return True

    teacher = get_timetable_teacher(user)

    if not teacher:
        return False

    subject_code = getattr(subject, "code", None)

    if not subject_code:
        return False

    assignments = (
        TimetableTeacherTeachingAssignment.objects
        .filter(
            teacher=teacher,
            is_active=True,
            subject__code=subject_code,
        )
        .select_related("subject")
    )

    for assignment in assignments:

        if not _same_class(
            class_name,
            assignment.class_name,
        ):
            continue

        if _same_stream(
            stream,
            assignment.stream,
        ):
            return True

    return False

def can_access_class(user, class_name, stream=None):
    """
    Check whether a staff member can access a class.

    When a specific stream is supplied, the assignment must match
    that stream.

    When no stream is supplied, the class is considered accessible
    if the staff member has any active assignment in that class.
    This is needed for class-level selectors such as Whole Class
    Excel and Subject Excel.
    """

    if is_admin(user):
        return True

    if not class_name:
        return False

    # --------------------------------------------------------
    # CLASS-LEVEL ACCESS
    # No stream supplied: any assigned stream in this class
    # grants access to the class selector.
    # --------------------------------------------------------

    if not stream:
        if TimetableTeacherClassAssignment.objects.filter(
            teacher=get_timetable_teacher(user),
            is_active=True,
        ).exists():
            for assignment in TimetableTeacherClassAssignment.objects.filter(
                teacher=get_timetable_teacher(user),
                is_active=True,
            ):
                if _same_class(
                    class_name,
                    assignment.class_name,
                ):
                    return True

        if TimetableTeacherTeachingAssignment.objects.filter(
            teacher=get_timetable_teacher(user),
            is_active=True,
        ).exists():
            for assignment in TimetableTeacherTeachingAssignment.objects.filter(
                teacher=get_timetable_teacher(user),
                is_active=True,
            ):
                if _same_class(
                    class_name,
                    assignment.class_name,
                ):
                    return True

        return False

    # --------------------------------------------------------
    # SPECIFIC STREAM ACCESS
    # --------------------------------------------------------

    if is_class_teacher_for(user, class_name, stream):
        return True

    teacher = get_timetable_teacher(user)

    if not teacher:
        return False

    class_assignments = TimetableTeacherClassAssignment.objects.filter(
        teacher=teacher,
        is_active=True,
    )

    for assignment in class_assignments:
        if _same_class(
            class_name,
            assignment.class_name,
        ):
            if _same_stream(
                stream,
                assignment.stream,
            ):
                return True

    teaching_assignments = TimetableTeacherTeachingAssignment.objects.filter(
        teacher=teacher,
        is_active=True,
    )

    for assignment in teaching_assignments:
        if _same_class(
            class_name,
            assignment.class_name,
        ):
            if _same_stream(
                stream,
                assignment.stream,
            ):
                return True

    return False

def allowed_class_streams(user):
    """
    Returns None for administrators.
    Otherwise returns a set of:

        (class_name, stream)

    available to the staff member.
    """

    if is_admin(user):
        return None

    teacher = get_timetable_teacher(user)

    if not teacher:
        return set()

    result = set()

    class_assignments = TimetableTeacherClassAssignment.objects.filter(
        teacher=teacher,
        is_active=True,
    )

    for assignment in class_assignments:
        result.add(
            (
                assignment.class_name,
                assignment.stream or "",
            )
        )

    teaching_assignments = TimetableTeacherTeachingAssignment.objects.filter(
        teacher=teacher,
        is_active=True,
    )

    for assignment in teaching_assignments:
        result.add(
            (
                assignment.class_name,
                assignment.stream or "",
            )
        )

    return result


def allowed_subject_ids_for_class(
    user,
    class_name,
    stream=None,
):
    """
    Return academic.Subject IDs that the user may enter.

    None means unrestricted subjects for:
        - Admin
        - Class teacher

    Subject teachers are matched by subject code because
    timetable.TimetableSubject and academic.Subject are separate models.
    """

    if is_admin(user):
        return None

    if is_class_teacher_for(
        user,
        class_name,
        stream,
    ):
        return None

    teacher = get_timetable_teacher(user)

    if not teacher:
        return set()

    assignments = (
        TimetableTeacherTeachingAssignment.objects
        .filter(
            teacher=teacher,
            is_active=True,
        )
        .select_related("subject")
    )

    allowed_codes = set()

    for assignment in assignments:

        if not _same_class(
            class_name,
            assignment.class_name,
        ):
            continue

        if not _same_stream(
            stream,
            assignment.stream,
        ):
            continue

        code = getattr(
            assignment.subject,
            "code",
            None,
        )

        if code:
            allowed_codes.add(
                str(code).strip().casefold()
            )

    if not allowed_codes:
        return set()

    from .models import Subject

    allowed_ids = set()

    for subject in Subject.objects.filter(
        is_active=True
    ):
        code = getattr(
            subject,
            "code",
            None,
        )

        if code and str(code).strip().casefold() in allowed_codes:
            allowed_ids.add(subject.id)

    return allowed_ids



