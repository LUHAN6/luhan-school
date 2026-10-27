from django.db.models import Max
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.urls import reverse

from .models import (
    TimetableDay,
    TimetablePeriod,
    TimetableTerm,
    TimetableClass,
    TimetableSubject,
    TimetableTeacher,
    TimetableRoom,
    LessonRequirement,
    TeacherAvailability,
    TimetableLesson,
)


# ============================================================
# STAFF PERMISSION GATE
# ============================================================
#
# Timetable module access is controlled by the existing
# Admin Portal Custom Role -> Django Permission system.
#
# Operational teacher/class/subject assignment remains
# separate and is enforced by the relevant views.

def _timetable_permission_allowed(user, codename):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    try:
        profile = user.profile
    except Exception:
        return False

    if getattr(profile, "role", "") == "ADMIN":
        return True

    custom_role = getattr(profile, "custom_role", None)
    if not custom_role or not custom_role.is_active:
        return False

    return custom_role.permissions.filter(
        codename=codename,
        content_type__app_label="timetable",
    ).exists()

def _timetable_admin_allowed(user):
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    try:
        profile = user.profile
    except Exception:
        return False

    return getattr(profile, "role", "") == "ADMIN"


def _timetable_admin_redirect(request):
    if _timetable_admin_allowed(request.user):
        return None

    messages.error(
        request,
        "Only timetable administrators can perform this whole-school operation.",
    )
    return redirect("accounts:staff_dashboard")

def _timetable_permission_redirect(request, codename):
    if _timetable_permission_allowed(request.user, codename):
        return None

    messages.error(
        request,
        "You do not have permission to access this timetable section.",
    )
    return redirect("accounts:staff_dashboard")

def dashboard(request):
    denied = _timetable_permission_redirect(request, "view_timetablelesson")
    if denied:
        return denied

    is_timetable_admin = _timetable_admin_allowed(request.user)

    if is_timetable_admin:
        context = {
            "classes_count": TimetableClass.objects.filter(active=True).count(),
            "subjects_count": TimetableSubject.objects.filter(active=True).count(),
            "teachers_count": TimetableTeacher.objects.filter(active=True).count(),
            "rooms_count": TimetableRoom.objects.filter(active=True).count(),
            "requirements_count": LessonRequirement.objects.filter(active=True).count(),
            "lessons_count": TimetableLesson.objects.count(),
        }
    else:
        from .staff_utils import get_staff_teacher

        staff_teacher = get_staff_teacher(request.user)

        if not staff_teacher:
            messages.error(
                request,
                "Your staff account is not linked to an active timetable teacher."
            )
            return redirect("accounts:staff_dashboard")

        context = {
            "classes_count": TimetableClass.objects.filter(
                active=True,
                lesson_requirements__teacher=staff_teacher,
            ).distinct().count(),
            "subjects_count": TimetableSubject.objects.filter(
                active=True,
                lesson_requirements__teacher=staff_teacher,
            ).distinct().count(),
            "teachers_count": 1,
            "rooms_count": TimetableRoom.objects.filter(
                active=True,
                lesson_requirements__teacher=staff_teacher,
            ).distinct().count(),
            "requirements_count": LessonRequirement.objects.filter(
                active=True,
                teacher=staff_teacher,
            ).count(),
            "lessons_count": TimetableLesson.objects.filter(
                teacher=staff_teacher,
            ).count(),
        }

    context["is_timetable_admin"] = is_timetable_admin

    return render(request, "timetable/dashboard.html", context)

@login_required
def setup(request):
    denied = _timetable_permission_redirect(request, "view_timetableconfiguration")
    if denied:
        return denied
    from academic.models import AcademicYear, Term
    from .models import TimetableTerm

    academic_years = AcademicYear.objects.filter(
        is_active=True
    ).order_by("-year")

    terms = Term.objects.filter(
        is_active=True
    ).order_by("order")

    if request.method == "POST":
        selected_year = request.POST.get("academic_year", "").strip()
        selected_term = request.POST.get("term", "").strip()

        if not selected_year or not selected_term:
            messages.error(
                request,
                "Please select both Academic Year and Term."
            )
            return redirect("timetable:setup")

        timetable_term, created = TimetableTerm.objects.get_or_create(
            academic_year=selected_year,
            term_name=selected_term,
            defaults={
                "active": True,
            },
        )

        request.session["timetable_term_id"] = timetable_term.id
        request.session["timetable_academic_year"] = selected_year
        request.session["timetable_term_name"] = selected_term
        request.session.modified = True

        messages.success(
            request,
            f"Timetable term selected: {selected_year} - {selected_term}"
        )

        return redirect("timetable:setup")

    timetable_terms = TimetableTerm.objects.filter(
        active=True
    ).order_by("-academic_year", "term_name")

    selected_timetable_term = None

    selected_id = request.session.get("timetable_term_id")

    if selected_id:
        selected_timetable_term = TimetableTerm.objects.filter(
            id=selected_id,
            active=True,
        ).first()

    if not selected_timetable_term:
        if academic_years.exists() and terms.exists():
            selected_year = str(academic_years.first().year)
            selected_term = str(terms.first().name)

            selected_timetable_term = TimetableTerm.objects.filter(
                academic_year=selected_year,
                term_name=selected_term,
                active=True,
            ).first()

    return render(
        request,
        "timetable/setup.html",
        {
            "academic_years": academic_years,
            "terms": terms,
            "timetable_terms": timetable_terms,
            "selected_timetable_term": selected_timetable_term,
        },
    )


def get_selected_timetable_term(request):
    from .models import TimetableTerm, TimetableLesson

    # First honour an explicitly selected term.
    term_id = request.session.get("timetable_term_id")

    if term_id:
        term = TimetableTerm.objects.filter(
            id=term_id,
            active=True
        ).first()

        if term:
            return term

    # If no term has been selected, show the term that
    # currently contains generated lessons.
    term_with_lessons = (
        TimetableTerm.objects
        .filter(active=True, lessons__isnull=False)
        .distinct()
        .order_by("-academic_year", "-id")
        .first()
    )

    if term_with_lessons:
        return term_with_lessons

    # Final fallback.
    return (
        TimetableTerm.objects
        .filter(active=True)
        .order_by("-academic_year", "term_name")
        .first()
    )

def classes(request):
    denied = _timetable_permission_redirect(request, "view_timetableclass")
    if denied:
        return denied

    items = TimetableClass.objects.all()
    return render(request, "timetable/list.html", {
        "title": "Classes & Streams",
        "items": items,
        "back": "/timetable/",
        "empty": "No classes have been added yet.",
    })


@login_required
def subjects(request):
    denied = _timetable_permission_redirect(request, "view_timetablesubject")
    if denied:
        return denied
    items = TimetableSubject.objects.all()
    return render(request, "timetable/list.html", {
        "title": "Subjects",
        "items": items,
        "back": "/timetable/",
        "empty": "No subjects have been added yet.",
    })


@login_required
def teachers(request):
    denied = _timetable_permission_redirect(request, "view_timetableteacher")
    if denied:
        return denied
    items = TimetableTeacher.objects.all()
    return render(request, "timetable/list.html", {
        "title": "Teachers",
        "items": items,
        "back": "/timetable/",
        "empty": "No teachers have been added yet.",
    })


@login_required
def rooms(request):
    denied = _timetable_permission_redirect(request, "view_timetableroom")
    if denied:
        return denied
    items = TimetableRoom.objects.all()
    return render(request, "timetable/list.html", {
        "title": "Rooms",
        "items": items,
        "back": "/timetable/",
        "empty": "No rooms have been added yet.",
    })


@login_required
def requirements(request):
    denied = _timetable_permission_redirect(request, "view_lessonrequirement")
    if denied:
        return denied
    items = LessonRequirement.objects.select_related(
        "class_group",
        "subject",
        "teacher",
        "room",
    )
    return render(request, "timetable/requirements.html", {
        "items": items,
    })


@login_required
def availability(request):
    denied = _timetable_permission_redirect(request, "view_teacheravailability")
    if denied:
        return denied
    items = TeacherAvailability.objects.select_related(
        "teacher",
        "day",
        "period",
    )
    return render(request, "timetable/availability.html", {
        "items": items,
    })


@login_required
def workspace(request):
    denied = _timetable_permission_redirect(request, "view_timetablelesson")
    if denied:
        return denied

    is_timetable_admin = _timetable_admin_allowed(request.user)
    staff_teacher = None

    if not is_timetable_admin:
        from .staff_utils import get_staff_teacher

        staff_teacher = get_staff_teacher(request.user)

        if not staff_teacher:
            messages.error(
                request,
                "Your staff account is not linked to an active timetable teacher."
            )
            return redirect("accounts:staff_dashboard")

    from .models import (
        TimetableLesson,
        TimetableDay,
        TimetablePeriod,
    )

    term = get_selected_timetable_term(request)

    from .complete_timetable_system import (
        check_timetable,
        current_draft,
        published_version,
    )

    draft_version = (
        current_draft(term)
        if term
        else None
    )

    global_published = published_version()

    published_for_term = None

    if (
        global_published
        and term
        and global_published.term_id == term.id
    ):
        published_for_term = global_published

    active_version = (
        draft_version
        or published_for_term
    )

    conflict_result = (
        check_timetable(term)
        if term
        else {
            "ok": True,
            "conflicts": [],
            "count": 0,
        }
    )

    conflict_count = len(
        conflict_result.get(
            "conflicts",
            []
        )
    )

    days = list(
        TimetableDay.objects.filter(active=True)
        .order_by("order")
    )

    periods = list(
        TimetablePeriod.objects.filter(active=True)
        .order_by("order")
    )

    lessons = []

    if term:
        lesson_qs = TimetableLesson.objects.filter(
            term=term,
            is_active=True,
        )

        if not is_timetable_admin:
            lesson_qs = lesson_qs.filter(
                teacher=staff_teacher
            )

        if active_version:
            lesson_qs = lesson_qs.filter(
                version=active_version
            )

        lessons = list(
            lesson_qs
            .select_related(
                "class_group",
                "subject",
                "teacher",
                "room",
                "day",
                "period",
            )
            .order_by(
                "day__order",
                "class_group__name",
                "class_group__stream",
                "period__order",
            )
        )

    grouped = {}

    for lesson in lessons:
        key = (lesson.day_id, lesson.class_group_id)

        if key not in grouped:
            grouped[key] = {
                "day": lesson.day,
                "class_group": lesson.class_group,
                "lessons": {},
            }

        grouped[key]["lessons"][lesson.period_id] = lesson

    master_rows = []

    for day in days:

        day_rows = [
            row for key, row in grouped.items()
            if key[0] == day.id
        ]

        day_rows.sort(
            key=lambda row: (
                row["class_group"].name,
                row["class_group"].stream,
            )
        )

        # Always display every active school day.
        # If there are no lessons/classes for this day,
        # create one empty timetable row.
        if not day_rows:
            empty_cells = []

            for period in periods:
                empty_cells.append({
                    "period": period,
                    "lesson": None,
                    "colspan": 1,
                })

            master_rows.append({
                "day": day,
                "class_group": None,
                "cells": empty_cells,
                "first_day_row": True,
                "day_rowspan": 1,
                "empty_day": True,
            })

            continue

        for index, row in enumerate(day_rows):

            lesson_map = row["lessons"]
            cells = []
            skip_period_ids = set()

            for i, period in enumerate(periods):

                if period.id in skip_period_ids:
                    continue

                lesson = lesson_map.get(period.id)

                if lesson:

                    duration = max(1, int(lesson.duration_periods or 1))

                    colspan = 1
                    covered = []

                    if duration > 1:
                        for next_period in periods[i + 1:]:
                            if next_period.is_break or next_period.is_lunch or next_period.is_activity:
                                break

                            if next_period.id in lesson_map:
                                break

                            covered.append(next_period.id)

                            if len(covered) >= duration - 1:
                                break

                        colspan += len(covered)
                        skip_period_ids.update(covered)

                    cells.append({
                        "period": period,
                        "lesson": lesson,
                        "colspan": colspan,
                    })

                else:
                    cells.append({
                        "period": period,
                        "lesson": None,
                        "colspan": 1,
                    })

            master_rows.append({
                "day": day,
                "class_group": row["class_group"],
                "cells": cells,
                "first_day_row": index == 0,
                "day_rowspan": len(day_rows),
            })

    workspace_conflict_count = conflict_count if is_timetable_admin else 0
    workspace_conflicts = (
        conflict_result.get("conflicts", [])
        if is_timetable_admin
        else []
    )

    return render(
        request,
        "timetable/workspace.html",
        {
            "term": term,
            "days": days,
            "periods": periods,
            "lessons": lessons,
            "master_rows": master_rows,
            "generation_result": request.session.get(
                "timetable_generation_result"
            ),
            "draft_version": draft_version,
            "published_version": published_for_term,
            "active_version": active_version,
            "is_timetable_admin": is_timetable_admin,
            "conflict_count": workspace_conflict_count,
            "conflicts": workspace_conflicts,
        },
    )


def conflicts(request):
    lessons = TimetableLesson.objects.select_related(
        "class_group",
        "subject",
        "teacher",
        "room",
        "day",
        "period",
    )

    conflicts = []

    seen_classes = {}
    seen_teachers = {}
    seen_rooms = {}

    for lesson in lessons:
        key = (lesson.day_id, lesson.period_id)

        if lesson.class_group_id:
            if (key, lesson.class_group_id) in seen_classes:
                conflicts.append(
                    f"Class clash: {lesson.class_group} at "
                    f"{lesson.day} / {lesson.period}"
                )
            seen_classes[(key, lesson.class_group_id)] = lesson.id

        if lesson.teacher_id:
            if (key, lesson.teacher_id) in seen_teachers:
                conflicts.append(
                    f"Teacher clash: {lesson.teacher} at "
                    f"{lesson.day} / {lesson.period}"
                )
            seen_teachers[(key, lesson.teacher_id)] = lesson.id

        if lesson.room_id:
            if (key, lesson.room_id) in seen_rooms:
                conflicts.append(
                    f"Room clash: {lesson.room} at "
                    f"{lesson.day} / {lesson.period}"
                )
            seen_rooms[(key, lesson.room_id)] = lesson.id

    return render(request, "timetable/conflicts.html", {
        "conflicts": conflicts,
    })



# ============================================================
# CRUD CONTROL CENTRE
# ============================================================

from django import forms
from django.core.exceptions import FieldDoesNotExist
from django.db.models import Q
from django.shortcuts import get_object_or_404


CRUD_MODELS = {
    "terms": TimetableTerm,
    "days": TimetableDay,
    "periods": TimetablePeriod,
    "classes": TimetableClass,
    "subjects": TimetableSubject,
    "teachers": TimetableTeacher,
    "rooms": TimetableRoom,
    "requirements": LessonRequirement,
    "availability": TeacherAvailability,
}


CRUD_LABELS = {
    "terms": "Timetable Terms",
    "days": "Timetable Days",
    "periods": "Timetable Periods",
    "classes": "Timetable Classes",
    "subjects": "Timetable Subjects",
    "teachers": "Timetable Teachers",
    "rooms": "Timetable Rooms",
    "requirements": "Lesson Requirements",
    "availability": "Teacher Availability",
}


def _crud_model(key):
    return CRUD_MODELS.get(key)


def _crud_label(key):
    return CRUD_LABELS.get(key, key.replace("_", " ").title())


# ============================================================
# GENERIC TIMETABLE CRUD PERMISSION GATE
# ============================================================
#
# Generic /manage/<model_key>/ routes use the existing
# Admin Portal -> Custom Role -> Django Permission system.
#
# Module permission and operational teacher/class/subject
# scope remain separate.
# ============================================================

CRUD_PERMISSION_CODENAMES = {
    "terms": "timetableterm",
    "days": "timetableday",
    "periods": "timetableperiod",
    "classes": "timetableclass",
    "subjects": "timetablesubject",
    "teachers": "timetableteacher",
    "rooms": "timetableroom",
    "requirements": "lessonrequirement",
    "availability": "teacheravailability",
}


def _crud_permission_allowed(user, model_key, action):
    if user.is_superuser:
        return True

    try:
        profile = user.profile
    except Exception:
        return False

    if getattr(profile, "role", "") == "ADMIN":
        return True

    custom_role = getattr(profile, "custom_role", None)

    if not custom_role or not custom_role.is_active:
        return False

    model_codename = CRUD_PERMISSION_CODENAMES.get(model_key)

    if not model_codename:
        return False

    return custom_role.permissions.filter(
        codename=f"{action}_{model_codename}",
        content_type__app_label="timetable",
    ).exists()


def _crud_permission_redirect(request, model_key, action):
    if _crud_permission_allowed(
        request.user,
        model_key,
        action,
    ):
        return None

    messages.error(
        request,
        "You do not have permission to access this timetable section.",
    )
    return redirect("accounts:staff_dashboard")

def _model_fields_for_form(model):
    fields = []

    for field in model._meta.get_fields():

        if getattr(field, "auto_created", False):
            continue

        if getattr(field, "many_to_many", False):
            fields.append(field.name)
            continue

        if not hasattr(field, "editable") or field.editable:
            if field.name not in ("id",):
                fields.append(field.name)

    return fields


def _make_crud_form(model, instance=None):
    field_names = _model_fields_for_form(model)

    # Order is automatically controlled for periods/breaks.
    if model.__name__ == "TimetablePeriod" and "order" in field_names:
        field_names.remove("order")

    Meta = type(
        "Meta",
        (),
        {
            "model": model,
            "fields": field_names,
        },
    )

    CrudForm = type(
        f"{model.__name__}CrudForm",
        (forms.ModelForm,),
        {"Meta": Meta},
    )

    form = CrudForm(instance=instance)

    # ---------------------------------------------------------
    # PERIOD TIME PICKERS
    # ---------------------------------------------------------
    # For Periods & Breaks, use the browser's clock/time picker
    # instead of requiring manual time entry.
    if model.__name__ == "TimetablePeriod":

        if "start_time" in form.fields:
            form.fields["start_time"].widget = forms.TimeInput(
                format="%H:%M",
                attrs={
                    "type": "time",
                    "step": "300",
                },
            )

        if "end_time" in form.fields:
            form.fields["end_time"].widget = forms.TimeInput(
                format="%H:%M",
                attrs={
                    "type": "time",
                    "step": "300",
                },
            )

    return form


@login_required
def control_centre(request):
    denied = _timetable_admin_redirect(request)
    if denied:
        return denied

    cards = []

    for key, model in CRUD_MODELS.items():
        try:
            count = model.objects.count()
        except Exception:
            count = 0

        cards.append(
            {
                "key": key,
                "label": _crud_label(key),
                "count": count,
            }
        )

    return render(
        request,
        "timetable/control_centre.html",
        {
            "cards": cards,
        },
    )

