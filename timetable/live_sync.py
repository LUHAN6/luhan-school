# ============================================================
# ACADEMIC YEAR + TERM LIVE SYNC
# ============================================================

# ============================================================
# ACADEMIC YEAR + TERM LIVE SYNC
# ============================================================

def sync_academic_years_and_terms():
    """
    Pull Academic Years and Terms from the main ERP into
    TimetableTerm without deleting existing timetable data.
    """

    from fees.models import AcademicYear, Term
    from .models import TimetableTerm

    years_created = 0
    years_updated = 0
    terms_created = 0
    terms_updated = 0

    academic_years = AcademicYear.objects.all().order_by("year")

    for academic_year in academic_years:

        terms = Term.objects.filter(is_active=True).order_by("order", "id")

        for term in terms:

            timetable_term, created = TimetableTerm.objects.update_or_create(
                academic_year=academic_year,
                term_name=term.name,
                defaults={
                    "active": bool(
                        getattr(academic_year, "is_active", True)
                        and getattr(term, "is_active", True)
                    )
                }
            )

            if created:
                terms_created += 1
            else:
                terms_updated += 1

        # Count the year as synchronized through its linked terms.
        if academic_year:
            years_updated += 1

    return {
        "years_created": years_created,
        "years_updated": years_updated,
        "terms_created": terms_created,
        "terms_updated": terms_updated,
    }



from django.db import transaction


def sync_timetable_sources():

    # Keep Academic Years and Terms synchronized with Timetabling.
    sync_academic_years_and_terms()
    """
    Keep timetable reference tables synchronized with the main ERP.

    Sources:
      students.Student       -> TimetableClass
      academic.Stream        -> TimetableClass streams
      academic.Subject       -> TimetableSubject
      hr_payroll.Employee    -> TimetableTeacher
    """

    from students.models import Student
    from academic.models import Subject, Stream
    from hr_payroll.models import Employee

    from .models import (
        TimetableClass,
        TimetableSubject,
        TimetableTeacher,
    )

    with transaction.atomic():

        # ----------------------------------------------------
        # SUBJECTS
        # ----------------------------------------------------
        for source in Subject.objects.filter(is_active=True).order_by("name"):

            obj, created = TimetableSubject.objects.get_or_create(
                code=source.code or f"SUB-{source.pk}",
                defaults={
                    "name": source.name,
                    "active": True,
                },
            )

            changed = False

            if obj.name != source.name:
                obj.name = source.name
                changed = True

            if hasattr(obj, "active") and not obj.active:
                obj.active = True
                changed = True

            if changed:
                obj.save()

        # ----------------------------------------------------
        # TEACHERS / STAFF
        # ----------------------------------------------------
        for source in Employee.objects.filter(
            is_active=True
        ).order_by("first_name", "last_name"):

            full_name = " ".join(
                x for x in [
                    source.first_name,
                    source.middle_name,
                    source.last_name,
                ]
                if x
            ).strip()

            staff_number = (
                source.employee_number
                or f"EMP-{source.pk}"
            )

            # HR Employee is the authoritative staff record.
            # Keep the direct Employee -> TimetableTeacher relationship.
            obj = TimetableTeacher.objects.filter(
                employee=source
            ).first()

            # Recover an existing teacher record created before the
            # employee relationship was populated.
            if obj is None:
                obj = TimetableTeacher.objects.filter(
                    staff_number=staff_number
                ).first()

            if obj is None:
                obj = TimetableTeacher.objects.create(
                    employee=source,
                    staff_number=staff_number,
                    name=full_name,
                    email=source.email or "",
                    active=True,
                )
                changed = False
            else:
                changed = False

                if obj.employee_id != source.pk:
                    obj.employee = source
                    changed = True

                if obj.name != full_name:
                    obj.name = full_name
                    changed = True

                if obj.staff_number != staff_number:
                    obj.staff_number = staff_number
                    changed = True

                if obj.email != (source.email or ""):
                    obj.email = source.email or ""
                    changed = True

                if hasattr(obj, "active") and not obj.active:
                    obj.active = True
                    changed = True

                if changed:
                    obj.save()

        # ----------------------------------------------------
        # CLASSES / GRADES + STREAMS
        # ----------------------------------------------------

        # First use the actual student records because
        # Student.class_name is the ERP's current class/grade source.
        student_pairs = (
            Student.objects
            .exclude(class_name__isnull=True)
            .exclude(class_name__exact="")
            .values_list("class_name", "stream")
            .distinct()
        )

        seen = set()

        for class_name, stream in student_pairs:

            class_name = (class_name or "").strip()
            stream = (stream or "").strip()

            if not class_name:
                continue

            key = (class_name.lower(), stream.lower())

            if key in seen:
                continue

            seen.add(key)

            obj = TimetableClass.objects.filter(
                name__iexact=class_name,
                stream__iexact=stream,
            ).first()

            if obj is None:
                obj = TimetableClass.objects.create(
                    name=class_name,
                    stream=stream,
                    level=class_name,
                    active=True,
                )
            else:
                changed = False

                if hasattr(obj, "level") and obj.level != class_name:
                    obj.level = class_name
                    changed = True

                if hasattr(obj, "active") and not obj.active:
                    obj.active = True
                    changed = True

                if changed:
                    obj.save()

        # ----------------------------------------------------
        # ACADEMIC STREAMS
        # ----------------------------------------------------
        for stream in Stream.objects.filter(
            is_active=True
        ).order_by("name"):

            stream_name = (stream.name or "").strip()

            if not stream_name:
                continue

            # If the stream exists in student data it has
            # already been attached to its class above.
            # We do not invent a grade where none exists.

        print(
            "LIVE TIMETABLE SYNC COMPLETE: "
            f"{TimetableClass.objects.filter(active=True).count()} classes, "
            f"{TimetableSubject.objects.filter(active=True).count()} subjects, "
            f"{TimetableTeacher.objects.filter(active=True).count()} teachers."
        )
