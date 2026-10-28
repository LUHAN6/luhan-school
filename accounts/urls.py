from django.urls import path
from . import views
from . import hostel_portal
from . import staff_wizard



from .admin_password_reset_view import admin_password_reset
app_name = "accounts"


urlpatterns = [
    # ========================================================
    # FRESH ADD STAFF WIZARD
    # ========================================================

    path(
        "staff/new/",
        staff_wizard.start,
        name="fresh_staff_start"
    ),

    path(
        "staff/new/teaching/",
        staff_wizard.teaching_details,
        name="fresh_staff_teaching"
    ),

    path(
        "staff/new/support/",
        staff_wizard.support_details,
        name="fresh_staff_support"
    ),

    path(
        "staff/new/role/",
        staff_wizard.role,
        name="fresh_staff_role"
    ),

    path(
        "staff/new/subjects/",
        staff_wizard.subjects,
        name="fresh_staff_subjects"
    ),

    path(
        "staff/new/classes/",
        staff_wizard.classes,
        name="fresh_staff_classes"
    ),

    path(
        "staff/new/success/",
        staff_wizard.success,
        name="fresh_staff_success"
    ),
    # AUTHENTICATION
    path("admin-login/", views.admin_login, name="admin_login"),
    path("staff-login/", views.staff_login, name="staff_login"),
    path("student-login/", views.student_login, name="student_login"),
    path("parent-login/", views.parent_login, name="parent_login"),

    path("staff-type-selection/", views.staff_type_selection, name="staff_type_selection"),
    # STAFF LOGIN SELECTION
    path("staff-selection/", views.staff_selection, name="staff_selection"),
    path("teaching-staff-details/", views.teaching_staff_details, name="teaching_staff_details"),
    path("support-staff-details/", views.support_staff_details, name="support_staff_details"),
    path("staff-role-assignment/", views.staff_role_assignment, name="staff_role_assignment"),
        path("staff-class-assignment/",
         views.staff_class_assignment,
         name="staff_class_assignment"),    path("staff-subject-assignment/", views.staff_subject_assignment, name="staff_subject_assignment"),
    path("staff-creation-success/", views.staff_creation_success, name="staff_creation_success"),
    path("teaching-staff-login/", views.teaching_staff_login, name="teaching_staff_login"),
    path("support-staff-login/", views.support_staff_login, name="support_staff_login"),


    path("profile-settings/", views.profile_settings, name="profile_settings"),

    # ========================================================
    # AUTHENTICATION
    # ========================================================

    path(
        "login/",
        views.login_view,
        name="login",
    ),

    path(
        "logout/",
        views.logout_view,
        name="logout",
    ),


    # ========================================================
    # ADMIN PASSWORD RESET
    path(
        "admin-password-reset/",
        admin_password_reset,
        name="admin_password_reset",
    ),
    # DASHBOARDS
    # ========================================================

    path(
        "admin-dashboard/",
        views.admin_dashboard,
        name="admin_dashboard",
    ),

    path(
        "staff-dashboard/",
        views.staff_dashboard,
        name="staff_dashboard",
    ),

    path(
        "my-timetable/",
        views.staff_my_timetable,
        name="staff_my_timetable",
    ),


    # ========================================================
    # ========================================================
    # STAFF ACADEMIC PORTAL
    # ========================================================

    path(
        "academic-portal/",
        views.staff_academic_portal,
        name="staff_academic_portal",
    ),

    path(
        "academic-portal/class/",
        views.staff_academic_class,
        name="staff_academic_class",
    ),

    # STAFF MANAGEMENT
    # ========================================================

    path(
        "staff-management/",
        views.staff_management,
        name="staff_management",
    ),

    path(
        "staff/add/",
        views.add_staff,
        name="add_staff",
    ),

    path(
        "staff-role-management/",
        views.staff_role_management,
        name="staff_role_management",
    ),

    path(
        "staff/<int:user_id>/",
        views.view_staff,
        name="view_staff",
    ),

    path(
        "staff/<int:user_id>/edit/",
        views.edit_staff,
        name="edit_staff",
    ),

    path(
        "staff/<int:user_id>/delete/",
        views.delete_staff,
        name="delete_staff",
    ),

    path(
        "staff/<int:user_id>/toggle-status/",
        views.toggle_staff_status,
        name="toggle_staff_status",
    ),


    # ========================================================
    # DEPARTMENT MANAGEMENT
    # ========================================================

    path(
        "department-management/",
        views.department_management,
        name="department_management",
    ),

    path(
        "departments/add/",
        views.add_department,
        name="add_department",
    ),

    path(
        "departments/<int:department_id>/edit/",
        views.edit_department,
        name="edit_department",
    ),

    path(
        "departments/<int:department_id>/toggle-status/",
        views.toggle_department_status,
        name="toggle_department_status",
    ),


    # ========================================================
    # ROLE MANAGEMENT
    # ========================================================

    path(
        "role-management/",
        views.role_management,
        name="role_management",
    ),

    path(
        "roles/add/",
        views.add_role,
        name="add_role",
    ),

    path(
        "roles/<int:role_id>/edit/",
        views.edit_role,
        name="edit_role",
    ),

    path(
        "roles/<int:role_id>/toggle-status/",
        views.toggle_role_status,
        name="toggle_role_status",
    ),


    # ========================================================
    # SCHOOL BRANDING
    # ========================================================

    path(
        "branding-management/",
        views.branding_management,
        name="branding_management",
    ),


    # ========================================================
    # STUDENT / PARENT DASHBOARDS
    # ========================================================

    path(
        "student-dashboard/",
        views.student_dashboard,
        name="student_dashboard",
    ),

    path(
        "parent-dashboard/",
        views.parent_dashboard,
        name="parent_dashboard",
    ),

    path(
        "parent-results/<int:student_id>/",
        views.parent_academic_results,
        name="parent_academic_results",
    ),


    path(
        "parent-fees/<int:student_id>/",
        views.parent_fees,
        name="parent_fees",
    ),

    path(
        "parent-timetable/<int:student_id>/",
        views.parent_timetable,
        name="parent_timetable",
    ),

    path(
        "parent-assignments/<int:student_id>/",
        views.parent_assignments,
        name="parent_assignments",
    ),

    path(
        "parent-learning/<int:student_id>/",
        views.parent_learning,
        name="parent_learning",
    ),

    path(
        "parent-attendance/<int:student_id>/",
        views.parent_attendance,
        name="parent_attendance",
    ),

    path(
        "parent-announcements/",
        views.parent_announcements,
        name="parent_announcements",
    ),

    path(
        "parent-library/<int:student_id>/",
        views.parent_library,
        name="parent_library",
    ),

    path(
        "parent-receipt/<int:payment_id>/",
        views.parent_print_receipt,
        name="parent_print_receipt",
    ),


    # ========================================================
    # STUDENT PORTAL
    # ========================================================

    path(
        "student-results/",
        views.student_results,
        name="student_results",
    ),

    path(
        "student-profile/",
        views.student_profile,
        name="student_profile",
    ),

    path(
        "student-library/",
        views.student_library,
        name="student_library",
    ),

    path(
        "student-announcements/",
        views.student_announcements,
        name="student_announcements",
    ),

    path(
        "student-assignments/",
        views.student_assignments,
        name="student_assignments",
    ),

    path(
        "student-learning/",
        views.student_learning,
        name="student_learning",
    ),

    path(
        "student-attendance/",
        views.student_attendance,
        name="student_attendance",
    ),

    path(
        "student-fees/",
        views.student_fees,
        name="student_fees",
    ),

    path(
        "student-timetable/",
        views.student_timetable,
        name="student_timetable",
    ),

    path(
        "student-receipt/<int:payment_id>/",
        views.student_print_receipt,
        name="student_print_receipt",
    ),


    # ========================================================
    # HOSTEL PORTAL
    # ========================================================

    path(
        "student-hostel/",
        hostel_portal.student_hostel,
        name="student_hostel",
    ),

    path(
        "student-hostel/apply/",
        hostel_portal.student_hostel_apply,
        name="student_hostel_apply",
    ),

    path(
        "student-hostel/report-incident/",
        hostel_portal.student_hostel_incident,
        name="student_hostel_incident",
    ),

    path(
        "parent-hostel/",
        hostel_portal.parent_hostel,
        name="parent_hostel",
    ),

    path(
        "parent-hostel/<int:student_id>/apply/",
        hostel_portal.parent_hostel_apply,
        name="parent_hostel_apply",
    ),

    path(
        "parent-hostel/<int:student_id>/report-incident/",
        hostel_portal.parent_hostel_incident,
        name="parent_hostel_incident",
    ),
    path("staff/published-timetable/",
        views.staff_published_timetable,
        name="staff_published_timetable",
    ),]