@login_required
def crud_list(request, model_key):
    denied = _crud_permission_redirect(
        request,
        model_key,
        "view",
    )

    if denied:
        return denied
    from django.contrib import messages

    if model_key not in CRUD_MODELS:
        messages.error(request, "Invalid timetable section.")
        return redirect("timetable:control_centre")

    model = CRUD_MODELS[model_key]
    objects = model.objects.all()

    # Prepare field information in Python.
    # Django templates must NOT access model._meta directly.
    field_data = []

    for field in model._meta.fields:
        if field.name == "id":
            continue

        field_data.append({
            "name": field.name,
            "verbose_name": field.verbose_name,
        })

    # Prepare row values in Python so the template
    # never needs getattr() or _meta.
    for obj in objects:
        obj.row_values = []

        for field in field_data:
            value = getattr(obj, field["name"], "")
            obj.row_values.append(str(value if value is not None else ""))

    title_map = {
        "terms": "Academic Years & Terms",
        "days": "School Days",
        "periods": "Periods & Breaks",
        "classes": "Classes",
        "subjects": "Subjects",
        "teachers": "Teachers",
        "rooms": "Rooms",
        "requirements": "Lesson Requirements",
        "availability": "Teacher Availability",
    }

    title = title_map.get(model_key, model.__name__)

    return render(
        request,
        "timetable/crud_list.html",
        {
            "model": model,
            "model_key": model_key,
            "objects": objects,
            "title": title,
            "field_data": field_data,
        },
    )

@login_required
def crud_create(request, model_key):
    action = "add" if request.method == "POST" else "view"

    denied = _crud_permission_redirect(
        request,
        model_key,
        action,
    )

    if denied:
        return denied
    model = _crud_model(model_key)

    if model is None:
        messages.error(request, "Unknown timetable section.")
        return redirect("timetable:control_centre")

    form = _make_crud_form(model)

    # ---------------------------------------------------------
    # PERIOD ADD: START TIME = PREVIOUS PERIOD/BREAK END TIME
    # ---------------------------------------------------------
    if model_key == "periods" and request.method == "GET":

        previous_item = (
            model.objects
            .filter(active=True)
            .exclude(end_time__isnull=True)
            .order_by("-order", "-id")
            .first()
        )

        if previous_item and previous_item.end_time:

            previous_end = previous_item.end_time

            # Give the browser time input an exact HH:MM value.
            if hasattr(previous_end, "strftime"):
                previous_end = previous_end.strftime("%H:%M")

            form.initial["start_time"] = previous_end

            if "start_time" in form.fields:
                form.fields["start_time"].initial = previous_end

    if request.method == "POST":
        form = type(form)(request.POST, request.FILES)

        if form.is_valid():
            obj = form.save()

            if model_key == "periods":
                _reorder_periods(model)

            messages.success(
                request,
                f"{_crud_label(model_key)} record created successfully."
            )

            return redirect(
                "timetable:crud_list",
                model_key=model_key,
            )

    return render(
        request,
        "timetable/crud_form.html",
        {
            "form": form,
            "model_key": model_key,
            "model_label": _crud_label(model_key),
            "action": "Add",
        },
    )


def _reorder_periods(model):
    """
    Automatically assign order numbers according to timetable
    start time. Users never manage order manually.
    """

    items = list(
        model.objects
        .filter(active=True)
        .order_by("start_time", "end_time", "id")
    )

    for index, item in enumerate(items, start=1):
        if item.order != index:
            item.order = index
            item.save(update_fields=["order"])


def _cascade_period_times(model, edited_object):
    """
    After editing an item, keep every following period/break
    connected continuously while preserving each item's duration.
    """

    from datetime import datetime, timedelta

    # Use the current timetable order.
    items = list(
        model.objects
        .filter(active=True)
        .order_by("order", "id")
    )

    try:
        edited_index = next(
            i for i, item in enumerate(items)
            if item.pk == edited_object.pk
        )
    except StopIteration:
        return

    previous_end = edited_object.end_time

    if not previous_end:
        return

    for item in items[edited_index + 1:]:

        if not item.start_time or not item.end_time:
            continue

        old_start = datetime.combine(
            datetime.today().date(),
            item.start_time
        )

        old_end = datetime.combine(
            datetime.today().date(),
            item.end_time
        )

        duration = old_end - old_start

        if duration.total_seconds() <= 0:
            duration += timedelta(days=1)

        new_start = datetime.combine(
            datetime.today().date(),
            previous_end
        )

        new_end = new_start + duration

        item.start_time = new_start.time()
        item.end_time = new_end.time()

        item.save(
            update_fields=["start_time", "end_time"]
        )

        previous_end = item.end_time

    # Finally rebuild the automatic order.
    _reorder_periods(model)

@login_required
def crud_edit(request, model_key, pk):
    action = "change" if request.method == "POST" else "view"

    denied = _crud_permission_redirect(
        request,
        model_key,
        action,
    )

    if denied:
        return denied
    model = _crud_model(model_key)

    if model is None:
        messages.error(request, "Unknown timetable section.")
        return redirect("timetable:control_centre")

    obj = get_object_or_404(model, pk=pk)

    form = _make_crud_form(model, obj)

    if request.method == "POST":
        form = type(form)(request.POST, request.FILES, instance=obj)

        if form.is_valid():
            obj = form.save()

            # -------------------------------------------------
            # PERIOD TIME CASCADE + AUTOMATIC ORDER
            # -------------------------------------------------
            if model_key == "periods":
                _cascade_period_times(model, obj)

            messages.success(
                request,
                f"{_crud_label(model_key)} record updated successfully."
            )

            return redirect(
                "timetable:crud_list",
                model_key=model_key,
            )

    return render(
        request,
        "timetable/crud_form.html",
        {
            "form": form,
            "model_key": model_key,
            "model_label": _crud_label(model_key),
            "action": "Edit",
            "object": obj,
        },
    )


@login_required
def crud_delete(request, model_key, pk):
    action = "delete" if request.method == "POST" else "view"

    denied = _crud_permission_redirect(
        request,
        model_key,
        action,
    )

    if denied:
        return denied
    model = _crud_model(model_key)

    if model is None:
        messages.error(request, "Unknown timetable section.")
        return redirect("timetable:control_centre")

    obj = get_object_or_404(model, pk=pk)

    if request.method == "POST":
        obj.delete()

        messages.success(
            request,
            f"{_crud_label(model_key)} record deleted."
        )

        return redirect(
            "timetable:crud_list",
            model_key=model_key,
        )

    return render(
        request,
        "timetable/crud_delete.html",
        {
            "object": obj,
            "model_key": model_key,
            "model_label": _crud_label(model_key),
        },
    )



# ============================================================
# TIMETABLE GENERATION / WORKSPACE
# ============================================================

@login_required
def publish_timetable(request):
    denied = _timetable_admin_redirect(request)
    if denied:
        return denied

    denied = _timetable_permission_redirect(request, "change_timetableversion")
    if denied:
        return denied
    from django.contrib import messages

    from .complete_timetable_system import (
        check_timetable,
        current_draft,
        publish_draft,
    )

    if request.method != "POST":
        return redirect(
            "timetable:workspace"
        )

    term = get_selected_timetable_term(
        request
    )

    if not term:
        messages.error(
            request,
            "No active timetable term is configured."
        )
        return redirect(
            "timetable:setup"
        )

    draft = current_draft(
        term
    )

    if not draft:
        messages.error(
            request,
            (
                f"No draft timetable exists for {term}. "
                "Generate a timetable first."
            )
        )
        return redirect(
            "timetable:workspace"
        )

    result = check_timetable(
        draft.term
    )

    if not result["ok"]:

        count = len(
            result.get(
                "conflicts",
                []
            )
        )

        messages.error(
            request,
            (
                "Timetable cannot be published. "
                f"{count} conflict(s) detected."
            )
        )

        return redirect(
            "timetable:conflicts"
        )

    published = publish_draft(
        term
    )

    if isinstance(
        published,
        dict,
    ):

        conflicts = published.get(
            "conflicts",
            []
        )

        messages.error(
            request,
            (
                "Timetable publication failed. "
                f"{len(conflicts)} conflict(s) detected."
            )
        )

        return redirect(
            "timetable:conflicts"
        )

    if not published:

        messages.error(
            request,
            "No draft timetable was available for publication."
        )

        return redirect(
            "timetable:workspace"
        )

    request.session.pop(
        "timetable_generation_result",
        None,
    )

    request.session.modified = True

    messages.success(
        request,
        (
            f"Timetable published successfully for "
            f"{published.term}. "
            f"Version: {published.name}"
        )
    )

    return redirect(
        "timetable:workspace"
    )

@login_required
def generate_timetable(request):
    denied = _timetable_admin_redirect(request)
    if denied:
        return denied

    denied = _timetable_permission_redirect(request, "add_timetablelesson")
    if denied:
        return denied
    from django.contrib import messages
    from .generator_engine import TimetableGenerator

    if request.method != "POST":
        return redirect("timetable:workspace")

    term = get_selected_timetable_term(request)

    if not term:
        messages.error(
            request,
            "No active timetable term is configured. Please select an Academic Year and Term first."
        )
        return redirect("timetable:setup")

    generator = TimetableGenerator(term)
    result = generator.generate()

    version = result.get("version")

    safe_result = {
        "term": str(result.get("term", term)),
        "created": int(result.get("created", 0)),
        "requested": int(result.get("requested", 0)),
        "locked": int(result.get("locked", 0)),
        "failed": result.get("failed", []),
        "version_id": (
            getattr(
                version,
                "id",
                result.get("version_id")
            )
        ),
        "version_name": (
            getattr(
                version,
                "name",
                result.get("version_name", "")
            )
        ),
        "version_status": "DRAFT",
    }

    request.session["timetable_generation_result"] = safe_result
    request.session.modified = True

    created = safe_result["created"]
    failed = safe_result["failed"]

    if failed:
        messages.warning(
            request,
            f"Timetable generated for {term}. "
            f"{created} lesson(s) created; "
            f"{len(failed)} lesson(s) could not be placed."
        )
    else:
        messages.success(
            request,
            f"Timetable generated successfully for {term}. "
            f"{created} lesson(s) created."
        )

    return redirect("timetable:workspace")


@login_required
def clear_generated_timetable(request):
    denied = _timetable_admin_redirect(request)
    if denied:
        return denied

    denied = _timetable_permission_redirect(
        request,
        "delete_timetablelesson",
    )

    if denied:
        return denied
    from django.contrib import messages
    from .advanced_models import TimetableVersion

    if request.method != "POST":
        return redirect(
            "timetable:workspace"
        )

    term = get_selected_timetable_term(
        request
    )

    if not term:
        messages.error(
            request,
            "No active timetable term found."
        )
        return redirect(
            "timetable:workspace"
        )

    draft_versions = list(
        TimetableVersion.objects.filter(
            term=term,
            status=TimetableVersion.STATUS_DRAFT,
        )
    )

    draft_ids = [
        version.id
        for version in draft_versions
    ]

    deleted = 0

    if draft_ids:

        deleted, _ = (
            TimetableLesson.objects.filter(
                version_id__in=draft_ids,
                locked=False,
                is_published=False,
            ).delete()
        )

        TimetableVersion.objects.filter(
            id__in=draft_ids
        ).delete()

    unversioned_deleted, _ = (
        TimetableLesson.objects.filter(
            term=term,
            version__isnull=True,
            locked=False,
            is_published=False,
        ).delete()
    )

    deleted += unversioned_deleted

    messages.success(
        request,
        (
            f"{deleted} generated lesson record(s) cleared. "
            "Published and locked lessons were preserved."
        )
    )

    return redirect(
        "timetable:workspace"
    )


@login_required
def conflicts(request):
    conflicts = []

    lessons = TimetableLesson.objects.select_related(
        "class_group",
        "subject",
        "teacher",
        "room",
        "day",
        "period",
    )

    seen_class = {}
    seen_teacher = {}
    seen_room = {}

    for lesson in lessons:

        class_key = (
            lesson.class_group_id,
            lesson.day_id,
            lesson.period_id,
        )

        teacher_key = (
            lesson.teacher_id,
            lesson.day_id,
            lesson.period_id,
        )

        room_key = (
            lesson.room_id,
            lesson.day_id,
            lesson.period_id,
        )

        if class_key in seen_class:
            conflicts.append(
                f"Class clash: {lesson} and "
                f"{seen_class[class_key]}"
            )
        else:
            seen_class[class_key] = lesson

        if lesson.teacher_id:
            if teacher_key in seen_teacher:
                conflicts.append(
                    f"Teacher clash: {lesson} and "
                    f"{seen_teacher[teacher_key]}"
                )
            else:
                seen_teacher[teacher_key] = lesson

        if lesson.room_id:
            if room_key in seen_room:
                conflicts.append(
                    f"Room clash: {lesson} and "
                    f"{seen_room[room_key]}"
                )
            else:
                seen_room[room_key] = lesson

    return render(
        request,
        "timetable/conflicts.html",
        {
            "conflicts": conflicts,
            "lessons_count": lessons.count(),
        },
    )


# ============================================================
# REQUIREMENT BUILDER
# ============================================================

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404
from .generator_engine import generate_timetable as run_timetable_generator


@login_required
def requirement_builder(request):
    denied = _timetable_permission_redirect(request, "view_lessonrequirement")
    if denied:
        return denied
    classes = TimetableClass.objects.filter(active=True).order_by("name", "stream")
    subjects = TimetableSubject.objects.filter(active=True).order_by("name")
    if is_timetable_admin:
        teachers = TimetableTeacher.objects.filter(
            active=True
        ).order_by("name")
    else:
        teachers = TimetableTeacher.objects.filter(
            pk=staff_teacher.pk,
            active=True,
        )
    rooms = TimetableRoom.objects.filter(active=True).order_by("name")
    days = TimetableDay.objects.filter(active=True).order_by("order")

    selected_class = request.GET.get("class")
    selected_subject = request.GET.get("subject")

    requirements = LessonRequirement.objects.select_related(
        "class_group",
        "subject",
        "teacher",
        "room",
        "preferred_day",
    ).filter(active=True)

    if selected_class:
        requirements = requirements.filter(class_group_id=selected_class)

    if selected_subject:
        requirements = requirements.filter(subject_id=selected_subject)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save":
            class_id = request.POST.get("class_group")
            subject_id = request.POST.get("subject")
            teacher_id = request.POST.get("teacher") or None
            room_id = request.POST.get("room") or None
            lessons = request.POST.get("lessons_per_week") or 1
            duration = request.POST.get("duration_periods") or 1
            requires_double = request.POST.get("requires_double") == "on"
            double_lessons_per_week = request.POST.get("double_lessons_per_week") or 0
            practical = request.POST.get("practical") == "on"
            preferred_day = request.POST.get("preferred_day") or None
            notes = request.POST.get("notes", "").strip()

            if not class_id or not subject_id:
                messages.error(
                    request,
                    "Class and Subject are required."
                )
            else:
                LessonRequirement.objects.create(
                    class_group_id=class_id,
                    subject_id=subject_id,
                    teacher_id=teacher_id,
                    room_id=room_id,
                    lessons_per_week=max(1, int(lessons)),
                    duration_periods=max(1, int(duration)),
                    requires_double=(double_lessons > 0),
                    double_lessons_per_week=min(
                        max(0, int(double_lessons_per_week)),
                        max(1, int(lessons))
                    ),
                    practical=practical,
        preferred_day_id=int(request.POST.get("preferred_day")) if request.POST.get("preferred_day") else None,
                    notes=notes,
                    active=True,
                )

                messages.success(
                    request,
                    "Lesson requirement added successfully."
                )

                return redirect("timetable:requirement_builder")

        elif action == "delete":
            requirement_id = request.POST.get("requirement_id")

            if requirement_id:
                requirement = get_object_or_404(
                    LessonRequirement,
                    pk=requirement_id
                )
                requirement.delete()

                messages.success(
                    request,
                    "Lesson requirement deleted."
                )

            return redirect("timetable:requirement_builder")

    return render(
        request,
        "timetable/requirement_builder.html",
        {
            "classes": classes,
            "subjects": subjects,
            "teachers": teachers,
            "rooms": rooms,
            "days": days,
            "requirements": requirements,
            "selected_class": selected_class,
            "selected_subject": selected_subject,
        },
    )



@login_required
def clear_generated_timetable(request):
    denied = _timetable_admin_redirect(request)
    if denied:
        return denied

    denied = _timetable_permission_redirect(
        request,
        "delete_timetablelesson",
    )

    if denied:
        return denied
    if request.method != "POST":
        return redirect("timetable:workspace")

    term = TimetableTerm.objects.filter(active=True).order_by("-id").first()

    if not term:
        messages.error(request, "No active timetable term found.")
        return redirect("timetable:workspace")

    deleted, _ = TimetableLesson.objects.filter(
        term=term,
        locked=False
    ).delete()

    messages.success(
        request,
        f"{deleted} generated lesson record(s) cleared. Locked lessons were preserved."
    )

    return redirect("timetable:workspace")


# ============================================================
# CONFLICT REPORT
# ============================================================

@login_required
def conflicts(request):
    denied = _timetable_permission_redirect(
        request,
        "view_timetablelesson",
    )
    if denied:
        return denied

    term = TimetableTerm.objects.filter(active=True).order_by("-id").first()

    lessons = TimetableLesson.objects.none()

    if term:
        lessons = TimetableLesson.objects.filter(
            term=term
        ).select_related(
            "class_group",
            "subject",
            "teacher",
            "room",
            "day",
            "period",
        )

    conflicts_found = []

    class_seen = {}
    teacher_seen = {}
    room_seen = {}

    for lesson in lessons:
        duration = max(1, lesson.duration_periods or 1)

        try:
            start_index = list(
                TimetablePeriod.objects.filter(
                    active=True,
                    is_break=False,
                    is_lunch=False
                ).order_by("order")
            ).index(lesson.period)
        except ValueError:
            start_index = 0

        for offset in range(duration):
            period_id = lesson.period_id

            class_key = (
                lesson.class_group_id,
                lesson.day_id,
                period_id
            )

            if class_key in class_seen:
                conflicts_found.append(
                    f"Class clash: {lesson.class_group} on "
                    f"{lesson.day} during {lesson.period}"
                )
            else:
                class_seen[class_key] = lesson.id

            if lesson.teacher_id:
                teacher_key = (
                    lesson.teacher_id,
                    lesson.day_id,
                    period_id
                )

                if teacher_key in teacher_seen:
                    conflicts_found.append(
                        f"Teacher clash: {lesson.teacher} on "
                        f"{lesson.day} during {lesson.period}"
                    )
                else:
                    teacher_seen[teacher_key] = lesson.id

            if lesson.room_id:
                room_key = (
                    lesson.room_id,
                    lesson.day_id,
                    period_id
                )

                if room_key in room_seen:
                    conflicts_found.append(
                        f"Room clash: {lesson.room} on "
                        f"{lesson.day} during {lesson.period}"
                    )
                else:
                    room_seen[room_key] = lesson.id

    return render(
        request,
        "timetable/conflicts.html",
        {
            "term": term,
            "conflicts": conflicts_found,
            "conflict_count": len(conflicts_found),
        }
    )


# ============================================================
# CUSTOM TIMETABLE REQUIREMENTS BUILDER
# ============================================================

