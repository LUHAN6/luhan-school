from django.db.models import Q

from hr_payroll.models import Employee
from timetable.models import (
    TimetableSubject,
    TimetableTeacher,
    TimetableLesson,
 )
from timetable.advanced_models import (
    TimetableTeacherClassAssignment,
    TimetableTeacherTeachingAssignment,
 )
from students.models import Student


# ============================================================
# BASIC ACCESS
# ============================================================

def is_admin_user(user):
    """
    Administrators have unrestricted access.
    """
    if not user or not user.is_authenticated:
        return False

    return (
        user.is_superuser
        or user.is_staff
        or getattr(
            getattr(user, "profile", None),
            "role",
            ""
        ) == "ADMIN"
    )


def get_staff_employee(user):
    """
    Return the Employee connected to the logged-in user.
    """
    if not user or not user.is_authenticated:
        return None

    try:
        profile = user.profile
    except Exception:
        return None

    return getattr(profile, "employee", None)


def get_staff_teacher(user):
    """
    Return the active timetable Teacher connected
    to the logged-in user's Employee.
    """
    employee = get_staff_employee(user)

    if not employee:
        return None

    return (
        TimetableTeacher.objects
        .filter(
            employee=employee,
        active=True,
        )
        .first()
    )


# ============================================================
# TEACHER ASSIGNMENTS
# ============================================================

def get_teacher_class_assignments(user):
    """
    Return active class assignments for this teacher.

    These assignments determine which classes/streams the
    teacher may access.

    Admins are unrestricted and therefore receive all active
    class assignments.
    """
    if is_admin_user(user):
        return (
            TimetableTeacherClassAssignment.objects
            .filter(is_active=True)
            .select_related("teacher")
        )

    teacher = get_staff_teacher(user)

    if not teacher:
        return TimetableTeacherClassAssignment.objects.none()

    return (
        TimetableTeacherClassAssignment.objects
        .filter(
            teacher=teacher,
            is_active=True,
        )
        .select_related("teacher")
    )


def get_teacher_teaching_assignments(user):
    """
    Return active subject + class + stream assignments
    for this teacher.

    This is the source of truth for subject-teaching
    permissions.
    """
    if is_admin_user(user):
        return (
            TimetableTeacherTeachingAssignment.objects
            .filter(is_active=True)
            .select_related("teacher", "subject")
        )

    teacher = get_staff_teacher(user)

    if not teacher:
        return TimetableTeacherTeachingAssignment.objects.none()

    return (
        TimetableTeacherTeachingAssignment.objects
        .filter(
            teacher=teacher,
            is_active=True,
        )
        .select_related("teacher", "subject")
    )


# ============================================================
# STREAM MATCHING
# ============================================================

def _normalise_stream(stream):
    """
    Convert null/blank streams to an empty string so that
    assignment matching remains consistent.
    """
    return (stream or "").strip()


def _assignment_matches_class(
    assignment,
    class_name,
    stream="",
):
    """
    Determine whether an assignment covers a class/stream.

    A blank assignment stream means the assignment applies
    to the whole class.

    A specific assignment stream applies only to that stream.
    """
    requested_class = (class_name or "").strip()
    requested_stream = _normalise_stream(stream)

    assignment_class = (
        assignment.class_name or ""
    ).strip()

    assignment_stream = _normalise_stream(
        assignment.stream
    )

    if assignment_class != requested_class:
        return False

    # Blank assignment stream = whole class.
    if not assignment_stream:
        return True

    return assignment_stream == requested_stream


# ============================================================
# CLASS ACCESS
# ============================================================

def is_assigned_to_class(
    user,
    class_name,
    stream="",
):
    """
    True when the teacher has an active assignment covering
    the requested class/stream.
    """
    if is_admin_user(user):
        return True

    assignments = get_teacher_class_assignments(user)

    for assignment in assignments:
        if _assignment_matches_class(
            assignment,
            class_name,
            stream,
        ):
            return True

    return False


def is_class_teacher_for(
    user,
    class_name,
    stream="",
):
    """
    True only when the teacher is specifically designated
    as the class teacher for the requested class/stream.
    """
    if is_admin_user(user):
        return True

    assignments = (
        get_teacher_class_assignments(user)
        .filter(is_class_teacher=True)
    )

    for assignment in assignments:
        if _assignment_matches_class(
            assignment,
            class_name,
            stream,
        ):
            return True

    return False


