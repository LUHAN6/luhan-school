from django.db.models import Q


def _find_employee(user):
    if not user:
        return None

    try:
        from hr_payroll.models import Employee
    except Exception:
        return None

    # Direct user relation where present.
    try:
        field_names = {
            f.name
            for f in Employee._meta.get_fields()
        }

        if "user" in field_names:
            employee = Employee.objects.filter(
                user=user
            ).first()

            if employee:
                return employee
    except Exception:
        pass

    # Common related-object paths.
    paths = [
        "employee",
        "staff",
        "employee_profile",
        "staff_profile",
    ]

    for path in paths:
        try:
            obj = getattr(user, path, None)

            if obj is not None:
                employee = getattr(obj, "employee", None)

                if employee is not None:
                    return employee

                if obj.__class__.__name__ == "Employee":
                    return obj
        except Exception:
            pass

    # Profile relationships.
    try:
        profile = getattr(user, "profile", None)

        if profile:

            employee = getattr(
                profile,
                "employee",
                None,
            )

            if employee:
                return employee

            employee = getattr(
                profile,
                "staff",
                None,
            )

            if employee:
                return employee
    except Exception:
        pass

    # Email fallback.
    try:
        if user.email:
            employee = Employee.objects.filter(
                email__iexact=user.email
            ).first()

            if employee:
                return employee
    except Exception:
        pass

    return None


def get_staff_teacher(user):
    """
    Resolve an authenticated ERP staff user to the
    canonical TimetableTeacher through the HR Employee record.

    The Employee -> TimetableTeacher relationship is authoritative.
    No username, email, name, or staff-number fallback is used.
    """
    if not user:
        return None

    try:
        from timetable.models import TimetableTeacher
    except Exception:
        return None

    employee = _find_employee(user)

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


def is_class_teacher_for(
    user,
    class_name,
    stream=None,
):
    teacher = get_staff_teacher(user)

    if not teacher:
        return False

    from timetable.advanced_models import (
        TimetableTeacherClassAssignment,
    )

    qs = TimetableTeacherClassAssignment.objects.filter(
        teacher=teacher,
        class_name__iexact=(class_name or "").strip(),
        is_active=True,
    )

    if stream not in (None, ""):
        qs = qs.filter(
            Q(stream__iexact=str(stream).strip())
            | Q(stream__isnull=True)
            | Q(stream="")
        )

    return qs.exists()


def get_staff_subjects_for_class(
    user,
    class_name,
    stream=None,
):
    """
    Return academic Subject objects corresponding to the
    canonical Timetabling teaching assignments.
    """
    teacher = get_staff_teacher(user)

    if not teacher:
        return []

    from timetable.models import TimetableSubject

    from timetable.advanced_models import (
        TimetableTeacherTeachingAssignment,
        TimetableTeacherSubject,
    )

    timetable_subjects = []

    assignments = (
        TimetableTeacherTeachingAssignment.objects
        .filter(
            teacher=teacher,
            class_name__iexact=(class_name or "").strip(),
            is_active=True,
        )
    )

    if stream not in (None, ""):
        assignments = assignments.filter(
            Q(stream__iexact=str(stream).strip())
            | Q(stream="")
            | Q(stream__isnull=True)
        )

    for assignment in assignments.select_related("subject"):
        timetable_subjects.append(
            assignment.subject
        )

    # Fallback to teacher-subject links when no
    # class-specific teaching assignment exists.
    if not timetable_subjects:
        timetable_subjects = list(
            TimetableSubject.objects.filter(
                teacher_links__teacher=teacher,
                teacher_links__is_active=True,
                active=True,
            ).distinct()
        )

    codes = {
        (s.code or "").strip()
        for s in timetable_subjects
        if s.code
    }

    names = {
        s.name.strip()
        for s in timetable_subjects
        if s.name
    }

    try:
        from academic.models import Subject

        result = []

        for subject in Subject.objects.filter(
            is_active=True
        ).order_by("name"):

            if (
                subject.code
                and subject.code.strip() in codes
            ) or (
                subject.name
                and subject.name.strip() in names
            ):
                result.append(subject)

        return result

    except Exception:
        return timetable_subjects