def timetable_conflict_engine(term):
    """
    Complete timetable validation engine.

    Checks:
    - Class clashes
    - Teacher clashes
    - Room clashes
    - Teacher availability
    - Requirements not fully generated
    - Invalid lesson durations
    - Lessons placed outside active timetable periods
    """

    conflicts = []

    if not term:
        return conflicts

    lessons = list(
        TimetableLesson.objects
        .filter(term=term)
        .select_related(
            "class_group",
            "subject",
            "teacher",
            "room",
            "day",
            "period",
        )
        .order_by(
            "day__order",
            "period__order",
        )
    )

    # --------------------------------------------------------
    # OCCUPANCY MAPS
    # --------------------------------------------------------

    class_map = {}
    teacher_map = {}
    room_map = {}

    for lesson in lessons:

        key = (
            lesson.day_id,
            lesson.period_id,
        )

        if lesson.class_group_id:
            class_map.setdefault(
                (lesson.class_group_id, *key),
                []
            ).append(lesson)

        if lesson.teacher_id:
            teacher_map.setdefault(
                (lesson.teacher_id, *key),
                []
            ).append(lesson)

        if lesson.room_id:
            room_map.setdefault(
                (lesson.room_id, *key),
                []
            ).append(lesson)

    # --------------------------------------------------------
    # CLASS CLASHES
    # --------------------------------------------------------

    for key, items in class_map.items():

        if len(items) > 1:

            for lesson in items:

                conflicts.append({
                    "type": "Class Clash",
                    "severity": "danger",
                    "class": (
                        lesson.class_group.name
                        if lesson.class_group else "-"
                    ),
                    "subject": (
                        lesson.subject.name
                        if lesson.subject else "-"
                    ),
                    "teacher": (
                        lesson.teacher.name
                        if lesson.teacher else "-"
                    ),
                    "room": (
                        lesson.room.name
                        if lesson.room else "-"
                    ),
                    "day": (
                        lesson.day.name
                        if lesson.day else "-"
                    ),
                    "period": (
                        lesson.period.name
                        if lesson.period else "-"
                    ),
                    "reason": "The same class has more than one lesson in the same period.",
                    "lesson_id": lesson.id,
                })

    # --------------------------------------------------------
    # TEACHER CLASHES
    # --------------------------------------------------------

    for key, items in teacher_map.items():

        if len(items) > 1:

            for lesson in items:

                conflicts.append({
                    "type": "Teacher Clash",
                    "severity": "danger",
                    "class": (
                        lesson.class_group.name
                        if lesson.class_group else "-"
                    ),
                    "subject": (
                        lesson.subject.name
                        if lesson.subject else "-"
                    ),
                    "teacher": (
                        lesson.teacher.name
                        if lesson.teacher else "-"
                    ),
                    "room": (
                        lesson.room.name
                        if lesson.room else "-"
                    ),
                    "day": (
                        lesson.day.name
                        if lesson.day else "-"
                    ),
                    "period": (
                        lesson.period.name
                        if lesson.period else "-"
                    ),
                    "reason": "The same teacher is assigned to multiple lessons in the same period.",
                    "lesson_id": lesson.id,
                })

    # --------------------------------------------------------
    # ROOM CLASHES
    # --------------------------------------------------------

    for key, items in room_map.items():

        if len(items) > 1:

            for lesson in items:

                conflicts.append({
                    "type": "Room Clash",
                    "severity": "danger",
                    "class": (
                        lesson.class_group.name
                        if lesson.class_group else "-"
                    ),
                    "subject": (
                        lesson.subject.name
                        if lesson.subject else "-"
                    ),
                    "teacher": (
                        lesson.teacher.name
                        if lesson.teacher else "-"
                    ),
                    "room": (
                        lesson.room.name
                        if lesson.room else "-"
                    ),
                    "day": (
                        lesson.day.name
                        if lesson.day else "-"
                    ),
                    "period": (
                        lesson.period.name
                        if lesson.period else "-"
                    ),
                    "reason": "The same room is assigned to multiple lessons in the same period.",
                    "lesson_id": lesson.id,
                })

    # --------------------------------------------------------
    # TEACHER AVAILABILITY
    # --------------------------------------------------------

    availability = {}

    for item in TeacherAvailability.objects.select_related(
        "teacher",
        "day",
        "period",
    ):
        availability[
            (
                item.teacher_id,
                item.day_id,
                item.period_id,
            )
        ] = item.available

    for lesson in lessons:

        if not lesson.teacher_id:
            continue

        key = (
            lesson.teacher_id,
            lesson.day_id,
            lesson.period_id,
        )

        if key in availability and not availability[key]:

            conflicts.append({
                "type": "Teacher Unavailable",
                "severity": "warning",
                "class": (
                    lesson.class_group.name
                    if lesson.class_group else "-"
                ),
                "subject": (
                    lesson.subject.name
                    if lesson.subject else "-"
                ),
                "teacher": (
                    lesson.teacher.name
                    if lesson.teacher else "-"
                ),
                "room": (
                    lesson.room.name
                    if lesson.room else "-"
                ),
                "day": (
                    lesson.day.name
                    if lesson.day else "-"
                ),
                "period": (
                    lesson.period.name
                    if lesson.period else "-"
                ),
                "reason": "Teacher availability marks this period as unavailable.",
                "lesson_id": lesson.id,
            })

    # --------------------------------------------------------
    # INVALID DURATION
    # --------------------------------------------------------

    for lesson in lessons:

        duration = int(lesson.duration_periods or 1)

        if duration < 1:

            conflicts.append({
                "type": "Invalid Duration",
                "severity": "warning",
                "class": (
                    lesson.class_group.name
                    if lesson.class_group else "-"
                ),
                "subject": (
                    lesson.subject.name
                    if lesson.subject else "-"
                ),
                "teacher": (
                    lesson.teacher.name
                    if lesson.teacher else "-"
                ),
                "room": (
                    lesson.room.name
                    if lesson.room else "-"
                ),
                "day": (
                    lesson.day.name
                    if lesson.day else "-"
                ),
                "period": (
                    lesson.period.name
                    if lesson.period else "-"
                ),
                "reason": "Lesson has an invalid duration.",
                "lesson_id": lesson.id,
            })

    # --------------------------------------------------------
    # REQUIREMENTS NOT FULLY GENERATED
    # --------------------------------------------------------

    requirements = (
        LessonRequirement.objects
        .filter(active=True)
        .select_related(
            "class_group",
            "subject",
            "teacher",
            "room",
        )
    )

    for requirement in requirements:

        expected = int(requirement.lessons_per_week or 0)

        actual = TimetableLesson.objects.filter(
            term=term,
            class_group_id=requirement.class_group_id,
            subject_id=requirement.subject_id,
        ).count()

        if expected > 0 and actual < expected:

            conflicts.append({
                "type": "Unplaced Requirement",
                "severity": "warning",
                "class": (
                    requirement.class_group.name
                    if requirement.class_group else "-"
                ),
                "subject": (
                    requirement.subject.name
                    if requirement.subject else "-"
                ),
                "teacher": (
                    requirement.teacher.name
                    if requirement.teacher else "-"
                ),
                "room": (
                    requirement.room.name
                    if requirement.room else "-"
                ),
                "day": "-",
                "period": "-",
                "reason": (
                    f"Required {expected} lesson occurrences "
                    f"but only {actual} were generated."
                ),
            })

    return conflicts


@login_required
def timetable_conflicts_page(request):
    denied = _timetable_permission_redirect(
        request,
        "view_timetablelesson",
    )

    if denied:
        return denied

    term = get_selected_timetable_term(request)

    conflicts = timetable_conflict_engine(term)

    danger_count = sum(
        1 for item in conflicts
        if item.get("severity") == "danger"
    )

    warning_count = sum(
        1 for item in conflicts
        if item.get("severity") == "warning"
    )

    lessons_count = (
        TimetableLesson.objects.filter(term=term).count()
        if term else 0
    )

    locked_count = (
        TimetableLesson.objects.filter(
            term=term,
            locked=True,
        ).count()
        if term else 0
    )

    return render(
        request,
        "timetable/smart_conflicts.html",
        {
            "term": term,
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
            "danger_count": danger_count,
            "warning_count": warning_count,
            "lessons_count": lessons_count,
            "locked_count": locked_count,
        },
    )


@login_required
def generation_control(request):
    denied = _timetable_admin_redirect(request)
    if denied:
        return denied

    denied = _timetable_permission_redirect(
        request,
        "view_timetablelesson",
    )

    if denied:
        return denied
    from .complete_timetable_system import (
        check_timetable,
        current_draft,
        published_version,
    )

    term = get_selected_timetable_term(
        request
    )

    draft_version = (
        current_draft(term)
        if term
        else None
    )

    global_published = published_version()

    published_for_term = None

    if (
        global_published
        and term
        and global_published.term_id == term.id
    ):
        published_for_term = global_published

    active_version = (
        draft_version
        or published_for_term
    )

    total_lessons = 0
    locked_lessons = 0
    requirement_count = 0
    conflict_count = 0
    conflicts_data = []

    if term:

        if active_version:

            total_lessons = (
                TimetableLesson.objects.filter(
                    term=term,
                    version=active_version,
                    is_active=True,
                ).count()
            )

        else:

            total_lessons = (
                TimetableLesson.objects.filter(
                    term=term,
                    is_active=True,
                ).count()
            )

        locked_lessons = (
            TimetableLesson.objects.filter(
                term=term,
                locked=True,
                is_active=True,
            ).count()
        )

        requirement_count = (
            LessonRequirement.objects.filter(
                active=True
            ).count()
        )

        conflict_result = check_timetable(
            term
        )

        conflict_count = len(
            conflict_result.get(
                "conflicts",
                []
            )
        )

        conflicts_data = (
            conflict_result.get(
                "conflicts",
                []
            )
        )

    generation_result = request.session.get(
        "timetable_generation_result"
    )

    return render(
        request,
        "timetable/generation_control.html",
        {
            "term": term,
            "total_lessons": total_lessons,
            "locked_lessons": locked_lessons,
            "requirement_count": requirement_count,
            "conflict_count": conflict_count,
            "conflicts": conflicts_data,
            "generation_result": generation_result,
            "draft_version": draft_version,
            "published_version": published_for_term,
            "active_version": active_version,
        },
    )


@login_required
def timetable_requirement_edit(request, pk):
    if request.method == "POST":
        denied = _timetable_permission_redirect(
            request,
            "change_lessonrequirement",
        )
    else:
        denied = _timetable_permission_redirect(
            request,
            "view_lessonrequirement",
        )

    if denied:
        return denied
    is_timetable_admin = _timetable_admin_allowed(request.user)
    staff_teacher = None

    if not is_timetable_admin:
        from .staff_utils import get_staff_teacher

        staff_teacher = get_staff_teacher(request.user)

        if not staff_teacher:
            messages.error(
                request,
                "Your staff account is not linked to an active timetable teacher."
            )
            return redirect("accounts:staff_dashboard")

    if is_timetable_admin:
        requirement = get_object_or_404(
            LessonRequirement,
            pk=pk,
        )
    else:
        requirement = get_object_or_404(
            LessonRequirement,
            pk=pk,
            teacher=staff_teacher,
        )

    classes = TimetableClass.objects.filter(active=True).order_by("name", "stream")
    subjects = TimetableSubject.objects.filter(active=True).order_by("name")
    if is_timetable_admin:
        teachers = TimetableTeacher.objects.filter(
            active=True
        ).order_by("name")
    else:
        teachers = TimetableTeacher.objects.filter(
            pk=staff_teacher.pk,
            active=True,
        )
    rooms = TimetableRoom.objects.filter(active=True).order_by("name")
    days = TimetableDay.objects.filter(active=True).order_by("order")

    if request.method == "POST":
        class_id = request.POST.get("class_id")
        subject_id = request.POST.get("subject_id")
        if is_timetable_admin:
            teacher_id = request.POST.get("teacher_id") or None
        else:
            teacher_id = staff_teacher.pk
        room_id = request.POST.get("room_id") or None

        single_lessons = int(request.POST.get("single_lessons") or 0)
        double_lessons = int(request.POST.get("double_lessons") or 0)

        duration_periods = int(request.POST.get("duration_periods") or 1)
        priority = int(request.POST.get("priority") or 0)
        preferred_day_id = request.POST.get("preferred_day_id") or None
        practical = bool(request.POST.get("practical"))
        notes = request.POST.get("notes", "").strip()

        if not class_id or not subject_id:
            messages.error(request, "Please select both Class and Subject.")

        elif single_lessons < 0 or double_lessons < 0:
            messages.error(request, "Lessons cannot be negative.")

        elif single_lessons == 0 and double_lessons == 0:
            messages.error(request, "Enter at least one single or double lesson.")

        else:
            requirement.class_group_id = class_id
            requirement.subject_id = subject_id
            requirement.teacher_id = teacher_id
            requirement.room_id = room_id

            requirement.lessons_per_week = (
                single_lessons + double_lessons
            )

            requirement.double_lessons_per_week = double_lessons
            requirement.requires_double = double_lessons > 0
            requirement.duration_periods = max(1, duration_periods)
            requirement.priority = priority
            requirement.preferred_day_id = preferred_day_id
            requirement.practical = practical
            requirement.notes = notes

            requirement.save()

            messages.success(
                request,
                "Timetable requirement updated successfully."
            )

            return redirect("timetable:requirements")

    return render(
        request,
        "timetable/requirement_edit.html",
        {
            "requirement": requirement,
            "classes": classes,
            "subjects": subjects,
            "teachers": teachers,
            "rooms": rooms,
            "days": days,
            "single_lessons": max(
                0,
                int(requirement.lessons_per_week or 0)
                - int(requirement.double_lessons_per_week or 0)
            ),
            "double_lessons": int(
                requirement.double_lessons_per_week or 0
            ),
        },
    )


@login_required
def timetable_requirement_delete(request, pk):
    denied = _timetable_permission_redirect(
        request,
        "delete_lessonrequirement",
    )
    if denied:
        return denied
    is_timetable_admin = _timetable_admin_allowed(request.user)
    staff_teacher = None

    if not is_timetable_admin:
        from .staff_utils import get_staff_teacher

        staff_teacher = get_staff_teacher(request.user)

        if not staff_teacher:
            messages.error(
                request,
                "Your staff account is not linked to an active timetable teacher."
            )
            return redirect("accounts:staff_dashboard")

    if is_timetable_admin:
        requirement = get_object_or_404(
            LessonRequirement,
            pk=pk,
        )
    else:
        requirement = get_object_or_404(
            LessonRequirement,
            pk=pk,
            teacher=staff_teacher,
        )

    if request.method == "POST":
        requirement.delete()
        messages.success(
            request,
            "Timetable requirement deleted successfully."
        )

    return redirect("timetable:requirements")


@login_required
def timetable_requirement_toggle(request, pk):
    denied = _timetable_permission_redirect(
        request,
        "change_lessonrequirement",
    )
    if denied:
        return denied
    is_timetable_admin = _timetable_admin_allowed(request.user)
    staff_teacher = None

    if not is_timetable_admin:
        from .staff_utils import get_staff_teacher

        staff_teacher = get_staff_teacher(request.user)

        if not staff_teacher:
            messages.error(
                request,
                "Your staff account is not linked to an active timetable teacher."
            )
            return redirect("accounts:staff_dashboard")

    if is_timetable_admin:
        requirement = get_object_or_404(
            LessonRequirement,
            pk=pk,
        )
    else:
        requirement = get_object_or_404(
            LessonRequirement,
            pk=pk,
            teacher=staff_teacher,
        )

    if request.method == "POST":
        requirement.active = not requirement.active
        requirement.save(update_fields=["active"])

        status = "activated" if requirement.active else "deactivated"

        messages.success(
            request,
            f"Requirement {status} successfully."
        )

    return redirect("timetable:requirements")


@login_required
def timetable_requirements_builder(request):
    if request.method == "POST":
        denied = _timetable_permission_redirect(
            request,
            "add_lessonrequirement",
        )
    else:
        denied = _timetable_permission_redirect(
            request,
            "view_lessonrequirement",
        )

    if denied:
        return denied
    selected_term = get_selected_timetable_term(request)
    is_timetable_admin = _timetable_admin_allowed(request.user)
    staff_teacher = None

    if not is_timetable_admin:
        from .staff_utils import get_staff_teacher

        staff_teacher = get_staff_teacher(request.user)

        if not staff_teacher:
            messages.error(
                request,
                "Your staff account is not linked to an active timetable teacher."
            )
            return redirect("accounts:staff_dashboard")

    classes = TimetableClass.objects.filter(active=True).order_by("name", "stream")
    subjects = TimetableSubject.objects.filter(active=True).order_by("name")
    if is_timetable_admin:
        teachers = TimetableTeacher.objects.filter(
            active=True
        ).order_by("name")
    else:
        teachers = TimetableTeacher.objects.filter(
            pk=staff_teacher.pk,
            active=True,
        )
    rooms = TimetableRoom.objects.filter(active=True).order_by("name")
    days = TimetableDay.objects.filter(active=True).order_by("order")

    if request.method == "POST":

        class_id = request.POST.get("class_id")
        subject_id = request.POST.get("subject_id")
        if is_timetable_admin:
            teacher_id = request.POST.get("teacher_id") or None
        else:
            teacher_id = staff_teacher.pk
        room_id = request.POST.get("room_id") or None

        single_lessons = int(request.POST.get("single_lessons") or 0)
        double_lessons = int(request.POST.get("double_lessons") or 0)

        duration_periods = int(
            request.POST.get("duration_periods") or 1
        )

        priority = int(request.POST.get("priority") or 0)
        preferred_day_id = request.POST.get("preferred_day_id") or None
        practical = bool(request.POST.get("practical"))
        notes = request.POST.get("notes", "").strip()

        # Type is a UI convenience. Practical is stored in the model.
        requirement_type = request.POST.get("requirement_type", "normal")

        if requirement_type == "practical":
            practical = True

        if not class_id or not subject_id:
            messages.error(
                request,
                "Please select both a Class and Subject."
            )

        elif single_lessons < 0 or double_lessons < 0:
            messages.error(
                request,
                "Single and double lessons cannot be negative."
            )

        elif single_lessons == 0 and double_lessons == 0:
            messages.error(
                request,
                "Enter at least one single or double lesson."
            )

        else:
            total_lessons = single_lessons + double_lessons

            if double_lessons > total_lessons:
                messages.error(
                    request,
                    "Double lessons cannot exceed total lessons."
                )
            else:
                requirement = LessonRequirement.objects.create(
                    class_group_id=class_id,
                    subject_id=subject_id,
                    teacher_id=teacher_id,
                    room_id=room_id,
                    lessons_per_week=total_lessons,
                    duration_periods=max(1, duration_periods),
                    requires_double=(double_lessons > 0),
                    double_lessons_per_week=double_lessons,
                    practical=practical,
        preferred_day_id=int(request.POST.get("preferred_day")) if request.POST.get("preferred_day") else None,
                    notes=notes,
                    priority=priority,
                    active=True,
                )

                messages.success(
                    request,
                    (
                        f"Requirement saved successfully: "
                        f"{single_lessons} single + "
                        f"{double_lessons} double lessons."
                    )
                )

                return redirect(
                    "timetable:requirements"
                )

    requirement_qs = LessonRequirement.objects

    if not is_timetable_admin:
        requirement_qs = requirement_qs.filter(
            teacher=staff_teacher
        )
    requirements = list(
        requirement_qs
        .select_related(
            "class_group",
            "subject",
            "teacher",
            "room",
            "preferred_day",
        )
        .order_by(
            "-priority",
            "class_group__name",
            "subject__name",
        )
    )

    for requirement in requirements:
        requirement.single_lessons = max(
            0,
            int(requirement.lessons_per_week or 0)
            - int(requirement.double_lessons_per_week or 0)
        )

    return render(
        request,
        "timetable/requirements_builder.html",
        {
            "term": selected_term,
            "classes": classes,
            "subjects": subjects,
            "teachers": teachers,
            "rooms": rooms,
            "days": days,
            "requirements": requirements,
        },
    )