def can_view_class(
    user,
    class_name,
    stream="",
):
    """
    Determines whether a teacher can view a class register.

    Both class teachers and subject teachers can view the
    register for classes they are assigned to.
    """
    if is_admin_user(user):
        return True

    return is_assigned_to_class(
        user,
        class_name,
        stream,
    )


# ============================================================
# ATTENDANCE PERMISSIONS
# ============================================================

def can_mark_attendance(
    user,
    class_name,
    stream="",
):
    """
    Only administrators and class teachers can mark
    attendance.
    """
    if is_admin_user(user):
        return True

    return is_class_teacher_for(
        user,
        class_name,
        stream,
    )


# ============================================================
# SUBJECT PERMISSIONS
# ============================================================

def can_enter_marks(
    user,
    class_name,
    stream="",
    subject=None,
):
    """
    Determine whether a user can enter marks.

    Administrator:
        All classes and subjects.

    Class teacher:
        All subjects in their assigned class/stream.

    Subject teacher:
        Only subjects specifically assigned to that
        class/stream.
    """
    if is_admin_user(user):
        return True

    if not class_name or not subject:
        return False

    # --------------------------------------------------------
    # CLASS TEACHER
    # --------------------------------------------------------

    if is_class_teacher_for(
        user,
        class_name,
        stream,
    ):
        return True

    # --------------------------------------------------------
    # SUBJECT TEACHER
    # --------------------------------------------------------

    teaching_assignments = get_teacher_teaching_assignments(user)

    # Academic Subject and Timetable Subject are separate models.
    # Match the teacher assignment using subject code first, then name.
    timetable_subject = TimetableSubject.objects.filter(
        is_active=True,
    ).filter(
        Q(code=subject.code) | Q(name=subject.name)
    ).first()

    if not timetable_subject:
        return False

    teaching_assignments = teaching_assignments.filter(
        subject=timetable_subject,
    )

    for assignment in teaching_assignments:
        if _assignment_matches_class(
            assignment,
            class_name,
            stream,
        ):
            return True

    return False


def get_staff_subjects_for_class(
    user,
    class_name,
    stream="",
):
    """
    Return Academic Subject objects this teacher is allowed to
    enter marks for in the requested class/stream.

    Teacher assignments are stored against timetable.TimetableSubject,
    while Assessment uses academic.Subject.
    """

    # Import locally to avoid an accounts/academic import cycle.
    from academic.models import Subject as AcademicSubject

    active_subjects = AcademicSubject.objects.filter(
        is_active=True
    ).order_by("name")

    if is_admin_user(user):
        return active_subjects

    if is_class_teacher_for(
        user,
        class_name,
        stream,
    ):
        return active_subjects

    teaching_assignments = get_teacher_teaching_assignments(user)
    academic_subject_ids = []

    for assignment in teaching_assignments:
        if not _assignment_matches_class(
            assignment,
            class_name,
            stream,
        ):
            continue

        timetable_subject = assignment.subject

        academic_subject = AcademicSubject.objects.filter(
            is_active=True,
        ).filter(
            Q(code=timetable_subject.code)
            | Q(name=timetable_subject.name)
        ).first()

        if academic_subject:
            academic_subject_ids.append(academic_subject.id)

    if not academic_subject_ids:
        return AcademicSubject.objects.none()

    return (
        active_subjects
        .filter(id__in=academic_subject_ids)
        .distinct()
    )


# ============================================================
# CLASS PAIRS
# ============================================================

