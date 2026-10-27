from django.urls import path
from . import views


app_name = "hr_payroll"


urlpatterns = [

    # Dashboard
    path(
        "",
        views.hr_payroll_dashboard,
        name="dashboard",
    ),

    # Employees
    path(
        "employees/",
        views.employee_list,
        name="employee_list",
    ),

    path(
        "employees/add/",
        views.employee_add,
        name="employee_add",
    ),

    path(
        "employees/<int:pk>/",
        views.employee_detail,
        name="employee_detail",
    ),

    path(
        "employees/<int:pk>/edit/",
        views.employee_edit,
        name="employee_edit",
    ),

    path(
        "employees/<int:pk>/deactivate/",
        views.employee_deactivate,
        name="employee_deactivate",
    ),

    # Departments
    path(
        "departments/",
        views.department_list,
        name="department_list",
    ),

    path(
        "departments/add/",
        views.department_add,
        name="department_add",
    ),

    path(
        "departments/<int:pk>/edit/",
        views.department_edit,
        name="department_edit",
    ),

    # Positions
    path(
        "positions/",
        views.position_list,
        name="position_list",
    ),

    path(
        "positions/add/",
        views.position_add,
        name="position_add",
    ),

    path(
        "positions/<int:pk>/edit/",
        views.position_edit,
        name="position_edit",
    ),

    # Attendance
    path(
        "attendance/",
        views.attendance_list,
        name="attendance_list",
    ),

    path(
        "attendance/add/",
        views.attendance_add,
        name="attendance_add",
    ),

    path(
        "attendance/<int:pk>/edit/",
        views.attendance_edit,
        name="attendance_edit",
    ),

    path(
        "attendance/<int:pk>/delete/",
        views.attendance_delete,
        name="attendance_delete",
    ),

    # Leave Types
    path(
        "leave/types/",
        views.leave_type_list,
        name="leave_type_list",
    ),

    path(
        "leave/types/add/",
        views.leave_type_add,
        name="leave_type_add",
    ),

    # Leave Applications
    path(
        "leave/",
        views.leave_list,
        name="leave_list",
    ),

    path(
        "leave/add/",
        views.leave_add,
        name="leave_add",
    ),

    path(
        "leave/<int:pk>/approve/",
        views.leave_approve,
        name="leave_approve",
    ),

    path(
        "leave/<int:pk>/reject/",
        views.leave_reject,
        name="leave_reject",
    ),

    path(
        "leave/<int:pk>/cancel/",
        views.leave_cancel,
        name="leave_cancel",
    ),

    # Documents
    path(
        "documents/",
        views.document_list,
        name="document_list",
    ),

    path(
        "documents/add/",
        views.document_add,
        name="document_add",
    ),

    path(
        "documents/<int:pk>/delete/",
        views.document_delete,
        name="document_delete",
    ),

    # Employee Exits
    path(
        "exits/",
        views.employee_exit_list,
        name="employee_exit_list",
    ),

    path(
        "exits/add/",
        views.employee_exit_add,
        name="employee_exit_add",
    ),

    # Allowance Types
    path(
        "allowance-types/",
        views.allowance_type_list,
        name="allowance_type_list",
    ),

    path(
        "allowance-types/add/",
        views.allowance_type_add,
        name="allowance_type_add",
    ),

    # Allowances
    path(
        "allowances/",
        views.allowance_list,
        name="allowance_list",
    ),

    path(
        "allowances/add/",
        views.allowance_add,
        name="allowance_add",
    ),

    path(
        "allowances/<int:pk>/edit/",
        views.allowance_edit,
        name="allowance_edit",
    ),

    path(
        "allowances/<int:pk>/deactivate/",
        views.allowance_deactivate,
        name="allowance_deactivate",
    ),
    path(
        "statutory-deductions/<str:category>/<int:pk>/toggle/",
        views.statutory_deduction_toggle,
        name="statutory_deduction_toggle",
    ),
path(
        "statutory-deductions/",
        views.statutory_deductions,
        name="statutory_deductions",
    ),
    # Statutory Payroll Rules
    path(
        "paye-tax-bands/",
        views.paye_tax_band_list,
        name="paye_tax_band_list",
    ),
    path(
        "paye-tax-bands/add/",
        views.paye_tax_band_add,
        name="paye_tax_band_add",
    ),
    path(
        "paye-tax-bands/<int:pk>/edit/",
        views.paye_tax_band_edit,
        name="paye_tax_band_edit",
    ),
    path(
        "paye-reliefs/",
        views.paye_relief_list,
        name="paye_relief_list",
    ),
    path(
        "paye-reliefs/add/",
        views.paye_relief_add,
        name="paye_relief_add",
    ),
    path(
        "paye-reliefs/<int:pk>/edit/",
        views.paye_relief_edit,
        name="paye_relief_edit",
    ),
    path(
        "nssf-rules/",
        views.nssf_rule_list,
        name="nssf_rule_list",
    ),
    path(
        "nssf-rules/add/",
        views.nssf_rule_add,
        name="nssf_rule_add",
    ),
    path(
        "nssf-rules/<int:pk>/edit/",
        views.nssf_rule_edit,
        name="nssf_rule_edit",
    ),

    # Deduction Types
    path(
        "deduction-types/",
        views.deduction_type_list,
        name="deduction_type_list",
    ),

    path(
        "deduction-types/add/",
        views.deduction_type_add,
        name="deduction_type_add",
    ),
    path(
        "deduction-types/<int:pk>/edit/",
        views.deduction_type_edit,
        name="deduction_type_edit",
    ),
    path(
        "deduction-types/<int:pk>/delete/",
        views.deduction_type_delete,
        name="deduction_type_delete",
    ),

    # Deductions
path(
        "deductions/add/",
        views.deduction_add,
        name="deduction_add",
    ),

    path(
        "deductions/<int:pk>/edit/",
        views.deduction_edit,
        name="deduction_edit",
    ),

    path(
        "deductions/<int:pk>/deactivate/",
        views.deduction_deactivate,
        name="deduction_deactivate",
    ),

    # Loans
    path(
        "loans/",
        views.loan_list,
        name="loan_list",
    ),

    path(
        "loans/add/",
        views.loan_add,
        name="loan_add",
    ),

    path(
        "loans/<int:pk>/edit/",
        views.loan_edit,
        name="loan_edit",
    ),

    path(
        "loans/<int:pk>/repayment/",
        views.loan_repayment,
        name="loan_repayment",
    ),

    # Payroll
    path(
        "payroll/",
        views.payroll_list,
        name="payroll_list",
    ),

    path(
        "payroll/periods/add/",
        views.payroll_period_add,
        name="payroll_period_add",
    ),
    path(
        "payroll/periods/<int:pk>/delete/",
        views.payroll_period_delete,
        name="payroll_period_delete",
    ),

    path(
        "payroll/periods/<int:pk>/process/",
        views.payroll_process,
        name="payroll_process",
    ),

    path(
        "payroll/periods/<int:pk>/finalize/",
        views.finalize_payroll,
        name="finalize_payroll",
    ),

    # ========================================================
    # STAFF SELF-SERVICE
    # ========================================================

    path(
        "staff/attendance/",
        views.staff_attendance,
        name="staff_attendance",
    ),

    path(
        "staff/leave/",
        views.staff_leave_list,
        name="staff_leave_list",
    ),

    path(
        "staff/leave/apply/",
        views.staff_leave_apply,
        name="staff_leave_apply",
    ),

    path(
        "staff/leave/<int:pk>/cancel/",
        views.staff_leave_cancel,
        name="staff_leave_cancel",
    ),

    path(
        "staff/loans/",
        views.staff_loan_list,
        name="staff_loan_list",
    ),

    path(
        "staff/documents/",
        views.staff_document_list,
        name="staff_document_list",
    ),

    path(
        "staff/documents/<int:pk>/download/",
        views.staff_document_download,
        name="staff_document_download",
    ),

    # Staff Self-Service Payslips

    path(
        "staff/payslips/",
        views.staff_payslip_list,
        name="staff_payslip_list",
    ),

    path(
        "staff/payslips/<int:pk>/",
        views.staff_payslip_view,
        name="staff_payslip_view",
    ),

    path(
        "staff/payslips/<int:pk>/print/",
        views.staff_payslip_print,
        name="staff_payslip_print",
    ),

    path(
        "staff/payslips/<int:pk>/pdf/",
        views.staff_payslip_pdf,
        name="staff_payslip_pdf",
    ),

    # Payslips
    path(
        "payslips/",
        views.payslip_list,
        name="payslip_list",
    ),

    path(
        "payslips/generate/<int:payroll_record_id>/",
        views.payslip_generate,
        name="payslip_generate",
    ),
    path(
        "payslips/generate-all/<int:payroll_period_id>/",
        views.payslip_generate_all,
        name="payslip_generate_all",
    ),

    path(
        "payslips/<int:pk>/",
        views.payslip_view,
        name="payslip_view",
    ),

    path(
        "payslips/<int:pk>/edit/",
        views.payslip_edit,
        name="payslip_edit",
    ),

    path(
        "payslips/<int:pk>/delete/",
        views.payslip_delete,
        name="payslip_delete",
    ),

    path(
        "payslips/<int:pk>/print/",
        views.payslip_print,
        name="payslip_print",
    ),

    path(
        "payslips/<int:pk>/mark-sent/",
        views.payslip_mark_sent,
        name="payslip_mark_sent",
    ),

    # Appraisals
    path(
        "appraisals/",
        views.appraisal_list,
        name="appraisal_list",
    ),

    path(
        "appraisals/add/",
        views.appraisal_add,
        name="appraisal_add",
    ),

    path(
        "appraisals/<int:pk>/edit/",
        views.appraisal_edit,
        name="appraisal_edit",
    ),

    path(
        "appraisals/<int:pk>/status/<str:status>/",
        views.appraisal_status,
        name="appraisal_status",
    ),

    # Reports
    path(
        "reports/",
        views.hr_reports,
        name="hr_reports",
    ),

    # =========================================================
    # STAFF LOAN APPLICATIONS
    # =========================================================
    path(
        "staff/loans/apply/",
        views.staff_loan_apply,
        name="staff_loan_apply",
    ),

    path(
        "staff/loans/application/<int:pk>/",
        views.staff_loan_application_detail,
        name="staff_loan_application_detail",
    ),

    # =========================================================
    # ADMIN LOAN APPLICATIONS
    # =========================================================
    path(
        "loans/applications/",
        views.loan_applications,
        name="loan_applications",
    ),

    path(
        "loans/applications/<int:pk>/",
        views.loan_application_detail,
        name="loan_application_detail",
    ),

    path(
        "loans/applications/<int:pk>/approve/",
        views.loan_application_approve,
        name="loan_application_approve",
    ),

    path(
        "loans/applications/<int:pk>/reject/",
        views.loan_application_reject,
        name="loan_application_reject",
    ),

    path(
        "loans/applications/<int:pk>/disburse/",
        views.loan_application_disburse,
        name="loan_application_disburse",
    ),

]
