def timetable_workspace(request):
    import csv
    from django.http import HttpResponse

    term = (
        TimetableTerm.objects
        .filter(active=True)
        .order_by("-id")
        .first()
    )

    days = list(
        TimetableDay.objects
        .filter(active=True)
        .order_by("order")
    )

    periods = list(
        TimetablePeriod.objects
        .filter(
            active=True,
            is_break=False,
            is_lunch=False,
            is_activity=False,
        )
        .order_by("order")
    )

    classes = list(
        TimetableClass.objects
        .filter(active=True)
        .order_by("name", "stream")
    )

    teachers = list(
        TimetableTeacher.objects
        .filter(active=True)
        .order_by("name")
    )

    rooms = list(
        TimetableRoom.objects
        .filter(active=True)
        .order_by("name")
    )

    selected_view = request.GET.get("view", "class")

    if selected_view not in ["class", "teacher", "room"]:
        selected_view = "class"

    selected_class = request.GET.get("class", "")
    selected_teacher = request.GET.get("teacher", "")
    selected_room = request.GET.get("room", "")

    lessons = []

    if term:
        qs = (
            TimetableLesson.objects
            .filter(term=term)
            .select_related(
                "class_group",
                "subject",
                "teacher",
                "room",
                "day",
                "period",
            )
            .order_by(
                "day__order",
                "period__order",
            )
        )

        if selected_class:
            qs = qs.filter(
                class_group_id=selected_class
            )

        if selected_teacher:
            qs = qs.filter(
                teacher_id=selected_teacher
            )

        if selected_room:
            qs = qs.filter(
                room_id=selected_room
            )

        lessons = list(qs)

    # ---------------------------------------------------------
    # Build grid.
    #
    # A lesson with duration 2/3/4 is shown across consecutive
    # configured periods.
    # ---------------------------------------------------------

    period_index = {
        p.id: index
        for index, p in enumerate(periods)
    }

    grid = {}

    for lesson in lessons:
        start = period_index.get(lesson.period_id)

        if start is None:
            continue

        for offset in range(
            max(1, lesson.duration_periods)
        ):
            position = start + offset

            if position >= len(periods):
                continue

            period = periods[position]

            grid[
                (lesson.day_id, period.id)
            ] = lesson

    # ---------------------------------------------------------
    # CSV EXPORT
    # ---------------------------------------------------------

    if request.GET.get("export") == "csv":

        response = HttpResponse(
            content_type="text/csv"
        )

        response[
            "Content-Disposition"
        ] = (
            'attachment; filename="timetable.csv"'
        )

        writer = csv.writer(response)

        writer.writerow([
            "Day",
            "Period",
            "Start",
            "End",
            "Class",
            "Subject",
            "Teacher",
            "Room",
            "Duration",
            "Locked",
        ])

        for lesson in lessons:

            writer.writerow([
                lesson.day.name,
                lesson.period.name,
                lesson.period.start_time,
                lesson.period.end_time,
                str(lesson.class_group),
                str(lesson.subject),
                str(lesson.teacher)
                if lesson.teacher else "",
                str(lesson.room)
                if lesson.room else "",
                lesson.duration_periods,
                "Yes" if lesson.locked else "No",
            ])

        return response

    context = {
        "term": term,
        "days": days,
        "periods": periods,
        "classes": classes,
        "teachers": teachers,
        "rooms": rooms,
        "lessons": lessons,
        "grid": grid,
        "selected_view": selected_view,
        "selected_class": selected_class,
        "selected_teacher": selected_teacher,
        "selected_room": selected_room,
    }

    return render(
        request,
        "timetable/workspace.html",
        context,
    )


@login_required
def timetable_lesson_edit(request, pk):
    denied = _timetable_permission_redirect(request, "change_timetablelesson")
    if denied:
        return denied
    from django.contrib import messages
    from .models import (
        TimetableLesson,
        TimetableDay,
        TimetablePeriod,
        TimetableTeacher,
        TimetableRoom,
    )

    lesson = TimetableLesson.objects.select_related(
        "term",
        "class_group",
        "subject",
        "teacher",
        "room",
        "day",
        "period",
    ).filter(pk=pk).first()

    if not lesson:
        messages.error(request, "Timetable lesson not found.")
        return redirect("timetable:workspace")

    if request.method == "POST":
        day_id = request.POST.get("day")
        period_id = request.POST.get("period")
        teacher_id = request.POST.get("teacher")
        room_id = request.POST.get("room")
        notes = request.POST.get("notes", "").strip()

        day = TimetableDay.objects.filter(
            id=day_id,
            active=True
        ).first()

        period = TimetablePeriod.objects.filter(
            id=period_id,
            active=True
        ).first()

        teacher = TimetableTeacher.objects.filter(
            id=teacher_id,
            active=True
        ).first() if teacher_id else None

        room = TimetableRoom.objects.filter(
            id=room_id,
            active=True
        ).first() if room_id else None

        if not day or not period:
            messages.error(request, "Please select a valid day and period.")
            return redirect("timetable:timetable_lesson_edit", pk=lesson.pk)

        lesson.day = day
        lesson.period = period
        lesson.teacher = teacher
        lesson.room = room
        lesson.notes = notes
        lesson.save()

        messages.success(request, "Timetable lesson updated successfully.")
        return redirect("timetable:workspace")

    return render(
        request,
        "timetable/lesson_edit.html",
        {
            "lesson": lesson,
            "days": TimetableDay.objects.filter(active=True).order_by("order"),
            "periods": TimetablePeriod.objects.filter(
                active=True,
                is_break=False,
                is_lunch=False,
                is_activity=False,
            ).order_by("order"),
            "teachers": TimetableTeacher.objects.filter(
                active=True
            ).order_by("name"),
            "rooms": TimetableRoom.objects.filter(
                active=True
            ).order_by("name"),
        },
    )


@login_required
def timetable_lesson_lock(request, pk):
    denied = _timetable_permission_redirect(request, "change_timetablelesson")
    if denied:
        return denied
    from django.contrib import messages
    from .models import TimetableLesson

    if request.method != "POST":
        return redirect("timetable:workspace")

    lesson = TimetableLesson.objects.filter(pk=pk).first()

    if not lesson:
        messages.error(request, "Timetable lesson not found.")
        return redirect("timetable:workspace")

    lesson.locked = not lesson.locked
    lesson.save(update_fields=["locked"])

    if lesson.locked:
        messages.success(request, "Lesson locked. Automatic generation will preserve it.")
    else:
        messages.success(request, "Lesson unlocked.")

    return redirect("timetable:workspace")


@login_required
def timetable_lesson_delete(request, pk):
    denied = _timetable_permission_redirect(request, "delete_timetablelesson")
    if denied:
        return denied
    from django.contrib import messages
    from .models import TimetableLesson

    lesson = TimetableLesson.objects.filter(pk=pk).first()

    if not lesson:
        messages.error(request, "Timetable lesson not found.")
        return redirect("timetable:workspace")

    if lesson.locked:
        messages.error(
            request,
            "This lesson is locked. Unlock it before deleting."
        )
        return redirect("timetable:workspace")

    if request.method == "POST":
        lesson.delete()
        messages.success(request, "Timetable lesson deleted.")
        return redirect("timetable:workspace")

    return render(
        request,
        "timetable/lesson_delete.html",
        {"lesson": lesson},
    )

# ===== TIMETABLE WIZARD START =====

TIMETABLE_WIZARD_STEPS = [
    {
        "number": 1,
        "title": "Academic Year & Term",
        "description": "Select or create the academic year and term for the timetable.",
        "route": "timetable:crud_list",
        "argument": "terms",
    },
    {
        "number": 2,
        "title": "School Days",
        "description": "Set the working school days used by the timetable.",
        "route": "timetable:crud_list",
        "argument": "days",
    },
    {
        "number": 3,
        "title": "Periods & Breaks",
        "description": "Set lesson periods, breaks, lunch and activities.",
        "route": "timetable:crud_list",
        "argument": "periods",
    },
    {
        "number": 4,
        "title": "Classes",
        "description": "Create and manage classes and streams.",
        "route": "timetable:crud_list",
        "argument": "classes",
    },
    {
        "number": 5,
        "title": "Subjects",
        "description": "Create and manage timetable subjects.",
        "route": "timetable:crud_list",
        "argument": "subjects",
    },
    {
        "number": 6,
        "title": "Teachers",
        "description": "Create and manage teachers and their subjects.",
        "route": "timetable:crud_list",
        "argument": "teachers",
    },
    {
        "number": 7,
        "title": "Rooms",
        "description": "Create and manage classrooms, laboratories and other rooms.",
        "route": "timetable:crud_list",
        "argument": "rooms",
    },
    {
        "number": 8,
        "title": "Teacher Availability",
        "description": "Set teacher availability for days and periods.",
        "route": "timetable:availability",
        "argument": None,
    },
    {
        "number": 9,
        "title": "Lesson Requirements",
        "description": "Define lessons per week, doubles, duration, teachers, rooms and preferences.",
        "route": "timetable:requirement_builder",
        "argument": None,
    },
    {
        "number": 10,
        "title": "Review Requirements",
        "description": "Review, edit, activate or delete timetable requirements.",
        "route": "timetable:requirements",
        "argument": None,
    },
    {
        "number": 11,
        "title": "Generate Timetable",
        "description": "Generate or regenerate the timetable while preserving locked lessons.",
        "route": "timetable:generation_control",
        "argument": None,
    },
    {
        "number": 12,
        "title": "Conflict Check",
        "description": "Check the generated timetable for clashes and unplaced requirements.",
        "route": "timetable:smart_conflicts",
        "argument": None,
    },
    {
        "number": 13,
        "title": "Timetable Workspace",
        "description": "View and manage the complete master timetable.",
        "route": "timetable:workspace",
        "argument": None,
    },
    {
        "number": 14,
        "title": "Print / Export",
        "description": "Finish the timetable and access the final timetable for printing or export.",
        "route": "timetable:workspace",
        "argument": None,
    },
]



def timetable_teacher_page(request):
    if request.method == "POST":
        action = request.POST.get("wizard_action", "").strip()

        if action == "delete_lesson":
            permission_codename = "delete_lessonrequirement"

        elif action == "save_lesson":
            requirement_id = request.POST.get("requirement_id")

            if requirement_id and requirement_id.isdigit():
                permission_codename = "change_lessonrequirement"
            else:
                permission_codename = "add_lessonrequirement"

        elif action == "bulk_save_lessons":
            permission_codename = "add_lessonrequirement"

        else:
            permission_codename = "view_lessonrequirement"

        denied = _timetable_permission_redirect(
            request,
            permission_codename,
        )

        if denied:
            return denied

    else:
        denied = _timetable_permission_redirect(
            request,
            "view_lessonrequirement",
        )

        if denied:
            return denied
    # Resolve the teacher scope.
    #
    # ADMIN/SUPERUSER:
    #   May select and manage any active timetable teacher.
    #
    # STAFF:
    #   Must use the canonical TimetableTeacher linked through
    #   the authenticated user's HR Employee record.
    from .staff_utils import get_staff_teacher

    is_timetable_admin = request.user.is_superuser

    if not is_timetable_admin:
        try:
            profile = request.user.profile
            is_timetable_admin = (
                getattr(profile, "role", "") == "ADMIN"
            )
        except Exception:
            is_timetable_admin = False

    teacher_id = request.GET.get("teacher")
    selected_teacher = None

    if is_timetable_admin:
        if teacher_id and str(teacher_id).isdigit():
            selected_teacher = TimetableTeacher.objects.filter(
                pk=int(teacher_id),
                active=True
            ).first()
    else:
        selected_teacher = get_staff_teacher(request.user)

        if not selected_teacher:
            messages.error(
                request,
                "Your staff account is not linked to an active timetable teacher."
            )
            return redirect("accounts:staff_dashboard")

        # Ignore any teacher ID supplied by the staff user.
        teacher_id = str(selected_teacher.pk)

    if request.method == "POST":
        action = request.POST.get("wizard_action", "").strip()

        if action == "delete_lesson":
            requirement_id = request.POST.get("requirement_id")

            if requirement_id and requirement_id.isdigit():
                requirement = LessonRequirement.objects.filter(
                    pk=int(requirement_id),
                    teacher=selected_teacher,
                    active=True
                ).first()

                if requirement:
                    requirement.delete()
                    messages.success(
                        request,
                        "Subject assignment deleted successfully."
                    )
            return redirect(
                reverse("timetable:teacher_page")
                + "?teacher="
                + str(teacher_id)
            )

        if action == "bulk_save_lessons":

            if is_timetable_admin:
                teacher_pk = request.POST.get("teacher_id")

                if not teacher_pk or not teacher_pk.isdigit():
                    messages.error(
                        request,
                        "Please select a valid teacher."
                    )
                    return redirect(
                        reverse("timetable:teacher_page")
                    )

                teacher = TimetableTeacher.objects.filter(
                    pk=int(teacher_pk),
                    active=True
                ).first()

                if not teacher:
                    messages.error(
                        request,
                        "Teacher not found."
                    )
                    return redirect(
                        reverse("timetable:teacher_page")
                    )
            else:
                # Staff cannot choose another teacher through POST.
                teacher = selected_teacher
                teacher_pk = str(teacher.pk)

            row_count_value = request.POST.get("row_count", "0")

            try:
                row_count = int(row_count_value)
            except (TypeError, ValueError):
                row_count = 0

            added = 0
            skipped = 0
            invalid = 0

            for i in range(row_count):

                subject_value = request.POST.get(f"subject_{i}")
                class_value = request.POST.get(f"class_group_{i}")
                lessons_value = request.POST.get(f"lessons_{i}", "1")
                double_value = request.POST.get(f"double_lessons_{i}", "0")
                duration_value = request.POST.get(f"duration_periods_{i}", "1")
                preferred_day_value = request.POST.get(f"preferred_day_{i}")
                room_value = request.POST.get(f"room_{i}")
                priority_value = request.POST.get(f"priority_{i}", "0")
                practical_value = request.POST.get(f"practical_{i}", "0")
                notes_value = request.POST.get(f"notes_{i}", "")

                if not subject_value and not class_value:
                    continue

                try:
                    subject_pk = int(subject_value)
                    class_pk = int(class_value)

                    lessons = max(1, int(lessons_value or 1))
                    double_lessons = max(0, int(double_value or 0))
                    duration_periods = max(1, int(duration_value or 1))
                    priority = int(priority_value or 0)

                except (TypeError, ValueError):
                    invalid += 1
                    continue

                subject = TimetableSubject.objects.filter(
                    pk=subject_pk,
                    active=True
                ).first()

                class_group = TimetableClass.objects.filter(
                    pk=class_pk,
                    active=True
                ).first()

                if not subject or not class_group:
                    invalid += 1
                    continue

                # Prevent duplicate teacher + subject + class.
                if LessonRequirement.objects.filter(
                    teacher=teacher,
                    subject=subject,
                    class_group=class_group,
                    active=True
                ).exists():

                    skipped += 1
                    continue

                room = None

                if room_value and room_value.isdigit():
                    room = TimetableRoom.objects.filter(
                        pk=int(room_value),
                        active=True
                    ).first()

                preferred_day = None

                if preferred_day_value and preferred_day_value.isdigit():
                    preferred_day = TimetableDay.objects.filter(
                        pk=int(preferred_day_value),
                        active=True
                    ).first()

                LessonRequirement.objects.create(
                    teacher=teacher,
                    subject=subject,
                    class_group=class_group,
                    room=room,
                    preferred_day=preferred_day,
                    lessons_per_week=lessons,
                    double_lessons_per_week=double_lessons,
                    requires_double=double_lessons > 0,
                    duration_periods=duration_periods,
                    priority=priority,
                    practical=str(
                        practical_value
                    ).lower() in ("1", "true", "yes", "on"),
                    notes=notes_value,
                    active=True,
                )

                added += 1

            if added:
                messages.success(
                    request,
                    f"{added} lesson assignment(s) added successfully."
                )

            if skipped:
                messages.warning(
                    request,
                    f"{skipped} assignment(s) skipped because the subject "
                    f"is already assigned to this teacher for that class."
                )

            if invalid:
                messages.error(
                    request,
                    f"{invalid} invalid assignment row(s) were skipped."
                )

            return redirect(
                reverse("timetable:teacher_page")
                + "?teacher="
                + str(teacher_pk)
            )

        if action == "save_lesson":

            requirement_id = request.POST.get("requirement_id")
            subject_value = request.POST.get("subject")
            class_value = request.POST.get("class_group")
            room_value = request.POST.get("room")
            preferred_day_value = request.POST.get("preferred_day")
            single_value = request.POST.get("single_lessons", "0")
            double_value = request.POST.get("double_lessons", "0")
            duration_value = request.POST.get("duration_periods", "1")
            priority_value = request.POST.get("priority", "0")
            practical_value = request.POST.get("practical", "0")
            notes_value = request.POST.get("notes", "")

            try:
                if is_timetable_admin:
                    teacher_pk = int(teacher_id)
                else:
                    # Staff always save against their canonical teacher.
                    teacher_pk = int(selected_teacher.pk)

                subject_pk = int(subject_value)
                class_pk = int(class_value)

                single_lessons = max(0, int(single_value or 0))
                double_lessons = max(0, int(double_value or 0))
                duration_periods = max(1, int(duration_value or 1))
                priority = int(priority_value or 0)

            except (TypeError, ValueError):

                messages.error(
                    request,
                    "Please enter valid assignment details."
                )

                return redirect(
                    reverse("timetable:teacher_page")
                    + "?teacher="
                    + str(teacher_id)
                )

            if is_timetable_admin:
                teacher = TimetableTeacher.objects.filter(
                    pk=teacher_pk,
                    active=True
                ).first()
            else:
                teacher = selected_teacher

            subject = TimetableSubject.objects.filter(
                pk=subject_pk,
                active=True
            ).first()

            class_group = TimetableClass.objects.filter(
                pk=class_pk,
                active=True
            ).first()

            room = None
            if room_value and room_value.isdigit():
                room = TimetableRoom.objects.filter(
                    pk=int(room_value),
                    active=True
                ).first()

            preferred_day = None
            if preferred_day_value and preferred_day_value.isdigit():
                preferred_day = TimetableDay.objects.filter(
                    pk=int(preferred_day_value),
                    active=True
                ).first()

            if not teacher or not subject or not class_group:

                messages.error(
                    request,
                    "Teacher, subject and class are required."
                )

                return redirect(
                    reverse("timetable:teacher_page")
                    + "?teacher="
                    + str(teacher_id)
                )

            total_lessons = single_lessons + double_lessons

            # Prevent duplicate teacher + subject + class assignments.
            # A teacher can have a subject in a class only once.
            duplicate_qs = LessonRequirement.objects.filter(
                teacher=teacher,
                subject=subject,
                class_group=class_group,
                active=True,
            )

            # When editing, exclude the assignment currently being edited.
            if requirement_id and requirement_id.isdigit():
                duplicate_qs = duplicate_qs.exclude(
                    pk=int(requirement_id)
                )

            if duplicate_qs.exists():
                messages.error(
                    request,
                    "This subject is already assigned to this teacher for this class."
                )

                return redirect(
                    reverse("timetable:teacher_page")
                    + "?teacher="
                    + str(teacher_pk)
                )

            requirement = None

            if requirement_id and requirement_id.isdigit():
                requirement = LessonRequirement.objects.filter(
                    pk=int(requirement_id),
                    teacher=teacher,
                    active=True
                ).first()
            if requirement:

                requirement.teacher = teacher
                requirement.subject = subject
                requirement.class_group = class_group
                requirement.room = room
                requirement.preferred_day = preferred_day
                requirement.lessons_per_week = total_lessons
                requirement.double_lessons_per_week = double_lessons
                requirement.requires_double = double_lessons > 0
                requirement.duration_periods = duration_periods
                requirement.priority = priority
                requirement.practical = str(
                    practical_value
                ).lower() in ("1", "true", "yes", "on")
                requirement.notes = notes_value
                requirement.active = True
                requirement.save()

                messages.success(
                    request,
                    "Subject assignment updated successfully."
                )

            else:

                LessonRequirement.objects.create(
                    teacher=teacher,
                    subject=subject,
                    class_group=class_group,
                    room=room,
                    preferred_day=preferred_day,
                    lessons_per_week=total_lessons,
                    double_lessons_per_week=double_lessons,
                    requires_double=double_lessons > 0,
                    duration_periods=duration_periods,
                    priority=priority,
                    practical=str(
                        practical_value
                    ).lower() in ("1", "true", "yes", "on"),
                    notes=notes_value,
                    active=True,
                )

                messages.success(
                    request,
                    "Subject assignment added successfully."
                )

            return redirect(
                reverse("timetable:teacher_page")
                + "?teacher="
                + str(teacher_pk)
            )

    teacher_requirements = LessonRequirement.objects.filter(
        active=True
    ).select_related(
        "teacher",
        "subject",
        "class_group",
        "room",
        "preferred_day",
    )

    if selected_teacher:
        teacher_requirements = teacher_requirements.filter(
            teacher=selected_teacher
        )

    teacher_requirements = teacher_requirements.order_by(
        "subject__name",
        "class_group__name",
        "id",
    )

    editing_requirement = None

    edit_id = request.GET.get("edit")

    if edit_id and str(edit_id).isdigit():
        editing_requirement = LessonRequirement.objects.filter(
            pk=int(edit_id),
            active=True
        )

        if not is_timetable_admin:
            editing_requirement = editing_requirement.filter(
                teacher=selected_teacher
            )

        editing_requirement = editing_requirement.select_related(
            "teacher",
            "subject",
            "class_group",
            "room",
            "preferred_day",
        ).first()

    context = {
        "teachers": (
            TimetableTeacher.objects.filter(
                active=True
            ).order_by("name")
            if is_timetable_admin
            else TimetableTeacher.objects.filter(
                pk=selected_teacher.pk,
                active=True
            )
        ),

        "subjects": TimetableSubject.objects.filter(
            active=True
        ).order_by("name"),

        "classes": TimetableClass.objects.filter(
            active=True
        ).order_by("name"),

        "rooms": TimetableRoom.objects.filter(
            active=True
        ).order_by("name"),

        "days": TimetableDay.objects.filter(
            active=True
        ).order_by("id"),

        "selected_teacher": selected_teacher,

        "teacher_requirements": teacher_requirements,

        "editing_requirement": editing_requirement,
    }

    return render(
        request,
        "timetable/teacher_assignments.html",
        context
    )