def get_staff_class_pairs(user):
    """
    Return all class/stream combinations the teacher may
    access.

    Source of truth:
        TeacherClassAssignment
        TeacherTeachingAssignment

    Timetable is deliberately NOT used for permissions.
    """
    if is_admin_user(user):
        return list(
            Student.objects
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

    class_pairs = set()

    class_assignments = get_teacher_class_assignments(user)

    for assignment in class_assignments:
        class_name = (
            assignment.class_name or ""
        ).strip()

        stream = _normalise_stream(
            assignment.stream
        )

        if not class_name:
            continue

        if stream:
            class_pairs.add(
                (
                    class_name,
                    stream,
                )
            )
        else:
            # Whole-class assignment. Expand it to the actual
            # student class/stream combinations.
            student_pairs = (
                Student.objects
                .filter(class_name=class_name)
                .values_list(
                    "class_name",
                    "stream",
                )
                .distinct()
            )

            for pair in student_pairs:
                class_pairs.add(
                    (
                        pair[0],
                        pair[1] or "",
                    )
                )

    # Teaching assignments also provide class access.
    teaching_assignments = (
        get_teacher_teaching_assignments(user)
    )

    for assignment in teaching_assignments:
        class_name = (
            assignment.class_name or ""
        ).strip()

        stream = _normalise_stream(
            assignment.stream
        )

        if not class_name:
            continue

        if stream:
            class_pairs.add(
                (
                    class_name,
                    stream,
                )
            )
        else:
            student_pairs = (
                Student.objects
                .filter(class_name=class_name)
                .values_list(
                    "class_name",
                    "stream",
                )
                .distinct()
            )

            for pair in student_pairs:
                class_pairs.add(
                    (
                        pair[0],
                        pair[1] or "",
                    )
                )

    return sorted(
        class_pairs,
        key=lambda pair: (
            pair[0],
            pair[1],
        ),
    )


# ============================================================
# STAFF STUDENTS
# ============================================================

def get_staff_students(user):
    """
    Return students belonging to classes/streams the teacher
    is assigned to.

    Administrators receive all students.
    """
    if is_admin_user(user):
        return Student.objects.all()

    pairs = get_staff_class_pairs(user)

    if not pairs:
        return Student.objects.none()

    query = Q()

    for class_name, stream in pairs:
        class_query = Q(
            class_name=class_name
        )

        if stream:
            class_query &= Q(
                stream=stream
            )

        query |= class_query

    return (
        Student.objects
        .filter(query)
        .distinct()
    )


def teacher_has_student(
    user,
    student,
):
    """
    Determine whether the teacher has access to a student
    through an assigned class/stream.
    """
    if is_admin_user(user):
        return True

    if not student:
        return False

    return (
        get_staff_students(user)
        .filter(pk=student.pk)
        .exists()
    )


# ============================================================
# TIMETABLE
# ============================================================

def get_staff_timetable(user):
    """
    Timetable visibility remains based on timetable ownership.

    This function is intentionally separate from academic and
    attendance permissions.
    """
    if is_admin_user(user):
        return (
            TimetableLesson.objects
            .filter(is_active=True)
            .select_related(
                "teacher",
                "subject",
                "day",
                "period",
                "room",
            )
        )

    teacher = get_staff_teacher(user)

    if not teacher:
        return TimetableLesson.objects.none()

    return (
        TimetableLesson.objects
        .filter(
            teacher=teacher,
            is_active=True,
        )
        .select_related(
            "teacher",
            "subject",
            "day",
            "period",
            "room",
        )
    )


# ============================================================
# CUSTOM ROLE PERMISSION DECORATOR
# ============================================================

from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect


def role_permission_required(permission_codename, app_label):
    """
    Protect a view using the ERP custom Role -> Permission system.

    Superusers are always allowed.
    Otherwise the user's active custom role must contain
    the exact Django permission for the supplied app.
    """

    def decorator(view_func):

        @wraps(view_func)
        def wrapped(request, *args, **kwargs):

            if request.user.is_superuser:
                return view_func(
                    request,
                    *args,
                    **kwargs,
                )

            try:
                profile = request.user.profile
            except Exception:
                messages.error(
                    request,
                    "You do not have permission to access this section.",
                )
                return redirect(
                    "accounts:staff_dashboard"
                )

            if getattr(profile, "role", "") == "ADMIN":
                return view_func(
                    request,
                    *args,
                    **kwargs,
                )

            role = profile.custom_role

            if (
                role is None
                or not role.is_active
                or not role.permissions.filter(
                    codename=permission_codename,
                    content_type__app_label=app_label,
                ).exists()
            ):
                messages.error(
                    request,
                    "You do not have permission to access this section.",
                )
                return redirect(
                    "accounts:staff_dashboard"
                )

            return view_func(
                request,
                *args,
                **kwargs,
            )

        return wrapped

    return decorator








