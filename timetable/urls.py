
from django.urls import path
from . import views

app_name = "timetable"

urlpatterns = [
    path("teacher-page/", views.timetable_teacher_page, name="teacher_page"),
    path("subject-page/", views.timetable_subject_page, name="subject_page"),
    path("class-page/", views.timetable_class_page, name="class_page"),

    path("create/", views.timetable_creation_wizard, name="creation_wizard"),
    path("create/step/<int:step>/", views.timetable_creation_wizard, name="creation_wizard_step"),
    path("requirement-builder/", views.timetable_requirements_builder, name="requirements"),
    path("", views.dashboard, name="dashboard"),
    path("setup/", views.setup, name="setup"),

    path("classes/", views.classes, name="classes"),
    path("subjects/", views.subjects, name="subjects"),
    path("teachers/", views.teachers, name="teachers"),
    path("rooms/", views.rooms, name="rooms"),
    path("requirement-builder/", views.requirement_builder, name="requirement_builder"),
    path(
        "requirements/<int:pk>/edit/",
        views.timetable_requirement_edit,
        name="requirement_edit",
    ),
    path(
        "requirements/<int:pk>/delete/",
        views.timetable_requirement_delete,
        name="requirement_delete",
    ),
    path(
        "requirements/<int:pk>/toggle/",
        views.timetable_requirement_toggle,
        name="requirement_toggle",
    ),
    path("requirements/", views.timetable_requirements_builder, name="requirements"),
    path("availability/", views.availability, name="availability"),

    path("workspace/", views.workspace, name="workspace"),
    path(
        "generation-control/",
        views.generation_control,
        name="generation_control",
    ),
    path("generate/", views.generate_timetable, name="generate"),
    path("publish/", views.publish_timetable, name="publish"),
    path("print-preview/", views.timetable_print_preview, name="print_preview"),
    path("clear/", views.clear_generated_timetable, name="clear"),
    path("conflicts/", views.conflicts, name="conflicts"),
    path(
        "smart-conflicts/",
        views.timetable_conflicts_page,
        name="smart_conflicts",
    ),


    # CRUD CONTROL CENTRE
    path(
        "control-centre/",
        views.control_centre,
        name="control_centre",
    ),

    path(
        "manage/<str:model_key>/",
        views.crud_list,
        name="crud_list",
    ),

    path(
        "manage/<str:model_key>/add/",
        views.crud_create,
        name="crud_create",
    ),

    path(
        "manage/<str:model_key>/<int:pk>/edit/",
        views.crud_edit,
        name="crud_edit",
    ),

    path(
        "manage/<str:model_key>/<int:pk>/delete/",
        views.crud_delete,
        name="crud_delete",
    ),

    path(
        "lesson/<int:pk>/edit/",
        views.timetable_lesson_edit,
        name="timetable_lesson_edit",
    ),
    path(
        "lesson/<int:pk>/lock/",
        views.timetable_lesson_lock,
        name="timetable_lesson_lock",
    ),
    path(
        "lesson/<int:pk>/delete/",
        views.timetable_lesson_delete,
        name="timetable_lesson_delete",
    ),
]