@login_required
def timetable_subject_page(request):
    from .staff_utils import get_staff_teacher

    # ---------------------------------------------------------
    # ADMIN / STAFF SCOPE
    # ---------------------------------------------------------
    is_timetable_admin = request.user.is_superuser

    if not is_timetable_admin:
        try:
            profile = request.user.profile
            is_timetable_admin = (
                getattr(profile, "role", "") == "ADMIN"
            )
        except Exception:
            is_timetable_admin = False

    selected_teacher = None

    if not is_timetable_admin:
        selected_teacher = get_staff_teacher(request.user)

        if not selected_teacher:
            messages.error(
                request,
                "Your staff account is not linked to an active timetable teacher."
            )
            return redirect("accounts:staff_dashboard")

    # ---------------------------------------------------------
    # PERMISSION
    # ---------------------------------------------------------
    if request.method == "POST":
        denied = _timetable_permission_redirect(
            request,
            "change_lessonrequirement",
        )
    else:
        denied = _timetable_permission_redirect(
            request,
            "view_lessonrequirement",
        )

    if denied:
        return denied

    subject_id = request.GET.get("subject")
    selected_subject = None

    if subject_id and str(subject_id).isdigit():
        selected_subject = TimetableSubject.objects.filter(
            pk=int(subject_id),
            active=True,
        ).first()

    # ---------------------------------------------------------
    # POST ACTIONS
    # ---------------------------------------------------------
    if request.method == "POST":

        action = request.POST.get("action", "").strip()

        if action == "reassign_teacher":

            # Staff are not allowed to reassign lessons.
            if not is_timetable_admin:
                messages.error(
                    request,
                    "Only timetable administrators can reassign teachers."
                )
                return redirect(
                    reverse("timetable:subject_page")
                    + "?subject="
                    + str(subject_id)
                )

            requirement_id = request.POST.get("requirement_id")
            new_teacher_id = request.POST.get("new_teacher")

            if (
                requirement_id
                and requirement_id.isdigit()
                and new_teacher_id
                and new_teacher_id.isdigit()
            ):

                requirement = LessonRequirement.objects.filter(
                    pk=int(requirement_id),
                    active=True,
                ).first()

                if (
                    requirement is None
                    or selected_subject is None
                    or requirement.subject_id != selected_subject.id
                ):
                    messages.error(
                        request,
                        "This lesson assignment does not belong to the selected subject."
                    )
                    return redirect(
                        reverse("timetable:subject_page")
                        + "?subject="
                        + str(subject_id)
                    )

                new_teacher = TimetableTeacher.objects.filter(
                    pk=int(new_teacher_id),
                    active=True,
                ).first()

                if not requirement or not new_teacher:
                    messages.error(
                        request,
                        "The assignment or teacher could not be found."
                    )

                elif LessonRequirement.objects.filter(
                    teacher=new_teacher,
                    subject=requirement.subject,
                    class_group=requirement.class_group,
                    active=True,
                ).exclude(
                    pk=requirement.pk
                ).exists():

                    messages.error(
                        request,
                        "This subject is already assigned to that teacher for this class."
                    )

                else:
                    requirement.teacher = new_teacher
                    requirement.save(
                        update_fields=["teacher"]
                    )

                    messages.success(
                        request,
                        "Teacher reassigned successfully."
                    )

            else:
                messages.error(
                    request,
                    "Please select a valid teacher."
                )

            return redirect(
                reverse("timetable:subject_page")
                + "?subject="
                + str(subject_id)
            )

    # ---------------------------------------------------------
    # REQUIREMENTS
    # ---------------------------------------------------------
    subject_requirements = LessonRequirement.objects.filter(
        active=True
    ).select_related(
        "teacher",
        "subject",
        "class_group",
        "room",
        "preferred_day",
    )

    if selected_subject:
        subject_requirements = subject_requirements.filter(
            subject=selected_subject
        )

    # STAFF MAY ONLY SEE THEIR OWN ASSIGNMENTS.
    if not is_timetable_admin:
        subject_requirements = subject_requirements.filter(
            teacher=selected_teacher
        )

    subject_requirements = subject_requirements.order_by(
        "class_group__name",
        "teacher__name",
        "id",
    )

    # ---------------------------------------------------------
    # TEACHER LIST
    # ---------------------------------------------------------
    if is_timetable_admin:
        teachers = TimetableTeacher.objects.filter(
            active=True
        ).order_by("name")
    else:
        teachers = TimetableTeacher.objects.filter(
            pk=selected_teacher.pk,
            active=True,
        )

    context = {
        "subjects": TimetableSubject.objects.filter(
            active=True
        ).order_by("name"),

        "teachers": teachers,

        "selected_subject": selected_subject,
        "subject_requirements": subject_requirements,

        "is_timetable_admin": is_timetable_admin,
        "selected_teacher": selected_teacher,
    }

    return render(
        request,
        "timetable/subject_assignments.html",
        context,
    )

def timetable_class_page(request):
    from .staff_utils import get_staff_teacher

    # ---------------------------------------------------------
    # ADMIN / STAFF SCOPE
    # ---------------------------------------------------------
    is_timetable_admin = request.user.is_superuser

    if not is_timetable_admin:
        try:
            profile = request.user.profile
            is_timetable_admin = (
                getattr(profile, "role", "") == "ADMIN"
            )
        except Exception:
            is_timetable_admin = False

    selected_teacher = None

    if not is_timetable_admin:
        selected_teacher = get_staff_teacher(request.user)

        if not selected_teacher:
            messages.error(
                request,
                "Your staff account is not linked to an active timetable teacher."
            )
            return redirect("accounts:staff_dashboard")

    # ---------------------------------------------------------
    # PERMISSION
    # ---------------------------------------------------------
    if request.method == "POST":
        denied = _timetable_permission_redirect(
            request,
            "change_lessonrequirement",
        )
    else:
        denied = _timetable_permission_redirect(
            request,
            "view_lessonrequirement",
        )

    if denied:
        return denied

    class_id = request.GET.get("class")
    selected_class = None

    if class_id and str(class_id).isdigit():
        selected_class = TimetableClass.objects.filter(
            pk=int(class_id),
            active=True,
        ).first()

    # ---------------------------------------------------------
    # POST ACTIONS
    # ---------------------------------------------------------
    if request.method == "POST":

        action = request.POST.get("action", "").strip()

        if action == "save_class_lesson":

            requirement_id = request.POST.get("requirement_id")

            if not requirement_id or not requirement_id.isdigit():
                messages.error(
                    request,
                    "Invalid lesson assignment."
                )
                return redirect(
                    reverse("timetable:class_page")
                    + "?class="
                    + str(class_id)
                )

            requirement = LessonRequirement.objects.filter(
                pk=int(requirement_id),
                active=True,
            ).first()

            if (
                requirement is None
                or selected_class is None
                or requirement.class_group_id != selected_class.id
            ):
                messages.error(
                    request,
                    "This lesson assignment does not belong to the selected class."
                )
                return redirect(
                    reverse("timetable:class_page")
                    + "?class="
                    + str(class_id)
                )

            # -------------------------------------------------
            # STAFF OWNERSHIP CHECK
            # -------------------------------------------------
            if (
                not is_timetable_admin
                and requirement.teacher_id != selected_teacher.id
            ):
                messages.error(
                    request,
                    "You can only edit your own timetable lesson assignments."
                )
                return redirect(
                    reverse("timetable:class_page")
                    + "?class="
                    + str(class_id)
                )

            try:
                subject_id = int(
                    request.POST.get("subject", "")
                )

                teacher_id = int(
                    request.POST.get("teacher", "")
                )

                lessons = max(
                    0,
                    int(
                        request.POST.get(
                            "lessons_per_week",
                            "0",
                        )
                    ),
                )

                doubles = max(
                    0,
                    int(
                        request.POST.get(
                            "double_lessons_per_week",
                            "0",
                        )
                    ),
                )

                duration = max(
                    1,
                    int(
                        request.POST.get(
                            "duration_periods",
                            "1",
                        )
                    ),
                )

                priority = int(
                    request.POST.get(
                        "priority",
                        "0",
                    )
                )

            except (TypeError, ValueError):

                messages.error(
                    request,
                    "Please enter valid lesson details."
                )

                return redirect(
                    reverse("timetable:class_page")
                    + "?class="
                    + str(class_id)
                )

            subject = TimetableSubject.objects.filter(
                pk=subject_id,
                active=True,
            ).first()

            teacher = TimetableTeacher.objects.filter(
                pk=teacher_id,
                active=True,
            ).first()

            # -------------------------------------------------
            # STAFF CANNOT SUBMIT ANOTHER TEACHER
            # -------------------------------------------------
            if not is_timetable_admin:

                if (
                    teacher is None
                    or teacher.id != selected_teacher.id
                ):
                    messages.error(
                        request,
                        "You can only assign lessons to your own timetable teacher."
                    )
                    return redirect(
                        reverse("timetable:class_page")
                        + "?class="
                        + str(class_id)
                    )

                teacher = selected_teacher

            room_id = request.POST.get("room", "")
            day_id = request.POST.get("preferred_day", "")

            room = None

            if room_id and room_id.isdigit():
                room = TimetableRoom.objects.filter(
                    pk=int(room_id),
                    active=True,
                ).first()

            preferred_day = None

            if day_id and day_id.isdigit():
                preferred_day = TimetableDay.objects.filter(
                    pk=int(day_id),
                    active=True,
                ).first()

            if not subject or not teacher:
                messages.error(
                    request,
                    "Subject and teacher are required."
                )

                return redirect(
                    reverse("timetable:class_page")
                    + "?class="
                    + str(class_id)
                )

            duplicate = LessonRequirement.objects.filter(
                teacher=teacher,
                subject=subject,
                class_group=requirement.class_group,
                active=True,
            ).exclude(
                pk=requirement.pk
            ).exists()

            if duplicate:
                messages.error(
                    request,
                    "This subject is already assigned to this teacher for this class."
                )

                return redirect(
                    reverse("timetable:class_page")
                    + "?class="
                    + str(class_id)
                )

            requirement.subject = subject
            requirement.teacher = teacher
            requirement.lessons_per_week = lessons
            requirement.double_lessons_per_week = doubles
            requirement.requires_double = doubles > 0
            requirement.duration_periods = duration
            requirement.priority = priority
            requirement.room = room
            requirement.preferred_day = preferred_day
            requirement.practical = (
                request.POST.get("practical") == "1"
            )
            requirement.notes = request.POST.get(
                "notes",
                "",
            )

            requirement.save()

            messages.success(
                request,
                "Lesson assignment updated successfully."
            )

            return redirect(
                reverse("timetable:class_page")
                + "?class="
                + str(requirement.class_group_id)
            )

    # ---------------------------------------------------------
    # EDITING
    # ---------------------------------------------------------
    edit_id = request.GET.get("edit")
    editing_requirement = None

    if edit_id and edit_id.isdigit():

        editing_requirement = LessonRequirement.objects.filter(
            pk=int(edit_id),
            active=True,
        )

        if not is_timetable_admin:
            editing_requirement = editing_requirement.filter(
                teacher=selected_teacher
            )

        editing_requirement = editing_requirement.select_related(
            "teacher",
            "subject",
            "class_group",
            "room",
            "preferred_day",
        ).first()

        if editing_requirement and selected_class:
            if (
                editing_requirement.class_group_id
                != selected_class.id
            ):
                editing_requirement = None

    # ---------------------------------------------------------
    # REQUIREMENTS
    # ---------------------------------------------------------
    class_requirements = LessonRequirement.objects.filter(
        active=True,
    ).select_related(
        "teacher",
        "subject",
        "class_group",
        "room",
        "preferred_day",
    )

    if selected_class:
        class_requirements = class_requirements.filter(
            class_group=selected_class
        )

    if not is_timetable_admin:
        class_requirements = class_requirements.filter(
            teacher=selected_teacher
        )

    class_requirements = class_requirements.order_by(
        "subject__name",
        "teacher__name",
        "id",
    )

    # ---------------------------------------------------------
    # TEACHERS
    # ---------------------------------------------------------
    if is_timetable_admin:
        teachers = TimetableTeacher.objects.filter(
            active=True
        ).order_by("name")
    else:
        teachers = TimetableTeacher.objects.filter(
            pk=selected_teacher.pk,
            active=True,
        )

    context = {
        "classes": TimetableClass.objects.filter(
            active=True
        ).order_by("name"),

        "teachers": teachers,

        "subjects": TimetableSubject.objects.filter(
            active=True
        ).order_by("name"),

        "rooms": TimetableRoom.objects.filter(
            active=True
        ).order_by("name"),

        "days": TimetableDay.objects.filter(
            active=True
        ).order_by("order"),

        "selected_class": selected_class,
        "class_requirements": class_requirements,
        "editing_requirement": editing_requirement,

        "is_timetable_admin": is_timetable_admin,
        "selected_teacher": selected_teacher,
    }

    return render(
        request,
        "timetable/class_assignments.html",
        context,
    )

def _creation_wizard_permission(request, step):
    """
    Enforce Django permissions for each timetable creation-wizard step.

    The wizard only controls access to the relevant timetable operation.
    Operational teacher/class/subject scope remains separate.
    """
    step_permissions = {
        1: "view_timetableterm",
        2: "view_timetableday",
        3: "view_timetableperiod",
        4: "view_timetableclass",
        5: "view_timetablesubject",
        6: "view_timetableteacher",
        7: "view_timetableroom",
        8: "view_teacheravailability",
        9: "view_lessonrequirement",
        10: "view_lessonrequirement",
        11: "add_timetablelesson",
        12: "view_timetablelesson",
        13: "view_timetablelesson",
        14: "view_timetablelesson",
    }

    if step in (11, 12, 13, 14):
        return _timetable_admin_redirect(request)

    permission_codename = step_permissions.get(step)

    if request.method == "POST":
        if step == 9:
            permission_codename = "add_lessonrequirement"
        elif step == 11:
            permission_codename = "add_timetablelesson"

    if not permission_codename:
        return None

    return _timetable_permission_redirect(
        request,
        permission_codename,
    )

