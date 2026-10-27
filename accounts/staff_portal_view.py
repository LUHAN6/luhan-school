from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Sum
from django.utils import timezone
from decimal import Decimal

from hr_payroll.models import (
    Employee,
    EmployeeAllowance,
    EmployeeDeduction,
    StaffLoan,
    PayrollRecord,
    Payslip,
    Attendance as HRAttendance,
    LeaveApplication,
)

from .models import UserProfile, SchoolBranding


@login_required
def staff_dashboard(request):
    """Secure employee self-service dashboard."""

    profile = get_object_or_404(
        UserProfile.objects.select_related(
            "employee",
            "department",
            "employee__department",
            "employee__position",
        ),
        user=request.user,
    )

    employee = profile.employee

    if not employee:
        messages.error(
            request,
            "Your account is not linked to an employee record. "
            "Please contact the school administrator.",
        )
        return redirect("accounts:login")

    # ---------------------------------------------------------
    # ATTENDANCE
    # ---------------------------------------------------------

    attendance = (
        HRAttendance.objects
        .filter(employee=employee)
        .order_by("-date", "-id")
    )

    total_attendance = attendance.count()

    present_count = attendance.filter(status="PRESENT").count()
    absent_count = attendance.filter(status="ABSENT").count()
    late_count = attendance.filter(status="LATE").count()
    half_day_count = attendance.filter(status="HALF_DAY").count()
    leave_attendance_count = attendance.filter(status="LEAVE").count()
    off_day_count = attendance.filter(status="OFF").count()

    attendance_percentage = (
        round(
            (
                present_count
                + (half_day_count * Decimal("0.5"))
            )
            / total_attendance
            * 100,
            1,
        )
        if total_attendance
        else 0
    )

    # ---------------------------------------------------------
    # LEAVE
    # ---------------------------------------------------------

    leave_applications = (
        LeaveApplication.objects
        .filter(employee=employee)
        .select_related("leave_type")
        .order_by("-created_at", "-id")
    )

    pending_leave_count = leave_applications.filter(
        status="PENDING"
    ).count()

    approved_leave_count = leave_applications.filter(
        status="APPROVED"
    ).count()

    rejected_leave_count = leave_applications.filter(
        status="REJECTED"
    ).count()

    # ---------------------------------------------------------
    # ALLOWANCES
    # ---------------------------------------------------------

    allowances = (
        EmployeeAllowance.objects
        .filter(
            employee=employee,
            is_active=True,
        )
        .select_related("allowance_type")
        .order_by("allowance_type__name")
    )

    total_allowances = sum(
        (
            item.amount or Decimal("0.00")
            for item in allowances
        ),
        Decimal("0.00"),
    )

    # ---------------------------------------------------------
    # DEDUCTIONS
    # ---------------------------------------------------------

    deductions = (
        EmployeeDeduction.objects
        .filter(
            employee=employee,
            is_active=True,
        )
        .select_related("deduction_type")
        .order_by("deduction_type__name")
    )

    total_deductions = sum(
        (
            item.amount or Decimal("0.00")
            for item in deductions
        ),
        Decimal("0.00"),
    )

    # ---------------------------------------------------------
    # LOANS
    # ---------------------------------------------------------

    loans = (
        StaffLoan.objects
        .filter(employee=employee)
        .order_by("-created_at", "-id")
    )

    active_loans = loans.filter(status="ACTIVE")

    outstanding_loan_balance = sum(
        (
            (loan.principal_amount or Decimal("0.00"))
            - (loan.amount_paid or Decimal("0.00"))
            for loan in active_loans
        ),
        Decimal("0.00"),
    )

    outstanding_loan_balance = max(
        outstanding_loan_balance,
        Decimal("0.00"),
    )

    # ---------------------------------------------------------
    # PAYROLL
    # ---------------------------------------------------------

    payroll_records = (
        PayrollRecord.objects
        .filter(employee=employee)
        .select_related("payroll_period")
        .order_by(
            "-payroll_period__year",
            "-payroll_period__month",
            "-id",
        )
    )

    latest_payroll = payroll_records.first()

    # ---------------------------------------------------------
    # PAYSLIPS
    # ---------------------------------------------------------

    payslips = (
        Payslip.objects
        .filter(
            payroll_record__employee=employee
        )
        .select_related(
            "payroll_record",
            "payroll_record__payroll_period",
        )
        .order_by("-generated_at", "-id")
    )

    latest_payslip = payslips.first()

    # ---------------------------------------------------------
    # DOCUMENTS
    # ---------------------------------------------------------

    documents = (
        employee.documents
        .all()
        .order_by("-uploaded_at", "-id")
    )

    # ---------------------------------------------------------
    # PERFORMANCE
    # ---------------------------------------------------------

    appraisals = (
        employee.appraisals
        .all()
        .order_by("-appraisal_date", "-id")
    )

    latest_appraisal = appraisals.first()

    # ---------------------------------------------------------
    # TEACHING STAFF
    # ---------------------------------------------------------

    teacher = getattr(
        employee,
        "timetable_teacher",
        None,
    )

    teacher_subjects = []
    class_assignments = []
    teaching_assignments = []

    if teacher:
        teacher_subjects = (
            teacher.teacher_subject_links
            .filter(is_active=True)
            .select_related("subject")
            .order_by("subject__name")
        )

        class_assignments = (
            teacher.class_assignments
            .filter(is_active=True)
            .order_by("class_name", "stream")
        )

        teaching_assignments = (
            teacher.teaching_assignments
            .filter(is_active=True)
            .select_related("subject")
            .order_by(
                "class_name",
                "stream",
                "subject__name",
            )
        )

    # ---------------------------------------------------------
    # SCHOOL BRANDING
    # ---------------------------------------------------------

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    context = {
        "profile": profile,
        "employee": employee,
        "branding": branding,
        "today": timezone.localdate(),

        "attendance": attendance[:10],
        "total_attendance": total_attendance,
        "present_count": present_count,
        "absent_count": absent_count,
        "late_count": late_count,
        "half_day_count": half_day_count,
        "leave_attendance_count": leave_attendance_count,
        "off_day_count": off_day_count,
        "attendance_percentage": attendance_percentage,

        "leave_applications": leave_applications[:10],
        "pending_leave_count": pending_leave_count,
        "approved_leave_count": approved_leave_count,
        "rejected_leave_count": rejected_leave_count,

        "allowances": allowances,
        "total_allowances": total_allowances,

        "deductions": deductions,
        "total_deductions": total_deductions,

        "loans": loans[:10],
        "active_loans": active_loans,
        "outstanding_loan_balance": outstanding_loan_balance,

        "payroll_records": payroll_records[:10],
        "latest_payroll": latest_payroll,

        "payslips": payslips[:10],
        "latest_payslip": latest_payslip,

        "documents": documents[:10],

        "appraisals": appraisals[:10],
        "latest_appraisal": latest_appraisal,

        "teacher": teacher,
        "teacher_subjects": teacher_subjects,
        "class_assignments": class_assignments,
        "teaching_assignments": teaching_assignments,
        "is_teaching_staff": teacher is not None,
    }

    return render(
        request,
        "accounts/staff_dashboard.html",
        context,
    )



