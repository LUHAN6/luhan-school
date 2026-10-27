from django.urls import path
from . import views

app_name = "discipline"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("cases/", views.case_list, name="case_list"),
    path("cases/report/", views.case_create, name="case_create"),
    path("cases/<int:pk>/", views.case_detail, name="case_detail"),
    path("cases/<int:pk>/edit/", views.case_update, name="case_update"),
    path("cases/<int:pk>/status/<str:status>/", views.case_status, name="case_status"),
    path("cases/<int:pk>/statements/add/", views.add_statement, name="add_statement"),
    path("cases/<int:pk>/meetings/add/", views.add_meeting, name="add_meeting"),
    path("cases/<int:pk>/decisions/add/", views.add_decision, name="add_decision"),
    path("cases/<int:pk>/actions/add/", views.add_action, name="add_action"),
    path("cases/<int:pk>/improvement-plan/add/", views.add_improvement_plan, name="add_improvement_plan"),
    path("cases/<int:pk>/respond/", views.submit_response, name="submit_response"),
    path("cases/<int:pk>/appeals/add/", views.submit_appeal, name="submit_appeal"),
    path("cases/<int:pk>/appeals/<int:appeal_pk>/review/", views.review_appeal, name="review_appeal"),
    path("my-cases/", views.my_cases, name="my_cases"),
    path("reports/", views.reports, name="reports"),
    path("cases/<int:pk>/audit/", views.audit_log, name="audit_log"),
    path("cases/<int:pk>/evidence/<int:report_pk>/download/", views.download_evidence, name="download_evidence"),
]