def timetable_creation_wizard(request, step=1):
    denied = _creation_wizard_permission(request, step)
    if denied:
        return denied

    # =====================================================
    # SAFE WIZARD DEFAULTS
    # =====================================================
    selected_term_id = request.session.get("timetable_wizard_term")
    selected_classes = request.session.get("timetable_wizard_classes", [])
    selected_subjects = request.session.get("timetable_wizard_subjects", [])
    selected_teachers = request.session.get("timetable_wizard_teachers", [])
    selected_days = request.session.get("timetable_wizard_days", [])
    selected_rooms = request.session.get("timetable_wizard_rooms", [])

    # Safe wizard defaults


    """
    Timetable creation wizard.

    Step 4 is a complete Lesson Assignment Manager:
    - Teacher view
    - Subject view
    - Class view
    - Add
    - Edit
    - Remove
    - Reassign teacher
    """

    from django.contrib import messages
    from django.shortcuts import redirect, render

    from .models import (
TimetableTerm,
TimetableDay,
TimetablePeriod,
TimetableClass,
TimetableSubject,
TimetableTeacher,
TimetableRoom,
LessonRequirement,
TeacherAvailability,
    )

    # ---------------------------------------------------------
    # STAFF / ADMIN SCOPE
    # ---------------------------------------------------------
    from .staff_utils import get_staff_teacher

    is_timetable_admin = request.user.is_superuser

    if not is_timetable_admin:
        try:
            profile = request.user.profile
            is_timetable_admin = (
                getattr(profile, "role", "") == "ADMIN"
            )
        except Exception:
            is_timetable_admin = False

    selected_teacher = None

    if not is_timetable_admin:
        selected_teacher = get_staff_teacher(request.user)

        if not selected_teacher:
            messages.error(
                request,
                "Your staff account is not linked to an active timetable teacher."
            )
            return redirect("accounts:staff_dashboard")

    # BASIC DATA
    # ---------------------------------------------------------

    terms = TimetableTerm.objects.all().order_by("-id")
    days = TimetableDay.objects.filter(active=True).order_by("order", "id")
    periods = TimetablePeriod.objects.filter(active=True).order_by("order", "id")
    classes = TimetableClass.objects.filter(active=True).order_by("name", "stream", "id")
    subjects = TimetableSubject.objects.filter(active=True).order_by("name", "id")
    teachers = TimetableTeacher.objects.filter(active=True).order_by("name", "id")
    rooms = TimetableRoom.objects.filter(active=True).order_by("name", "id")

    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # STEP 1
    # ---------------------------------------------------------

    if step == 1:

        if request.method == "POST":

            term_id = request.POST.get("term")

            if term_id:
                request.session["timetable_wizard_term"] = int(term_id)
                request.session.modified = True
                return redirect(
                    "timetable:creation_wizard_step",
                    2
                )

        return render(
            request,
            "timetable/creation_wizard.html",
            {
                "current_step": 1,
                "terms": terms,
                "selected_term_id": selected_term_id,
            },
        )

    # ---------------------------------------------------------
    # STEP 2
    # ---------------------------------------------------------

    if step == 2:

        if request.method == "POST":

            request.session["timetable_wizard_days"] = list(
                TimetableDay.objects.filter(active=True)
                .order_by("order", "id")
                .values_list("id", flat=True)
            )
            request.session.modified = True
            return redirect(
                "timetable:creation_wizard_step",
                3
            )

        return render(
            request,
            "timetable/creation_wizard.html",
            {
                "current_step": 2,
                "days": days,
                "selected_days": selected_days,
            },
        )

    # ---------------------------------------------------------
    # STEP 3 - PERIOD MANAGEMENT
    # ---------------------------------------------------------

    if step == 3:

        # Use the existing working generic Period Management page.
        return redirect(
            "timetable:crud_list",
            model_key="periods",
        )

    # STEP 4
    if step == 4 and request.method == "POST":
        selected_classes = [
            int(x) for x in request.POST.getlist("classes")
            if str(x).isdigit()
        ]

        request.session["timetable_wizard_classes"] = selected_classes
        request.session.modified = True

        return redirect("timetable:creation_wizard_step", 5)

    # STEP 5
    if step == 5 and request.method == "POST":
        selected_subjects = [
            int(x) for x in request.POST.getlist("subjects")
            if str(x).isdigit()
        ]

        request.session["timetable_wizard_subjects"] = selected_subjects
        request.session.modified = True

        return redirect("timetable:creation_wizard_step", 6)

    # STEP 6
    if step == 6 and request.method == "POST":

        if is_timetable_admin:
            selected_teachers = [
                int(x)
                for x in request.POST.getlist("teachers")
                if str(x).isdigit()
            ]
        else:
            # Staff cannot choose another timetable teacher.
            selected_teachers = [selected_teacher.pk]

        request.session["timetable_wizard_teachers"] = selected_teachers
        request.session.modified = True

        return redirect("timetable:creation_wizard_step", 7)

    # STEP 7
    if step == 7 and request.method == "POST":
        selected_rooms = [
            int(x) for x in request.POST.getlist("rooms")
            if str(x).isdigit()
        ]

        request.session["timetable_wizard_rooms"] = selected_rooms
        request.session.modified = True

        return redirect("timetable:creation_wizard_step", 8)

    # STEP 8
    if step == 8 and request.method == "POST":
        return redirect("timetable:creation_wizard_step", 9)

    # STEP 9
    if step == 9 and request.method == "POST":
        action = request.POST.get("requirement_action")

        if action == "save":
            class_id = request.POST.get("class_group")
            subject_id = request.POST.get("subject")
            submitted_teacher_id = request.POST.get("teacher") or None
            room_id = request.POST.get("room") or None
            preferred_day_id = request.POST.get("preferred_day") or None

            class_group = None
            subject = None
            teacher = None
            room = None
            preferred_day = None

            # -------------------------------------------------
            # CLASS
            # -------------------------------------------------
            if class_id and str(class_id).isdigit():
                class_group = (
                    TimetableClass.objects
                    .filter(
                        pk=int(class_id),
                        active=True,
                    )
                    .first()
                )

            # -------------------------------------------------
            # SUBJECT
            # -------------------------------------------------
            if subject_id and str(subject_id).isdigit():
                subject = (
                    TimetableSubject.objects
                    .filter(
                        pk=int(subject_id),
                        active=True,
                    )
                    .first()
                )

            # -------------------------------------------------
            # TEACHER
            # -------------------------------------------------
            if is_timetable_admin:
                if (
                    submitted_teacher_id
                    and str(submitted_teacher_id).isdigit()
                ):
                    teacher = (
                        TimetableTeacher.objects
                        .filter(
                            pk=int(submitted_teacher_id),
                            active=True,
                        )
                        .first()
                    )
            else:
                # Staff are permanently scoped to their
                # authenticated HR-linked timetable teacher.
                teacher = selected_teacher

                if (
                    submitted_teacher_id
                    and str(submitted_teacher_id).isdigit()
                    and int(submitted_teacher_id) != selected_teacher.pk
                ):
                    messages.error(
                        request,
                        "You can only create timetable requirements for your own teacher account."
                    )
                    return redirect(
                        "timetable:creation_wizard_step",
                        9
                    )

            # -------------------------------------------------
            # ROOM
            # -------------------------------------------------
            if room_id and str(room_id).isdigit():
                room = (
                    TimetableRoom.objects
                    .filter(
                        pk=int(room_id),
                        active=True,
                    )
                    .first()
                )

            # -------------------------------------------------
            # PREFERRED DAY
            # -------------------------------------------------
            if preferred_day_id and str(preferred_day_id).isdigit():
                preferred_day = (
                    TimetableDay.objects
                    .filter(
                        pk=int(preferred_day_id),
                        active=True,
                    )
                    .first()
                )

            # -------------------------------------------------
            # LESSON COUNTS
            # -------------------------------------------------
            try:
                single = int(
                    request.POST.get("single_lessons", 0) or 0
                )
            except Exception:
                single = 0

            try:
                double = int(
                    request.POST.get("double_lessons", 0) or 0
                )
            except Exception:
                double = 0

            if single < 0:
                single = 0

            if double < 0:
                double = 0

            total = single + double

            # -------------------------------------------------
            # DURATION
            # -------------------------------------------------
            try:
                duration_periods = int(
                    request.POST.get("duration_periods", 1) or 1
                )
            except Exception:
                duration_periods = 1

            if duration_periods < 1:
                duration_periods = 1

            # -------------------------------------------------
            # PRIORITY
            # -------------------------------------------------
            try:
                priority = int(
                    request.POST.get("priority", 50) or 50
                )
            except Exception:
                priority = 50

            if priority < 0:
                priority = 0

            # -------------------------------------------------
            # VALIDATE REQUIRED OBJECTS
            # -------------------------------------------------
            if not class_group:
                messages.error(
                    request,
                    "Please select a valid active class."
                )
                return redirect(
                    "timetable:creation_wizard_step",
                    9
                )

            if not subject:
                messages.error(
                    request,
                    "Please select a valid active subject."
                )
                return redirect(
                    "timetable:creation_wizard_step",
                    9
                )

            if not teacher:
                messages.error(
                    request,
                    "Please select a valid active timetable teacher."
                )
                return redirect(
                    "timetable:creation_wizard_step",
                    9
                )

            if total <= 0:
                messages.error(
                    request,
                    "At least one lesson per week is required."
                )
                return redirect(
                    "timetable:creation_wizard_step",
                    9
                )

            # -------------------------------------------------
            # PREVENT ACTIVE DUPLICATE
            # -------------------------------------------------
            duplicate = LessonRequirement.objects.filter(
                class_group=class_group,
                subject=subject,
                teacher=teacher,
                active=True,
            ).exists()

            if duplicate:
                messages.error(
                    request,
                    "An active timetable requirement already exists for this class, subject and teacher."
                )
                return redirect(
                    "timetable:creation_wizard_step",
                    9
                )

            # -------------------------------------------------
            # CREATE REQUIREMENT
            # -------------------------------------------------
            LessonRequirement.objects.create(
                class_group=class_group,
                subject=subject,
                teacher=teacher,
                room=room,
                lessons_per_week=total,
                double_lessons_per_week=double,
                requires_double=double > 0,
                duration_periods=duration_periods,
                priority=priority,
                practical=(
                    request.POST.get("practical") == "1"
                ),
                preferred_day=preferred_day,
                notes=request.POST.get("notes") or "",
                active=True,
            )

            messages.success(
                request,
                "Timetable lesson requirement added successfully."
            )

        return redirect(
            "timetable:creation_wizard_step",
            9
        )
    # STEP 10
    if step == 10 and request.method == "POST":
        request.session["timetable_wizard_confirmed"] = True
        request.session.modified = True

        return redirect(
            "timetable:creation_wizard_step",
            11
        )

    # STEP 11
    if step == 11 and request.method == "POST":
        return redirect(
            "timetable:generation_control"
        )

    # STEP 12
    if step == 12 and request.method == "POST":
        return redirect(
            "timetable:smart_conflicts"
        )

    # STEP 13
    if step == 13 and request.method == "POST":
        return redirect(
            "timetable:workspace"
        )

    # STEP 14
    if step == 14 and request.method == "POST":
        return redirect(
            "timetable:workspace"
        )

    terms = TimetableTerm.objects.all().order_by("-id")
    days = TimetableDay.objects.filter(active=True).order_by("order", "id")
    periods = TimetablePeriod.objects.filter(active=True).order_by("order", "id")
    classes = TimetableClass.objects.filter(active=True).order_by("name", "stream", "id")
    subjects = TimetableSubject.objects.filter(active=True).order_by("name", "id")
    teachers = TimetableTeacher.objects.filter(active=True).order_by("name", "id")
    rooms = TimetableRoom.objects.filter(active=True).order_by("name", "id")

    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # STEP 1
    # ---------------------------------------------------------

    if step == 1:

        if request.method == "POST":

            term_id = request.POST.get("term")

            if term_id:
                request.session["timetable_wizard_term"] = int(term_id)
                request.session.modified = True
                return redirect(
                    "timetable:creation_wizard_step",
                    2
                )

        return render(
            request,
            "timetable/creation_wizard.html",
            {
                "current_step": 1,
                "terms": terms,
                "selected_term_id": selected_term_id,
            },
        )

    # ---------------------------------------------------------
    # STEP 2
    # ---------------------------------------------------------

    if step == 2:

        if request.method == "POST":

            request.session["timetable_wizard_days"] = list(
                TimetableDay.objects.filter(active=True)
                .order_by("order", "id")
                .values_list("id", flat=True)
            )
            request.session.modified = True
            return redirect(
                "timetable:creation_wizard_step",
                3
            )

        return render(
            request,
            "timetable/creation_wizard.html",
            {
                "current_step": 2,
                "days": days,
                "selected_days": selected_days,
            },
        )

    # ---------------------------------------------------------
    # STEP 3 - PERIODS & BREAKS
    # ---------------------------------------------------------

    if step == 3 and request.method == "POST":

        action = request.POST.get("wizard_action", "save_next")

        # ADD NEW PERIOD / BREAK
        if action == "add_period":

            name = (request.POST.get("new_name") or "").strip()
            start_time = request.POST.get("new_start") or None
            end_time = request.POST.get("new_end") or None
            item_type = request.POST.get("new_type", "period")

            if not name:
                messages.error(
                    request,
                    "Please enter a name for the new period or break."
                )

            elif not start_time or not end_time:
                messages.error(
                    request,
                    "Please enter both start and end times."
                )

            else:
                last_order = (
                    TimetablePeriod.objects.aggregate(
                        max_order=Max("order")
                    ).get("max_order") or 0
                )

                TimetablePeriod.objects.create(
                    name=name,
                    start_time=start_time,
                    end_time=end_time,
                    order=last_order + 1,
                    is_break=(item_type == "break"),
                    is_lunch=(item_type == "lunch"),
                    is_activity=(item_type == "activity"),
                    active=True,
                )

                messages.success(
                    request,
                    '"{}" was added successfully.'.format(name)
                )

            return redirect(
                "timetable:creation_wizard_step",
                3
            )

        # DELETE PERIOD / BREAK
        if action == "delete_period":

            pid = request.POST.get("delete_period_id")

            try:
                period = TimetablePeriod.objects.get(
                    pk=pid,
                    active=True
                )

                if TimetableLesson.objects.filter(
                    period=period
                ).exists():

                    messages.error(
                        request,
                        '"{}" cannot be deleted because it is already '
                        'used by timetable lessons.'.format(period.name)
                    )

                else:
                    period.active = False
                    period.save(update_fields=["active"])

                    messages.success(
                        request,
                        '"{}" was deleted successfully.'.format(period.name)
                    )

            except TimetablePeriod.DoesNotExist:

                messages.error(
                    request,
                    "The selected period or break no longer exists."
                )

            return redirect(
                "timetable:creation_wizard_step",
                3
            )

        # SAVE / EDIT EXISTING PERIODS
        for pid in request.POST.getlist("period_id"):

            try:
                period = TimetablePeriod.objects.get(
                    pk=pid,
                    active=True
                )

                period.name = request.POST.get(
                    "name_" + str(pid),
                    period.name
                )

                start_time = request.POST.get(
                    "start_" + str(pid)
                )

                end_time = request.POST.get(
                    "end_" + str(pid)
                )

                if start_time:
                    period.start_time = start_time

                if end_time:
                    period.end_time = end_time

                period.is_break = (
                    request.POST.get("break_" + str(pid)) == "1"
                )

                period.is_lunch = (
                    request.POST.get("lunch_" + str(pid)) == "1"
                )

                period.is_activity = (
                    request.POST.get("activity_" + str(pid)) == "1"
                )

                period.save()

            except Exception:
                pass

        messages.success(
            request,
            "Periods and breaks saved successfully."
        )

        return redirect(
            "timetable:creation_wizard_step",
            4
        )
    # STEP 4
    if step == 4 and request.method == "POST":
        selected_classes = [
            int(x) for x in request.POST.getlist("classes")
            if str(x).isdigit()
        ]

        request.session["timetable_wizard_classes"] = selected_classes
        request.session.modified = True

        return redirect("timetable:creation_wizard_step", 5)

    # STEP 5
    if step == 5 and request.method == "POST":
        selected_subjects = [
            int(x) for x in request.POST.getlist("subjects")
            if str(x).isdigit()
        ]

        request.session["timetable_wizard_subjects"] = selected_subjects
        request.session.modified = True

        return redirect("timetable:creation_wizard_step", 6)

    # STEP 6
    if step == 6 and request.method == "POST":
        selected_teachers = [
            int(x) for x in request.POST.getlist("teachers")
            if str(x).isdigit()
        ]

        request.session["timetable_wizard_teachers"] = selected_teachers
        request.session.modified = True

        return redirect("timetable:creation_wizard_step", 7)

    # STEP 7
    if step == 7 and request.method == "POST":
        selected_rooms = [
            int(x) for x in request.POST.getlist("rooms")
            if str(x).isdigit()
        ]

        request.session["timetable_wizard_rooms"] = selected_rooms
        request.session.modified = True

        return redirect("timetable:creation_wizard_step", 8)

    # STEP 8
    if step == 8 and request.method == "POST":
        return redirect("timetable:creation_wizard_step", 9)

    # STEP 10
    if step == 10 and request.method == "POST":
        request.session["timetable_wizard_confirmed"] = True
        request.session.modified = True
        return redirect("timetable:creation_wizard_step", 11)

    # STEP 11
    if step == 11 and request.method == "POST":
        return redirect("timetable:generation_control")

    # STEP 12
    if step == 12 and request.method == "POST":
        return redirect("timetable:smart_conflicts")

    # STEP 13
    if step == 13 and request.method == "POST":
        return redirect("timetable:workspace")

    # STEP 14
    if step == 14 and request.method == "POST":
        return redirect("timetable:workspace")

    terms = TimetableTerm.objects.all().order_by(
"-academic_year",
"term_name"
    )

    selected_term = None

    if selected_term_id:
        try:
            selected_term = TimetableTerm.objects.get(
                pk=selected_term_id
            )
        except Exception:
            selected_term = None

    days = TimetableDay.objects.filter(
        active=True
    ).order_by("order")

    periods = TimetablePeriod.objects.filter(
        active=True
    ).order_by("order")

    classes = TimetableClass.objects.filter(
        active=True
    ).order_by("level", "name", "stream")

    subjects = TimetableSubject.objects.filter(
        active=True
    ).order_by("name")

    teachers = TimetableTeacher.objects.filter(
        active=True
    ).order_by("name")

    rooms = TimetableRoom.objects.filter(
        active=True
    ).order_by("name")

    requirements = LessonRequirement.objects.filter(
        active=True
    ).select_related(
        "class_group",
        "subject",
        "teacher",
        "room",
    ).order_by(
        "class_group__name",
        "subject__name",
    )

    availability = TeacherAvailability.objects.filter(
        teacher__active=True
    ).select_related(
        "teacher",
        "day",
        "period",
    ).order_by(
        "teacher__name",
        "day__order",
        "period__order",
    )[:300]

    lesson_count = 0
    locked_count = 0

    if selected_term:
        lesson_count = TimetableLesson.objects.filter(
            term=selected_term
        ).count()

        locked_count = TimetableLesson.objects.filter(
            term=selected_term,
            locked=True
        ).count()

    steps = [
        (1, "Academic Year & Term"),
        (2, "School Days"),
        (3, "Periods & Breaks"),
        (4, "Classes"),
        (5, "Subjects"),
        (6, "Teachers"),
        (7, "Rooms"),
        (8, "Teacher Availability"),
        (9, "Lesson Requirements"),
        (10, "Review & Confirm"),
        (11, "Generate Timetable"),
        (12, "Smart Conflicts"),
        (13, "Workspace"),
        (14, "Workspace"),
    ]

    return render(
request,
"timetable/creation_wizard.html",
{
    "steps": steps,
    "current_step": step,
    "selected_term": selected_term,
    "terms": terms,
    "days": days,
    "periods": periods,
    "classes": classes,
    "subjects": subjects,
    "teachers": teachers,
    "rooms": rooms,
    "availability": availability,
    "requirements": requirements,
    "selected_classes": selected_classes,
    "selected_subjects": selected_subjects,
    "selected_teachers": selected_teachers,
    "selected_rooms": selected_rooms,
    "lesson_count": lesson_count,
    "locked_count": locked_count,
}
    )

# ===== FINAL TIMETABLE WIZARD END =====


# =========================================================
# PRINT PREVIEW CENTRE
# =========================================================

