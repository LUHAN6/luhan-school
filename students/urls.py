from django.urls import path
from . import views

urlpatterns = [
    path("transport-fee-quote/", views.transport_fee_quote, name="transport_fee_quote"),

    path("application-status/", views.application_status, name="application_status"),
    path("apply-online/", views.online_application_form, name="online_application_form"),
    path("online-applications/", views.online_applications, name="online_applications"),
    path("online-applications/<int:id>/", views.online_application_detail, name="online_application_detail"),
    path("online-applications/<int:application_id>/admit/", views.admit_online_application, name="admit_online_application"),
    path("online-applications/<int:id>/reject/", views.reject_online_application, name="reject_online_application"),

    path("", views.student_management, name="student_management"),
    path("dashboard/", views.student_management, name="student_management_dashboard"),

    path("add/", views.add_student, name="add_student"),
    path("list/", views.student_list, name="student_list"),
    path("print-class-lists/", views.print_class_lists, name="print_class_lists"),
    path("bulk-promotion/", views.bulk_promotion, name="bulk_promotion"),
    path(
        "view/<int:id>/promotion-history/",
        views.student_promotion_history,
        name="student_promotion_history"
    ),
    path("import/", views.import_students, name="import_students"),
    path("export/page/", views.export_students_page, name="export_students_page"),
    path("export/", views.export_students, name="export_students"),
    path("import/template/", views.student_import_template, name="student_import_template"),

    path("view/<int:id>/", views.student_profile, name="student_profile"),
    path("edit/<int:id>/", views.edit_student, name="edit_student"),
    path("delete/<int:id>/", views.delete_student, name="delete_student"),
]
