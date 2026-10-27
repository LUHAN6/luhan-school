from django.urls import path
from . import views

app_name = "transport_pro"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("reports/", views.reports, name="reports"),
    path("parent/", views.parent_portal, name="parent_portal"),
    path("staff/employee-lookup/", views.transport_employee_lookup, name="employee_lookup"),
    path("learners/register/", views.learner_registration, name="learner_registration"),
    path("learners/lookup/", views.learner_lookup, name="learner_lookup"),
    path("learners/import/template.xlsx", views.learner_import_template, name="learner_import_template"),
    path("learners/import/", views.learner_bulk_import, name="learner_bulk_import"),
    path("<str:kind>/", views.object_list, name="list"),
    path("<str:kind>/add/", views.create_object, name="create"),
    path("<str:kind>/<int:pk>/edit/", views.edit_object, name="edit"),
    path("trips/<int:pk>/<str:action>/", views.trip_action, name="trip_action"),
    path("payments/<int:pk>/verify/", views.verify_payment, name="verify_payment"),
]