@login_required
def timetable_print_preview(request):
    # =========================================================
    # PRINT PREVIEW - USE THE SAME MASTER GRID AS WORKSPACE
    # =========================================================

    selected_year = request.GET.get("year", "").strip()
    selected_term_name = request.GET.get("term", "").strip()
    preview_type = request.GET.get("type", "school").strip()

    selected_class_id = request.GET.get("class", "").strip()
    selected_teacher_id = request.GET.get("teacher", "").strip()

    valid_types = {
        "school",
        "class",
        "teacher",
        "all_teachers",
    }

    if preview_type not in valid_types:
        preview_type = "school"

    # ---------------------------------------------------------
    # TERMS
    # ---------------------------------------------------------
    terms = (
        TimetableTerm.objects
        .filter(active=True)
        .order_by("-academic_year", "term_name", "-id")
    )

    academic_years = list(
        TimetableTerm.objects
        .filter(active=True)
        .values_list("academic_year", flat=True)
        .distinct()
        .order_by("-academic_year")
    )

    # ---------------------------------------------------------
    # SELECT TERM
    # ---------------------------------------------------------
    selected_term = None

    if selected_year and selected_term_name:
        selected_term = (
            TimetableTerm.objects
            .filter(
                active=True,
                academic_year=selected_year,
                term_name=selected_term_name,
            )
            .order_by("-id")
            .first()
        )

    # If no explicit URL term, use the generated term.
    if not selected_term:
        generated_result = request.session.get(
            "timetable_generation_result"
        )

        generated_term_text = ""

        if generated_result:
            generated_term_text = str(
                generated_result.get("term", "")
            ).strip()

        if generated_term_text:
            for candidate in terms:
                if str(candidate) == generated_term_text:
                    selected_term = candidate
                    break

    # Final fallback.
    if not selected_term:
        selected_term = terms.first()

    if selected_term:
        selected_year = str(selected_term.academic_year)
        selected_term_name = str(selected_term.term_name)

    # ---------------------------------------------------------
    # DAYS / PERIODS
    # ---------------------------------------------------------
    days = list(
        TimetableDay.objects
        .filter(active=True)
        .order_by("order", "id")
    )

    periods = list(
        TimetablePeriod.objects
        .filter(active=True)
        .order_by("order", "id")
    )

    # ---------------------------------------------------------
    # CLASSES / TEACHERS
    # ---------------------------------------------------------
    classes = (
        TimetableClass.objects
        .filter(active=True)
        .order_by("level", "name", "stream")
    )

    teachers = (
        TimetableTeacher.objects
        .filter(active=True)
        .order_by("name")
    )

    selected_class = None
    selected_teacher = None

    if selected_class_id.isdigit():
        selected_class = classes.filter(
            pk=int(selected_class_id)
        ).first()

    if selected_teacher_id.isdigit():
        selected_teacher = teachers.filter(
            pk=int(selected_teacher_id)
        ).first()

    # ---------------------------------------------------------
    # MASTER GRID BUILDER
    # THIS IS THE SAME STRUCTURE USED BY WORKSPACE
    # ---------------------------------------------------------
    def build_master_rows(lesson_list):

        grouped = {}

        for lesson in lesson_list:

            key = (
                lesson.day_id,
                lesson.class_group_id,
            )

            if key not in grouped:
                grouped[key] = {
                    "day": lesson.day,
                    "class_group": lesson.class_group,
                    "lessons": {},
                }

            grouped[key]["lessons"][lesson.period_id] = lesson

        master_rows = []

        for day in days:

            day_rows = [
                row
                for key, row in grouped.items()
                if key[0] == day.id
            ]

            if not teacher_mode:
                day_rows.sort(
                    key=lambda row: (
                        row["class_group"].name,
                        row["class_group"].stream,
                    )
                )

            # Always display every active school day.
            if not day_rows:

                empty_cells = []

                for period in periods:
                    empty_cells.append({
                        "period": period,
                        "lesson": None,
                        "colspan": 1,
                    })

                master_rows.append({
                    "day": day,
                    "class_group": None,
                    "cells": empty_cells,
                    "first_day_row": True,
                    "day_rowspan": 1,
                    "empty_day": True,
                })

                continue

            for index, row in enumerate(day_rows):

                lesson_map = row["lessons"]
                cells = []
                skip_period_ids = set()

                for i, period in enumerate(periods):

                    if period.id in skip_period_ids:
                        continue

                    lesson = lesson_map.get(period.id)

                    if lesson:

                        duration = max(
                            1,
                            int(lesson.duration_periods or 1)
                        )

                        colspan = 1
                        covered = []

                        if duration > 1:

                            for next_period in periods[i + 1:]:

                                if (
                                    next_period.is_break
                                    or next_period.is_lunch
                                    or next_period.is_activity
                                ):
                                    break

                                if next_period.id in lesson_map:
                                    break

                                covered.append(next_period.id)

                                if len(covered) >= duration - 1:
                                    break

                        colspan += len(covered)
                        skip_period_ids.update(covered)

                        cells.append({
                            "period": period,
                            "lesson": lesson,
                            "colspan": colspan,
                        })

                    else:

                        cells.append({
                            "period": period,
                            "lesson": None,
                            "colspan": 1,
                        })

                master_rows.append({
                    "day": day,
                    "class_group": row["class_group"],
                    "cells": cells,
                    "first_day_row": index == 0,
                    "day_rowspan": len(day_rows),
                })

            # Mark BREAK, LUNCH and ACTIVITY so they can be
            # displayed once as vertically merged cells per day.
            for period in periods:
                if not (
                    period.is_break
                    or period.is_lunch
                    or period.is_activity
                ):
                    continue

                first = True

                for row_index in range(
                    len(master_rows) - len(day_rows),
                    len(master_rows)
                ):
                    row = master_rows[row_index]

                    for cell in row["cells"]:
                        if cell["period"].id == period.id:
                            if first:
                                cell["special_rowspan"] = len(day_rows)
                                cell["special_first"] = True
                                first = False
                            else:
                                cell["special_skip"] = True

        return master_rows

    # ---------------------------------------------------------
    # LOAD ALL LESSONS FOR SELECTED TERM
    # ---------------------------------------------------------
    all_lessons = []

    if selected_term:

        all_lessons = list(
            TimetableLesson.objects
            .filter(term=selected_term)
            .select_related(
                "class_group",
                "subject",
                "teacher",
                "room",
                "day",
                "period",
            )
            .order_by(
                "day__order",
                "class_group__name",
                "class_group__stream",
                "period__order",
            )
        )

    # ---------------------------------------------------------
    # FILTER FOR SCHOOL / CLASS / TEACHER
    # ---------------------------------------------------------
    lessons = all_lessons

    if preview_type == "class" and selected_class:

        lessons = [
            lesson
            for lesson in all_lessons
            if lesson.class_group_id == selected_class.id
        ]

    elif preview_type == "teacher" and selected_teacher:

        lessons = [
            lesson
            for lesson in all_lessons
            if lesson.teacher_id == selected_teacher.id
        ]

    # ---------------------------------------------------------
    # MAIN MASTER GRID
    # ---------------------------------------------------------
    master_rows = build_master_rows(lessons)

    # ---------------------------------------------------------
    # ALL TEACHERS
    # EACH TEACHER GETS THE SAME MASTER GRID
    # ---------------------------------------------------------
    teacher_previews = []

    if preview_type == "all_teachers" and selected_term:

        teacher_ids = sorted(
            {
                lesson.teacher_id
                for lesson in all_lessons
                if lesson.teacher_id
            }
        )

        teachers_with_lessons = teachers.filter(
            id__in=teacher_ids
        )

        for teacher in teachers_with_lessons:

            teacher_lessons = [
                lesson
                for lesson in all_lessons
                if lesson.teacher_id == teacher.id
            ]

            teacher_previews.append({
                "teacher": teacher,
                "lessons": teacher_lessons,
                "master_rows": build_master_rows(
                    teacher_lessons
                ),
            })

    # ---------------------------------------------------------
    # CONTEXT
    # ---------------------------------------------------------
    context = {
        "terms": terms,
        "academic_years": academic_years,

        "selected_year": selected_year,
        "selected_term_name": selected_term_name,
        "selected_term": selected_term,

        "preview_type": preview_type,

        "classes": classes,
        "teachers": teachers,

        "selected_class": selected_class,
        "selected_teacher": selected_teacher,

        "lessons": lessons,
        "master_rows": master_rows,
        "teacher_previews": teacher_previews,

        "days": days,
        "periods": periods,

        "generation_result": request.session.get(
            "timetable_generation_result"
        ),
    }

    return render(
        request,
        "timetable/print_preview.html",
        context,
    )

def timetable_print_preview(request):
    from .models import (
        TimetableTerm,
        TimetableDay,
        TimetablePeriod,
        TimetableClass,
        TimetableTeacher,
        TimetableLesson,
    )

    # ---------------------------------------------------------
    # PREVIEW TYPE
    # ---------------------------------------------------------

    preview_type = request.GET.get("type", "school").strip()

    if preview_type not in (
        "school",
        "class",
        "teacher",
        "all_teachers",
    ):
        preview_type = "school"

    # ---------------------------------------------------------
    # BASIC DATA
    # ---------------------------------------------------------

    terms = list(
        TimetableTerm.objects
        .filter(active=True)
        .order_by("-academic_year", "term_name", "-id")
    )

    academic_years = list(
        TimetableTerm.objects
        .filter(active=True)
        .values_list("academic_year", flat=True)
        .distinct()
        .order_by("-academic_year")
    )

    days = list(
        TimetableDay.objects
        .filter(active=True)
        .order_by("order", "id")
    )

    periods = list(
        TimetablePeriod.objects
        .filter(active=True)
        .order_by("order", "id")
    )

    classes = (
        TimetableClass.objects
        .filter(active=True)
        .order_by("level", "name", "stream", "id")
    )

    teachers = (
        TimetableTeacher.objects
        .filter(active=True)
        .order_by("name", "id")
    )

    # ---------------------------------------------------------
    # TERM
    #
    # IMPORTANT:
    # First use the same selected term as Workspace.
    # This is what gives us 2026 Term 3 / lesson records.
    # ---------------------------------------------------------

    selected_term = get_selected_timetable_term(request)

    # If a user explicitly selected another year + term,
    # honour that selection.
    requested_year = request.GET.get("year", "").strip()
    requested_term = request.GET.get("term", "").strip()

    if requested_year and requested_term:

        requested = (
            TimetableTerm.objects
            .filter(
                active=True,
                academic_year=requested_year,
                term_name=requested_term,
            )
            .order_by("-id")
            .first()
        )

        if requested:
            selected_term = requested

    selected_year = ""
    selected_term_name = ""

    if selected_term:
        selected_year = str(selected_term.academic_year)
        selected_term_name = str(selected_term.term_name)

    # ---------------------------------------------------------
    # LOAD ALL LESSONS FIRST
    # ---------------------------------------------------------

    if selected_term:

        all_lessons = list(
            TimetableLesson.objects
            .filter(term=selected_term)
            .select_related(
                "class_group",
                "subject",
                "teacher",
                "room",
                "day",
                "period",
            )
            .order_by(
                "day__order",
                "class_group__name",
                "class_group__stream",
                "period__order",
                "id",
            )
        )

    else:
        all_lessons = []

    # ---------------------------------------------------------
    # SELECTED CLASS / TEACHER
    # ---------------------------------------------------------

    selected_class = None
    selected_teacher = None

    class_id = request.GET.get("class", "").strip()
    teacher_id = request.GET.get("teacher", "").strip()

    if class_id.isdigit():
        selected_class = classes.filter(
            id=int(class_id)
        ).first()

    if teacher_id.isdigit():
        selected_teacher = teachers.filter(
            id=int(teacher_id)
        ).first()

    # ---------------------------------------------------------
    # FILTER LESSONS
    # ---------------------------------------------------------

    preview_lessons = all_lessons

    if preview_type == "class" and selected_class:

        preview_lessons = [
            lesson
            for lesson in all_lessons
            if lesson.class_group_id == selected_class.id
        ]

    elif preview_type == "teacher" and selected_teacher:

        preview_lessons = [
            lesson
            for lesson in all_lessons
            if lesson.teacher_id == selected_teacher.id
        ]

    # ---------------------------------------------------------
    # BUILD MASTER GRID
    #
    # This is the same algorithm used by Workspace.
    # ---------------------------------------------------------

    def build_master_rows(lessons):

        grouped = {}

        for lesson in lessons:

            key = (
                lesson.day_id,
                lesson.class_group_id,
            )

            if key not in grouped:

                grouped[key] = {
                    "day": lesson.day,
                    "class_group": lesson.class_group,
                    "lessons": {},
                }

            grouped[key]["lessons"][lesson.period_id] = lesson

        master_rows = []

        for day in days:

            day_rows = [
                row
                for key, row in grouped.items()
                if key[0] == day.id
            ]

            day_rows.sort(
                key=lambda row: (
                    row["class_group"].name,
                    row["class_group"].stream,
                )
            )

            # Same Workspace behaviour:
            # display every active school day.
            if not day_rows:

                empty_cells = []

                for period in periods:

                    empty_cells.append({
                        "period": period,
                        "lesson": None,
                        "colspan": 1,
                    })

                master_rows.append({
                    "day": day,
                    "class_group": None,
                    "cells": empty_cells,
                    "first_day_row": True,
                    "day_rowspan": 1,
                    "empty_day": True,
                })

                continue

            for index, row in enumerate(day_rows):

                lesson_map = row["lessons"]

                cells = []

                skip_period_ids = set()

                for i, period in enumerate(periods):

                    if period.id in skip_period_ids:
                        continue

                    lesson = lesson_map.get(period.id)

                    if lesson:

                        duration = max(
                            1,
                            int(
                                lesson.duration_periods or 1
                            )
                        )

                        colspan = 1

                        covered = []

                        if duration > 1:

                            for next_period in periods[i + 1:]:

                                if (
                                    next_period.is_break
                                    or next_period.is_lunch
                                    or next_period.is_activity
                                ):
                                    break

                                if next_period.id in lesson_map:
                                    break

                                covered.append(
                                    next_period.id
                                )

                                if len(covered) >= duration - 1:
                                    break

                        colspan += len(covered)

                        skip_period_ids.update(
                            covered
                        )

                        cells.append({
                            "period": period,
                            "lesson": lesson,
                            "colspan": colspan,
                        })

                    else:

                        cells.append({
                            "period": period,
                            "lesson": None,
                            "colspan": 1,
                        })

                master_rows.append({
                    "day": day,
                    "class_group": row["class_group"],
                    "cells": cells,
                    "first_day_row": index == 0,
                    "day_rowspan": len(day_rows),
                })

        return master_rows

    master_rows = build_master_rows(preview_lessons)

    # ---------------------------------------------------------
    # ALL TEACHERS
    # ---------------------------------------------------------

    teacher_previews = []

    if preview_type == "all_teachers":

        teacher_ids = sorted({
            lesson.teacher_id
            for lesson in all_lessons
            if lesson.teacher_id
        })

        teachers_with_lessons = teachers.filter(
            id__in=teacher_ids
        )

        for teacher in teachers_with_lessons:

            teacher_lessons = [
                lesson
                for lesson in all_lessons
                if lesson.teacher_id == teacher.id
            ]

            teacher_previews.append({
                "teacher": teacher,
                "master_rows": build_master_rows(
                    teacher_lessons
                ),
            })

    # ---------------------------------------------------------
    # DEBUG INFORMATION FOR TEMPLATE
    # ---------------------------------------------------------

    preview_lesson_count = len(preview_lessons)
    all_lesson_count = len(all_lessons)

    return render(
        request,
        "timetable/print_preview.html",
        {
            "terms": terms,
            "academic_years": academic_years,

            "selected_year": selected_year,
            "selected_term_name": selected_term_name,
            "selected_term": selected_term,

            "preview_type": preview_type,

            "classes": classes,
            "teachers": teachers,

            "selected_class": selected_class,
            "selected_teacher": selected_teacher,

            "days": days,
            "periods": periods,

            "lessons": preview_lessons,
            "master_rows": master_rows,

            "teacher_previews": teacher_previews,

            "all_lesson_count": all_lesson_count,
            "preview_lesson_count": preview_lesson_count,
        },
    )
def timetable_print_preview(request):
    from .models import (
        TimetableTerm,
        TimetableDay,
        TimetablePeriod,
        TimetableClass,
        TimetableTeacher,
        TimetableLesson,
    )

    preview_type = request.GET.get("type", "school").strip()

    if preview_type not in {
        "school",
        "class",
        "teacher",
        "all_teachers",
    }:
        preview_type = "school"

    requested_year = request.GET.get("year", "").strip()
    requested_term_name = request.GET.get("term", "").strip()

    selected_class_id = request.GET.get("class", "").strip()
    selected_teacher_id = request.GET.get("teacher", "").strip()

    terms = list(
        TimetableTerm.objects
        .filter(active=True)
        .order_by("-academic_year", "term_name", "-id")
    )

    academic_years = list(
        TimetableTerm.objects
        .filter(active=True)
        .values_list("academic_year", flat=True)
        .distinct()
        .order_by("-academic_year")
    )

    days = list(
        TimetableDay.objects
        .filter(active=True)
        .order_by("order")
    )

    periods = list(
        TimetablePeriod.objects
        .filter(active=True)
        .order_by("order")
    )

    classes = (
        TimetableClass.objects
        .filter(active=True)
        .order_by("level", "name", "stream")
    )

    teachers = (
        TimetableTeacher.objects
        .filter(active=True)
        .order_by("name")
    )

    # ---------------------------------------------------------
    # TERM SELECTION
    # Use the SAME logic as Workspace unless the user
    # explicitly changes the term in the Preview form.
    # ---------------------------------------------------------

    selected_term = None

    if requested_year and requested_term_name:
        selected_term = (
            TimetableTerm.objects
            .filter(
                active=True,
                academic_year=requested_year,
                term_name=requested_term_name,
            )
            .first()
        )

    # If there was no explicit term selection, use exactly
    # the Workspace selection function.
    if not selected_term:
        selected_term = get_selected_timetable_term(request)

    # Safety fallback: choose the active term containing
    # generated lessons.
    if not selected_term:
        selected_term = (
            TimetableTerm.objects
            .filter(
                active=True,
                lessons__isnull=False,
            )
            .distinct()
            .order_by("-academic_year", "-id")
            .first()
        )

    selected_year = ""
    selected_term_name = ""

    if selected_term:
        selected_year = str(selected_term.academic_year)
        selected_term_name = str(selected_term.term_name)

    selected_class = None
    selected_teacher = None

    if selected_class_id.isdigit():
        selected_class = classes.filter(
            pk=int(selected_class_id)
        ).first()

    if selected_teacher_id.isdigit():
        selected_teacher = teachers.filter(
            pk=int(selected_teacher_id)
        ).first()

    # ---------------------------------------------------------
    # BASE LESSONS
    # ---------------------------------------------------------

    if selected_term:
        all_lessons = (
            TimetableLesson.objects
            .filter(term=selected_term)
            .select_related(
                "class_group",
                "subject",
                "teacher",
                "room",
                "day",
                "period",
            )
            .order_by(
                "day__order",
                "class_group__name",
                "class_group__stream",
                "period__order",
            )
        )
    else:
        all_lessons = TimetableLesson.objects.none()

    # ---------------------------------------------------------
    # EXACT WORKSPACE MASTER ROW BUILDER
    # ---------------------------------------------------------

    def build_master_rows(lessons_queryset):

        lessons = list(lessons_queryset)

        grouped = {}

        for lesson in lessons:

            key = (
                lesson.day_id,
                lesson.class_group_id,
            )

            if key not in grouped:
                grouped[key] = {
                    "day": lesson.day,
                    "class_group": lesson.class_group,
                    "lessons": {},
                }

            grouped[key]["lessons"][lesson.period_id] = lesson

        master_rows = []

        for day in days:

            day_rows = [
                row
                for key, row in grouped.items()
                if key[0] == day.id
            ]

            day_rows.sort(
                key=lambda row: (
                    row["class_group"].name,
                    row["class_group"].stream,
                )
            )

            if not day_rows:

                empty_cells = []

                for period in periods:
                    empty_cells.append({
                        "period": period,
                        "lesson": None,
                        "colspan": 1,
                    })

                master_rows.append({
                    "day": day,
                    "class_group": None,
                    "cells": empty_cells,
                    "first_day_row": True,
                    "day_rowspan": 1,
                    "empty_day": True,
                })

                continue

            for index, row in enumerate(day_rows):

                lesson_map = row["lessons"]

                cells = []
                skip_period_ids = set()

                for i, period in enumerate(periods):

                    if period.id in skip_period_ids:
                        continue

                    lesson = lesson_map.get(period.id)

                    if lesson:

                        duration = max(
                            1,
                            int(
                                lesson.duration_periods or 1
                            )
                        )

                        colspan = 1
                        covered = []

                        if duration > 1:

                            for next_period in periods[i + 1:]:

                                if (
                                    next_period.is_break
                                    or next_period.is_lunch
                                    or next_period.is_activity
                                ):
                                    break

                                if next_period.id in lesson_map:
                                    break

                                covered.append(
                                    next_period.id
                                )

                                if len(covered) >= duration - 1:
                                    break

                        colspan += len(covered)

                        skip_period_ids.update(covered)

                        cells.append({
                            "period": period,
                            "lesson": lesson,
                            "colspan": colspan,
                        })

                    else:

                        cells.append({
                            "period": period,
                            "lesson": None,
                            "colspan": 1,
                        })

                master_rows.append({
                    "day": day,
                    "class_group": row["class_group"],
                    "cells": cells,
                    "first_day_row": index == 0,
                    "day_rowspan": len(day_rows),
                })

        return master_rows

    # ---------------------------------------------------------
    # CURRENT PREVIEW
    # ---------------------------------------------------------

    preview_lessons = all_lessons

    if preview_type == "class" and selected_class:

        preview_lessons = all_lessons.filter(
            class_group=selected_class
        )

    elif preview_type == "teacher" and selected_teacher:

        preview_lessons = all_lessons.filter(
            teacher=selected_teacher
        )

    master_rows = build_master_rows(preview_lessons)

    # ---------------------------------------------------------
    # ALL TEACHERS
    # ---------------------------------------------------------

    teacher_previews = []

    if selected_term and preview_type == "all_teachers":

        teacher_ids = (
            all_lessons
            .exclude(teacher_id__isnull=True)
            .values_list(
                "teacher_id",
                flat=True,
            )
            .distinct()
        )

        teachers_with_lessons = teachers.filter(
            id__in=teacher_ids
        )

        for teacher in teachers_with_lessons:

            teacher_lessons = all_lessons.filter(
                teacher=teacher
            )

            teacher_previews.append({
                "teacher": teacher,
                "master_rows": build_master_rows(
                    teacher_lessons
                ),
            })

    return render(
        request,
        "timetable/print_preview.html",
        {
            "terms": terms,
            "academic_years": academic_years,

            "selected_year": selected_year,
            "selected_term_name": selected_term_name,
            "selected_term": selected_term,

            "preview_type": preview_type,

            "classes": classes,
            "teachers": teachers,

            "selected_class": selected_class,
            "selected_teacher": selected_teacher,

            "days": days,
            "periods": periods,

            "lessons": preview_lessons,

            "master_rows": master_rows,

            "teacher_previews": teacher_previews,
        },
    )
def timetable_print_preview(request):
    from .models import (
        TimetableTerm,
        TimetableDay,
        TimetablePeriod,
        TimetableClass,
        TimetableTeacher,
        TimetableLesson,
    )

    selected_year = request.GET.get("year", "").strip()
    selected_term_name = request.GET.get("term", "").strip()
    preview_type = request.GET.get("type", "school").strip()

    selected_class_id = request.GET.get("class", "").strip()
    selected_teacher_id = request.GET.get("teacher", "").strip()

    valid_types = {
        "school",
        "class",
        "teacher",
        "all_teachers",
    }

    if preview_type not in valid_types:
        preview_type = "school"

    terms = (
        TimetableTerm.objects
        .filter(active=True)
        .order_by("-academic_year", "term_name", "-id")
    )

    academic_years = list(
        TimetableTerm.objects
        .filter(active=True)
        .values_list("academic_year", flat=True)
        .distinct()
        .order_by("-academic_year")
    )

    generated_result = request.session.get(
        "timetable_generation_result"
    )

    generated_term_text = ""
    if generated_result:
        generated_term_text = str(
            generated_result.get("term", "")
        ).strip()

    selected_term = None

    # Explicit URL selection always wins.
    if selected_year and selected_term_name:
        selected_term = (
            TimetableTerm.objects
            .filter(
                active=True,
                academic_year=selected_year,
                term_name=selected_term_name,
            )
            .order_by("-id")
            .first()
        )

    # Prefer the term recorded by the generator.
    if not selected_term and generated_term_text:
        for candidate in terms:
            if str(candidate) == generated_term_text:
                selected_term = candidate
                break

    # If no generator result is available, use a term that
    # actually contains generated lessons.
    if not selected_term:
        selected_term = (
            TimetableTerm.objects
            .filter(active=True, lessons__isnull=False)
            .distinct()
            .order_by("-academic_year", "-id")
            .first()
        )

    if not selected_term and terms.exists():
        selected_term = terms.first()

    if selected_term:
        selected_year = str(selected_term.academic_year)
        selected_term_name = str(selected_term.term_name)

    classes = (
        TimetableClass.objects
        .filter(active=True)
        .order_by("level", "name", "stream")
    )

    teachers = (
        TimetableTeacher.objects
        .filter(active=True)
        .order_by("name")
    )

    days = list(
        TimetableDay.objects
        .filter(active=True)
        .order_by("order")
    )

    periods = list(
        TimetablePeriod.objects
        .filter(active=True)
        .order_by("order")
    )

    selected_class = None
    selected_teacher = None

    if selected_class_id.isdigit():
        selected_class = classes.filter(
            pk=int(selected_class_id)
        ).first()

    if selected_teacher_id.isdigit():
        selected_teacher = teachers.filter(
            pk=int(selected_teacher_id)
        ).first()

    def build_master_rows(base_lessons):
        """
        Build the exact same master_rows structure used
        by the Workspace timetable.
        """

        grouped = {}

        for lesson in base_lessons:
            key = (lesson.day_id, lesson.class_group_id)

            if key not in grouped:
                grouped[key] = {
                    "day": lesson.day,
                    "class_group": lesson.class_group,
                    "lessons": {},
                }

            grouped[key]["lessons"][lesson.period_id] = lesson

        master_rows = []

        for day in days:

            day_rows = [
                row for key, row in grouped.items()
                if key[0] == day.id
            ]

            day_rows.sort(
                key=lambda row: (
                    row["class_group"].name,
                    row["class_group"].stream,
                )
            )

            # Exactly as Workspace: always display every
            # active school day.
            if not day_rows:
                empty_cells = []

                for period in periods:
                    empty_cells.append({
                        "period": period,
                        "lesson": None,
                        "colspan": 1,
                    })

                master_rows.append({
                    "day": day,
                    "class_group": None,
                    "cells": empty_cells,
                    "first_day_row": True,
                    "day_rowspan": 1,
                    "empty_day": True,
                })

                continue

            for index, row in enumerate(day_rows):

                lesson_map = row["lessons"]
                cells = []
                skip_period_ids = set()

                for i, period in enumerate(periods):

                    if period.id in skip_period_ids:
                        continue

                    lesson = lesson_map.get(period.id)

                    if lesson:

                        duration = max(
                            1,
                            int(lesson.duration_periods or 1)
                        )

                        colspan = 1
                        covered = []

                        if duration > 1:
                            for next_period in periods[i + 1:]:

                                if (
                                    next_period.is_break
                                    or next_period.is_lunch
                                    or next_period.is_activity
                                ):
                                    break

                                if next_period.id in lesson_map:
                                    break

                                covered.append(next_period.id)

                                if len(covered) >= duration - 1:
                                    break

                            colspan += len(covered)
                            skip_period_ids.update(covered)

                        cells.append({
                            "period": period,
                            "lesson": lesson,
                            "colspan": colspan,
                        })

                    else:
                        cells.append({
                            "period": period,
                            "lesson": None,
                            "colspan": 1,
                        })

                master_rows.append({
                    "day": day,
                    "class_group": row["class_group"],
                    "cells": cells,
                    "first_day_row": index == 0,
                    "day_rowspan": len(day_rows),
                })

        return master_rows

    def get_lessons():
        if not selected_term:
            return TimetableLesson.objects.none()

        return (
            TimetableLesson.objects
            .filter(term=selected_term)
            .select_related(
                "class_group",
                "subject",
                "teacher",
                "room",
                "day",
                "period",
            )
            .order_by(
                "day__order",
                "class_group__name",
                "class_group__stream",
                "period__order",
            )
        )

    base_lessons = get_lessons()

    if preview_type == "class" and selected_class:
        base_lessons = base_lessons.filter(
            class_group=selected_class
        )

    elif preview_type == "teacher" and selected_teacher:
        base_lessons = base_lessons.filter(
            teacher=selected_teacher
        )

    master_rows = build_master_rows(base_lessons)

    teacher_previews = []

    if selected_term and preview_type == "all_teachers":

        teacher_ids = (
            TimetableLesson.objects
            .filter(term=selected_term)
            .values_list("teacher_id", flat=True)
            .distinct()
        )

        teachers_with_lessons = teachers.filter(
            id__in=teacher_ids
        )

        for teacher in teachers_with_lessons:

            teacher_lessons = (
                TimetableLesson.objects
                .filter(
                    term=selected_term,
                    teacher=teacher,
                )
                .select_related(
                    "class_group",
                    "subject",
                    "room",
                    "day",
                    "period",
                )
                .order_by(
                    "day__order",
                    "class_group__name",
                    "class_group__stream",
                    "period__order",
                )
            )

            teacher_previews.append({
                "teacher": teacher,
                "master_rows": build_master_rows(
                    teacher_lessons
                ),
            })

    return render(
        request,
        "timetable/print_preview.html",
        {
            "terms": terms,
            "academic_years": academic_years,
            "selected_year": selected_year,
            "selected_term_name": selected_term_name,
            "selected_term": selected_term,

            "preview_type": preview_type,

            "classes": classes,
            "teachers": teachers,

            "selected_class": selected_class,
            "selected_teacher": selected_teacher,

            "days": days,
            "periods": periods,

            "master_rows": master_rows,
            "teacher_previews": teacher_previews,

            "lessons": base_lessons,
        },
    )

@login_required
def timetable_print_preview(request):
    # PRINT PREVIEW PERMISSION
    denied = _timetable_permission_redirect(
        request,
        "view_timetablelesson",
    )
    if denied:
        return denied

    # =========================================================
    # PRINT PREVIEW
    # Uses the same master grid structure as Workspace.
    # =========================================================

    selected_year = request.GET.get("year", "").strip()
    selected_term_name = request.GET.get("term", "").strip()
    preview_type = request.GET.get("type", "school").strip()

    selected_class_id = request.GET.get("class", "").strip()
    selected_teacher_id = request.GET.get("teacher", "").strip()

    if preview_type not in {
        "school",
        "class",
        "teacher",
        "all_teachers",
    }:
        preview_type = "school"

    # ---------------------------------------------------------
    # TERMS
    # ---------------------------------------------------------
    terms = (
        TimetableTerm.objects
        .filter(active=True)
        .order_by("-academic_year", "term_name", "-id")
    )

    academic_years = list(
        TimetableTerm.objects
        .filter(active=True)
        .values_list("academic_year", flat=True)
        .distinct()
        .order_by("-academic_year")
    )

    # ---------------------------------------------------------
    # SELECT TERM
    # Explicit URL selection has priority.
    # ---------------------------------------------------------
    selected_term = None

    if selected_year and selected_term_name:
        selected_term = (
            TimetableTerm.objects
            .filter(
                active=True,
                academic_year=selected_year,
                term_name=selected_term_name,
            )
            .order_by("-id")
            .first()
        )

    # Fallback to the generated term.
    if not selected_term:

        generated_result = request.session.get(
            "timetable_generation_result"
        )

        generated_term_text = ""

        if generated_result:
            generated_term_text = str(
                generated_result.get("term", "")
            ).strip()

        if generated_term_text:
            for candidate in terms:
                if str(candidate) == generated_term_text:
                    selected_term = candidate
                    break

    # Final fallback.
    if not selected_term:
        selected_term = terms.first()

    if selected_term:
        selected_year = str(selected_term.academic_year)
        selected_term_name = str(selected_term.term_name)

    # ---------------------------------------------------------
    # DAYS / PERIODS
    # ---------------------------------------------------------
    days = list(
        TimetableDay.objects
        .filter(active=True)
        .order_by("order", "id")
    )

    periods = list(
        TimetablePeriod.objects
        .filter(active=True)
        .order_by("order", "id")
    )

    # ---------------------------------------------------------
    # CLASSES / TEACHERS
    # ---------------------------------------------------------
    classes = (
        TimetableClass.objects
        .filter(active=True)
        .order_by("level", "name", "stream")
    )

    teachers = (
        TimetableTeacher.objects
        .filter(active=True)
        .order_by("name")
    )

    selected_class = None
    selected_teacher = None

    if selected_class_id.isdigit():
        selected_class = classes.filter(
            pk=int(selected_class_id)
        ).first()

    if selected_teacher_id.isdigit():
        selected_teacher = teachers.filter(
            pk=int(selected_teacher_id)
        ).first()

    # ---------------------------------------------------------
    # LOAD ALL LESSONS FOR SELECTED TERM
    # ---------------------------------------------------------
    all_lessons = []

    if selected_term:

        all_lessons = list(
            TimetableLesson.objects
            .filter(term_id=selected_term.id)
            .select_related(
                "class_group",
                "subject",
                "teacher",
                "room",
                "day",
                "period",
            )
            .order_by(
                "day__order",
                "class_group__name",
                "class_group__stream",
                "period__order",
            )
        )

    # ---------------------------------------------------------
    # FILTER LESSONS
    # ---------------------------------------------------------
    lessons = all_lessons

    if preview_type == "class" and selected_class:

        lessons = [
            lesson
            for lesson in all_lessons
            if lesson.class_group_id == selected_class.id
        ]

    elif preview_type == "teacher" and selected_teacher:

        lessons = [
            lesson
            for lesson in all_lessons
            if lesson.teacher_id == selected_teacher.id
        ]

    # ---------------------------------------------------------
    # MASTER GRID BUILDER
    # Exact Workspace-style row/cell structure.
    # ---------------------------------------------------------
    def build_master_rows(lesson_list, teacher_mode=False):

        grouped = {}

        for lesson in lesson_list:

            if teacher_mode:
                key = (lesson.day_id, None)
            else:
                key = (
                    lesson.day_id,
                    lesson.class_group_id,
                )

            if key not in grouped:
                grouped[key] = {
                    "day": lesson.day,
                    "class_group": (
                        None
                        if teacher_mode
                        else lesson.class_group
                    ),
                    "lessons": {},
                }

            grouped[key]["lessons"][lesson.period_id] = lesson

        master_rows = []

        for day in days:

            day_rows = [
                row
                for key, row in grouped.items()
                if key[0] == day.id
            ]

            if not teacher_mode:
                day_rows.sort(
                    key=lambda row: (
                        row["class_group"].name,
                        row["class_group"].stream,
                    )
                )

            # Keep every active school day visible.
            if not day_rows:

                empty_cells = []

                for period in periods:
                    empty_cells.append({
                        "period": period,
                        "lesson": None,
                        "colspan": 1,
                    })

                master_rows.append({
                    "day": day,
                    "class_group": None,
                    "cells": empty_cells,
                    "first_day_row": True,
                    "day_rowspan": 1,
                    "empty_day": True,
                })

                continue

            for index, row in enumerate(day_rows):

                lesson_map = row["lessons"]
                cells = []
                skip_period_ids = set()

                for i, period in enumerate(periods):

                    if period.id in skip_period_ids:
                        continue

                    lesson = lesson_map.get(period.id)

                    if lesson:

                        duration = max(
                            1,
                            int(lesson.duration_periods or 1)
                        )

                        colspan = 1
                        covered = []

                        if duration > 1:

                            for next_period in periods[i + 1:]:

                                if (
                                    next_period.is_break
                                    or next_period.is_lunch
                                    or next_period.is_activity
                                ):
                                    break

                                if next_period.id in lesson_map:
                                    break

                                covered.append(next_period.id)

                                if len(covered) >= duration - 1:
                                    break

                        colspan += len(covered)
                        skip_period_ids.update(covered)

                        cells.append({
                            "period": period,
                            "lesson": lesson,
                            "colspan": colspan,
                        })

                    else:

                        cells.append({
                            "period": period,
                            "lesson": None,
                            "colspan": 1,
                        })

                master_rows.append({
                    "day": day,
                    "class_group": row["class_group"],
                    "cells": cells,
                    "first_day_row": index == 0,
                    "day_rowspan": len(day_rows),
                })

        return master_rows

    # ---------------------------------------------------------
    # MAIN GRID
    # ---------------------------------------------------------
    master_rows = build_master_rows(
        lessons,
        teacher_mode=(preview_type == "teacher"),
    )

    # ---------------------------------------------------------
    # ALL TEACHERS
    # Each teacher receives its own Workspace-style grid.
    # ---------------------------------------------------------
    teacher_previews = []

    if preview_type == "all_teachers":

        teacher_ids = sorted({
            lesson.teacher_id
            for lesson in all_lessons
            if lesson.teacher_id
        })

        for teacher in teachers:

            if teacher.id not in teacher_ids:
                continue

            teacher_lessons = [
                lesson
                for lesson in all_lessons
                if lesson.teacher_id == teacher.id
            ]

            teacher_previews.append({
                "teacher": teacher,
                "lessons": teacher_lessons,
                "master_rows": build_master_rows(
                    teacher_lessons,
                    teacher_mode=True,
                ),
            })

    # ---------------------------------------------------------
    # CONTEXT
    # ---------------------------------------------------------
    context = {
        "terms": terms,
        "academic_years": academic_years,

        "selected_year": selected_year,
        "selected_term_name": selected_term_name,
        "selected_term": selected_term,

        "preview_type": preview_type,

        "classes": classes,
        "teachers": teachers,

        "selected_class": selected_class,
        "selected_teacher": selected_teacher,

        "lessons": lessons,
        "master_rows": master_rows,
        "teacher_previews": teacher_previews,

        "days": days,
        "periods": periods,

        "generation_result": request.session.get(
            "timetable_generation_result"
        ),
    }

    return render(
        request,
        "timetable/print_preview.html",
        context,
    )







































