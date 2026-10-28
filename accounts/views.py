from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User, Group, Permission
from django.shortcuts import redirect, render, get_object_or_404
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import get_random_string
from decimal import Decimal

from students.models import Student
from hr_payroll.models import Employee, JobPosition, Department as HRDepartment, Attendance as HRAttendance, EmployeeAllowance, EmployeeDeduction, StaffLoan, PayrollRecord, Payslip, LeaveApplication
from fees.models import FeeRecord, FeePayment, AcademicYear, Term
from academic.models import Assessment, AssessmentType
from attendance.models import Attendance
from lms.models import Assignment
from noticeboard.models import Notice
from timetable.models import TimetableSubject, TimetableTeacher
from timetable.advanced_models import TimetableTeacherSubject, TimetableTeacherClassAssignment, TimetableTeacherTeachingAssignment

from .staff_access import (
    role_permission_required,
    is_admin_user,
    get_staff_teacher,
    get_staff_class_pairs,
    get_staff_subjects_for_class,
    is_class_teacher_for,
)

from .models import (
    UserProfile,
    Department,
    Role,
    SchoolBranding,
)


# ============================================================
# AUTOMATIC EMPLOYEE NUMBER
# ============================================================

def generate_employee_number():
    from number_formats.services import (
        generate_employee_number as _generate_employee_number
    )

    return _generate_employee_number()


# ============================================================
# AUTHENTICATION
# ============================================================

def login_view(request):

    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    if request.method == "POST":

        username = request.POST.get(
            "username",
            ""
        ).strip()

        password = request.POST.get(
            "password",
            ""
        )

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user is not None:

            if not user.is_active:

                messages.error(
                    request,
                    "Your account is inactive."
                )

                return redirect(
                    "accounts:login"
                )

            login(
                request,
                user
            )

            return redirect_by_role(user)

        messages.error(
            request,
            "Invalid username or password."
        )

    branding = (SchoolBranding.objects.filter(is_active=True).order_by("-id").first())

    return render(
        request,
        "accounts/login.html",
        {"branding": branding}
    )


def logout_view(request):

    logout(request)

    return redirect(
        "accounts:login"
    )


# ============================================================
# ROLE REDIRECTION
# ============================================================

def redirect_by_role(user):

    if user.is_superuser:

        return redirect(
            "accounts:admin_dashboard"
        )

    try:

        profile = user.profile

    except UserProfile.DoesNotExist:

        return redirect(
            "accounts:login"
        )

    if not user.is_active or not profile.is_active:

        return redirect(
            "accounts:login"
        )

    if profile.role == "ADMIN":

        return redirect(
            "accounts:admin_dashboard"
        )

    if profile.role == "STAFF":

        # Teaching staff have an active TimetableTeacher record.
        # Other staff use the employee self-service dashboard.
        if profile.employee_id and TimetableTeacher.objects.filter(
            employee_id=profile.employee_id,
            active=True,
        ).exists():
            return redirect(
                "accounts:staff_academic_portal"
            )

        return redirect(
            "accounts:staff_dashboard"
        )

    if profile.role == "STUDENT":

        return redirect(
            "accounts:student_dashboard"
        )

    if profile.role == "PARENT":

        return redirect(
            "accounts:parent_dashboard"
        )

    return redirect(
        "accounts:login"
    )


# ============================================================
# STUDENT HELPER
# ============================================================

def _get_student_for_portal(request):

    profile = get_object_or_404(
        UserProfile.objects.select_related("student"),
        user=request.user
    )

    # Make sure this is actually a student account
    if profile.role != "STUDENT":

        messages.error(
            request,
            "This account is not registered as a student account."
        )

        return None, profile

    student = profile.student

    if not student:

        messages.error(
            request,
            "Your account is not linked to a student record. "
            "Please contact the school administrator."
        )

        return None, profile

    return student, profile


# ============================================================
# DASHBOARDS
# ============================================================

@login_required
def admin_dashboard(request):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to access the administrator dashboard."
        )

        return redirect_by_role(
            request.user
        )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    students_count = Student.objects.count()

    staff_count = UserProfile.objects.filter(
        role="STAFF"
    ).count()

    fee_count = FeeRecord.objects.count()

    academic_count = Assessment.objects.count()

    return render(
        request,
        "accounts/admin_dashboard.html",
        {
            "branding": branding,
            "students_count": students_count,
            "staff_count": staff_count,
            "fee_count": fee_count,
            "academic_count": academic_count,
        }
    )


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
    # ---------------------------------------------------------
    # ACADEMIC PORTAL ACCESS
    # ---------------------------------------------------------

    academic_class_pairs = get_staff_class_pairs(
        request.user
    )

    academic_class_teacher_pairs = []

    for class_name, stream in academic_class_pairs:
        if is_class_teacher_for(
            request.user,
            class_name,
            stream
        ):
            academic_class_teacher_pairs.append(
                (class_name, stream)
            )

    academic_subjects_by_class = {}

    for class_name, stream in academic_class_pairs:
        academic_subjects_by_class[
            (class_name, stream)
        ] = get_staff_subjects_for_class(
            request.user,
            class_name,
            stream
        )

    academic_portal_classes = []

    for class_name, stream in academic_class_pairs:
        academic_portal_classes.append({
            "class_name": class_name,
            "stream": stream,
            "is_class_teacher": is_class_teacher_for(
                request.user,
                class_name,
                stream,
            ),
            "subjects": academic_subjects_by_class.get(
                (class_name, stream),
                [],
            ),
        })

    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # ROLE-BASED PORTAL PERMISSIONS
    # ---------------------------------------------------------

    # Existing Staff Portal functions are retained.
    # Permissions are checked using app_label + codename
    # because several Django apps contain duplicate codenames.

    # ---------------------------------------------------------
    # Staff module access is controlled exclusively by the
    # Admin Portal Custom Role -> Django Permission assignments.
    #
    # IMPORTANT:
    # Do NOT automatically grant access merely because the user
    # is STAFF or because the user has no timetable Teacher record.
    # Operational teacher/class/subject scope is handled separately.


    can_view_attendance = user_has_role_permission(
        request.user,
        "view_attendance",
        "hr_payroll",
    )

    can_view_leave = user_has_role_permission(
        request.user,
        "view_leaveapplication",
        "hr_payroll",
    )

    can_view_payroll = (
        user_has_role_permission(
            request.user,
            "view_payslip",
            "hr_payroll",
        )
        or user_has_role_permission(
            request.user,
            "view_payrollrecord",
            "hr_payroll",
        )
    )

    can_view_loans = user_has_role_permission(
        request.user,
        "view_staffloan",
        "hr_payroll",
    )

    can_view_documents = user_has_role_permission(
        request.user,
        "view_employeedocument",
        "hr_payroll",
    )

    can_view_noticeboard = user_has_role_permission(
        request.user,
        "view_notice",
        "noticeboard",
    )

    can_view_messaging = user_has_role_permission(
        request.user,
        "view_message",
        "messaging",
    )



    can_view_timetable = (
        user_has_role_permission(
            request.user,
            "view_timetablelesson",
            "timetable",
        )
        and (
            is_admin_user(request.user)
            or get_staff_teacher(request.user) is not None
        )
    )

    can_view_weekly_reports = user_has_role_permission(
        request.user,
        "view_weeklyassessmentreport",
        "weekly_reports",
    )

    can_view_academic = user_has_role_permission(
        request.user,
        "view_academicrecord",
        "academic",
    )

    can_view_library = user_has_role_permission(
        request.user,
        "view_librarymember",
        "library",
    )

    can_view_fees = user_has_role_permission(
        request.user,
        "view_feerecord",
        "fees",
    )

    can_view_students = user_has_role_permission(
        request.user,
        "view_student",
        "students",
    )

    can_view_timetable = user_has_role_permission(
        request.user,
        "view_timetablelesson",
        "timetable",
    )

    can_view_transport = user_has_role_permission(
        request.user,
        "view_vehicle",
        "transport",
    )

    can_view_hostel = user_has_role_permission(
        request.user,
        "view_hostel",
        "hostel",
    )

    can_view_inventory = user_has_role_permission(
        request.user,
        "view_inventoryitem",
        "inventory",
    )

    can_view_lms = user_has_role_permission(
        request.user,
        "view_learningresource",
        "lms",
    )

    can_view_teaching = (
        can_view_academic
        and teacher is not None
    )

    can_use_academic_portal = (
        can_view_academic
        and (
            is_admin_user(request.user)
            or bool(academic_class_pairs)
        )
    )
    # SCHOOL BRANDING
    # ---------------------------------------------------------

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    # Show the new Transport Pro module only to an active Transport Manager
    # whose custom ERP role has every permission required by its dashboard.
    transport_dashboard_permissions = (
        ("view_vehicle", "vehicle"),
        ("view_transportstaff", "transportstaff"),
        ("view_learnertransport", "learnertransport"),
        ("view_transportroute", "transportroute"),
        ("view_transporttrip", "transporttrip"),
        ("view_transportincident", "transportincident"),
        ("view_maintenancerecord", "maintenancerecord"),
        ("view_boardingevent", "boardingevent"),
        ("view_transportcharge", "transportcharge"),
        ("view_transportpayment", "transportpayment"),
    )
    transport_role = getattr(profile, "custom_role", None)
    show_transport_module = bool(
        transport_role
        and transport_role.is_active
        and transport_role.name == "Transport Manager"
        and all(
            transport_role.permissions.filter(
                codename=codename,
                content_type__app_label="transport_pro",
                content_type__model=model_name,
            ).exists()
            for codename, model_name in transport_dashboard_permissions
        )
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

        "academic_class_pairs": academic_class_pairs,
        "academic_portal_classes": academic_portal_classes,
        "academic_class_teacher_pairs": academic_class_teacher_pairs,
        "academic_subjects_by_class": academic_subjects_by_class,
        "can_view_attendance": can_view_attendance,
        "can_view_leave": can_view_leave,
        "can_view_payroll": can_view_payroll,
        "can_view_loans": can_view_loans,
        "can_view_documents": can_view_documents,
        "can_view_noticeboard": can_view_noticeboard,
        "can_view_messaging": can_view_messaging,
        "can_view_timetable": can_view_timetable,
        "can_view_weekly_reports": can_view_weekly_reports,
        "can_view_academic": can_view_academic,
        "can_view_library": can_view_library,
        "can_view_fees": can_view_fees,
        "can_view_students": can_view_students,
        "can_view_timetable": can_view_timetable,
        "can_view_transport": can_view_transport,
        "show_transport_module": show_transport_module,
        "can_view_hostel": can_view_hostel,
        "can_view_inventory": can_view_inventory,
        "can_view_lms": can_view_lms,
        "can_use_academic_portal": can_use_academic_portal,
        "can_view_teaching": can_view_teaching,
    }

    return render(
        request,
        "accounts/staff_dashboard.html",
        context,
    )


# ============================================================
# STAFF ACADEMIC PORTAL
# ============================================================

@login_required
def staff_academic_portal(request):
    if not (
        is_admin_user(request.user)
        or user_has_role_permission(
            request.user,
            "view_academicrecord",
            "academic",
        )
    ):
        return redirect("accounts:staff_dashboard")

    if not is_admin_user(request.user):
        class_pairs = get_staff_class_pairs(request.user)

        if not class_pairs:
            return redirect("accounts:staff_dashboard")
    else:
        class_pairs = get_staff_class_pairs(request.user)

    academic_portal_classes = []

    for class_name, stream in class_pairs:

        academic_portal_classes.append({
            "class_name": class_name,
            "stream": stream,
            "is_class_teacher": is_class_teacher_for(
                request.user,
                class_name,
                stream,
            ),
        })

    return render(
        request,
        "accounts/staff_academic_portal.html",
        {
            "academic_portal_classes": academic_portal_classes,
            "branding": (
                SchoolBranding.objects
                .filter(is_active=True)
                .order_by("-id")
                .first()
            ),
            "today": timezone.localdate(),
        },
    )


@login_required
def staff_academic_class(request):
    if not (
        is_admin_user(request.user)
        or user_has_role_permission(
            request.user,
            "view_academicrecord",
            "academic",
        )
    ):
        return redirect("accounts:staff_dashboard")

    class_name = request.GET.get("class_name", "").strip()
    stream = request.GET.get("stream", "").strip()

    if not class_name:
        return redirect("accounts:staff_academic_portal")

    if not is_admin_user(request.user):

        class_pairs = get_staff_class_pairs(request.user)

        if (class_name, stream) not in class_pairs:
            return redirect("accounts:staff_academic_portal")

    is_class_teacher = is_class_teacher_for(
        request.user,
        class_name,
        stream,
    )

    subjects = get_staff_subjects_for_class(
        request.user,
        class_name,
        stream,
    )

    return render(
        request,
        "accounts/staff_academic_class.html",
        {
            "class_name": class_name,
            "stream": stream,
            "is_class_teacher": is_class_teacher,
            "subjects": subjects,
            "branding": (
                SchoolBranding.objects
                .filter(is_active=True)
                .order_by("-id")
                .first()
            ),
            "today": timezone.localdate(),
        },
    )

# ============================================================
# STUDENT DASHBOARD
# ============================================================

@login_required
def student_dashboard(request):

    # --------------------------------------------------------
    # GET LOGGED-IN STUDENT
    # --------------------------------------------------------

    student, profile = _get_student_for_portal(request)

    if not student:

        return redirect(
            "accounts:login"
        )

    # --------------------------------------------------------
    # ---------------------------------------------------------
    # SCHOOL BRANDING
    # --------------------------------------------------------

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    # ========================================================
    # ATTENDANCE
    # ========================================================

    attendance_records = (
        Attendance.objects
        .filter(student=student)
        .order_by("-date")
    )

    present = attendance_records.filter(
        status="present"
    ).count()

    absent = attendance_records.filter(
        status="absent"
    ).count()

    late = attendance_records.filter(
        status="late"
    ).count()

    excused = attendance_records.filter(
        status="excused"
    ).count()

    total_attendance = (
        present
        + absent
        + late
        + excused
    )

    if total_attendance:

        attendance_percentage = round(
            (present / total_attendance) * 100,
            1
        )

    else:

        attendance_percentage = 0

    attendance_summary = {
        "present": present,
        "absent": absent,
        "late": late,
        "excused": excused,
    }

    recent_attendance_records = (
        attendance_records[:10]
    )

    # ========================================================
    # FEES
    # ========================================================

    fee_records = (
        FeeRecord.objects
        .filter(student=student)
        .select_related(
            "academic_year",
            "term"
        )
        .order_by(
            "term__order",
            "-id"
        )
    )

    total_charged = sum(
        (
            record.amount_charged
            for record in fee_records
        ),
        0
    )

    total_paid = sum(
        (
            record.amount_paid
            for record in fee_records
        ),
        0
    )

    total_balance = sum(
        (
            record.balance
            for record in fee_records
        ),
        0
    )

    # ========================================================
    # RESULTS
    # ========================================================

    assessments = (
        Assessment.objects
        .filter(student=student)
        .select_related(
            "subject",
            "academic_year",
            "term",
            "assessment_type"
        )
        .order_by("-id")
    )

    recent_assessments = assessments[:10]

    # ========================================================
    # ASSIGNMENTS
    # ========================================================

    assignments = (
        Assignment.objects
        .filter(is_published=True)
        .filter(
            Q(class_name="") |
            Q(class_name=student.class_name)
        )
        .order_by(
            "due_date",
            "-created_at"
        )[:5]
    )

    # ========================================================
    # NOTICES
    # ========================================================

    now = timezone.now()

    notices = (
        Notice.objects
        .filter(
            published=True,
            audience__in=[
                "everyone",
                "students",
            ]
        )
        .filter(
            Q(expiry_date__isnull=True) |
            Q(expiry_date__gte=now)
        )
        .order_by(
            "-publish_date"
        )[:5]
    )

    # ========================================================
    # SEND DATA TO TEMPLATE
    # ========================================================

    return render(
        request,
        "accounts/student_dashboard.html",
        {
            "student": student,
            "profile": profile,
            "branding": branding,

            # Attendance
            "attendance_records":
                recent_attendance_records,

            "attendance_percentage":
                attendance_percentage,

            "attendance_summary":
                attendance_summary,

            # Fees
            "fee_records":
                fee_records,

            "total_charged":
                total_charged,

            "total_paid":
                total_paid,

            "total_balance":
                total_balance,

            # Results
            "assessments":
                assessments,

            "recent_assessments":
                recent_assessments,

            # Assignments
            "assignments":
                assignments,

            # Notices
            "notices":
                notices,
        }
    )


# ============================================================
# PARENT DASHBOARD
# ============================================================

@login_required
def parent_dashboard(request):

    from decimal import Decimal
    from django.db.models import Sum, Q
    from django.utils import timezone

    from fees.models import FeeRecord, FeePayment
    from academic.models import Assessment
    from attendance.models import Attendance
    from lms.models import Assignment
    from noticeboard.models import Notice

    parent = getattr(request.user, "parent", None)

    if parent is None:
        messages.error(
            request,
            "Your account is not linked to a parent profile."
        )
        return redirect("accounts:login")

    children = list(
        parent.children
        .all()
        .order_by("admission_no")
    )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    total_paid = Decimal("0.00")
    total_balance = Decimal("0.00")

    now = timezone.now()

    # --------------------------------------------------------
    # LOAD REAL DATABASE INFORMATION FOR EACH CHILD
    # --------------------------------------------------------

    for child in children:

        # ====================================================
        # FEES
        # ====================================================

        fee_records = FeeRecord.objects.filter(
            student=child
        )

        child_paid = (
            FeePayment.objects
            .filter(fee_record__student=child)
            .aggregate(total=Sum("amount"))
            ["total"]
            or Decimal("0.00")
        )

        child_balance = (
            fee_records.aggregate(
                opening=Sum("opening_balance"),
                charged=Sum("amount_charged"),
            )
        )

        child_balance = (
            (child_balance["opening"] or Decimal("0.00"))
            + (child_balance["charged"] or Decimal("0.00"))
            - child_paid
        )

        child.total_fee_paid = child_paid
        child.total_fee_balance = child_balance

        total_paid += child_paid
        total_balance += child_balance

        # ====================================================
        # ACADEMIC RESULTS
        # ====================================================

        child.parent_academic_results = list(
            Assessment.objects
            .filter(student=child)
            .select_related(
                "subject",
                "academic_year",
                "term",
                "assessment_type",
            )
            .order_by(
                "-academic_year__year",
                "term__order",
                "subject__name",
                "assessment_type__order",
            )[:5]
        )

        # ====================================================
        # ATTENDANCE
        # ====================================================

        attendance_qs = Attendance.objects.filter(
            student=child
        )

        attendance_total = attendance_qs.count()

        attendance_present = attendance_qs.filter(
            status="PRESENT"
        ).count()

        attendance_absent = attendance_qs.filter(
            status="ABSENT"
        ).count()

        attendance_late = attendance_qs.filter(
            status="LATE"
        ).count()

        attendance_excused = attendance_qs.filter(
            status="EXCUSED"
        ).count()

        attendance_rate = (
            round(
                (attendance_present / attendance_total) * 100,
                1
            )
            if attendance_total
            else 0
        )

        child.attendance_total = attendance_total
        child.attendance_present = attendance_present
        child.attendance_absent = attendance_absent
        child.attendance_late = attendance_late
        child.attendance_excused = attendance_excused
        child.attendance_rate = attendance_rate

        # ====================================================
        # ASSIGNMENTS
        # ====================================================

        child.parent_assignments = list(
            Assignment.objects
            .filter(
                is_published=True
            )
            .filter(
                Q(class_name=child.class_name)
                | Q(class_name="")
            )
            .order_by("-created_at")[:5]
        )

    # --------------------------------------------------------
    # SCHOOL ANNOUNCEMENTS
    # --------------------------------------------------------

    published_announcements = (
        Notice.objects
        .filter(
            published=True
        )
        .filter(
            Q(audience="parents")
            | Q(audience="everyone")
        )
        .filter(
            Q(expiry_date__isnull=True)
            | Q(expiry_date__gte=now)
        )
        .order_by("-publish_date")[:10]
    )

    # --------------------------------------------------------
    # DASHBOARD SUMMARY
    # --------------------------------------------------------

    context = {
        "parent": parent,
        "children": children,
        "children_count": len(children),
        "branding": branding,

        "total_paid": total_paid,
        "total_balance": total_balance,

        "published_announcements": published_announcements,
    }

    return render(
        request,
        "accounts/parent_dashboard.html",
        context
    )

# ============================================================
# STUDENT RESULTS
# ============================================================

@login_required
def student_results(request):

    student, profile = _get_student_for_portal(request)

    if not student:

        return redirect(
            "accounts:login"
        )

    academic_years = (
        AcademicYear.objects
        .all()
        .order_by("-year")
    )

    terms = (
        Term.objects
        .all()
        .order_by("order")
    )

    assessment_types = (
        AssessmentType.objects
        .filter(is_active=True)
        .order_by("order", "name")
    )

    selected_year_id = request.GET.get(
        "academic_year"
    )

    selected_term_id = request.GET.get(
        "term"
    )

    selected_assessment_type_id = request.GET.get(
        "assessment_type"
    )

    selected_year = None
    selected_term = None
    selected_assessment_type = None

    if selected_year_id:

        selected_year = (
            academic_years
            .filter(id=selected_year_id)
            .first()
        )

    if selected_term_id:

        selected_term = (
            terms
            .filter(id=selected_term_id)
            .first()
        )

    if selected_assessment_type_id:

        selected_assessment_type = (
            assessment_types
            .filter(id=selected_assessment_type_id)
            .first()
        )

    assessments = Assessment.objects.none()

    if selected_year and selected_term:

        assessments = (
            Assessment.objects
            .filter(
                student=student,
                academic_year=selected_year,
                term=selected_term,
            )
            .select_related(
                "subject",
                "academic_year",
                "term",
                "assessment_type",
            )
            .order_by(
                "subject__name",
                "assessment_type__order",
            )
        )

        if selected_assessment_type:

            assessments = assessments.filter(
                assessment_type=selected_assessment_type
            )

    return render(
        request,
        "accounts/student_results.html",
        {
            "student": student,
            "profile": profile,

            "academic_years":
                academic_years,

            "terms":
                terms,

            "assessment_types":
                assessment_types,

            "selected_year":
                selected_year,

            "selected_term":
                selected_term,

            "selected_assessment_type":
                selected_assessment_type,

            "assessments":
                assessments,
        }
    )


# ============================================================
# STUDENT FEES
# ============================================================

@login_required
def student_fees(request):

    student, profile = _get_student_for_portal(request)

    if not student:

        return redirect(
            "accounts:login"
        )

    academic_years = (
        AcademicYear.objects
        .filter(is_active=True)
        .order_by("-year")
    )

    terms = (
        Term.objects
        .filter(is_active=True)
        .order_by("order")
    )

    selected_year_id = request.GET.get(
        "academic_year",
        ""
    ).strip()

    selected_term_id = request.GET.get(
        "term",
        ""
    ).strip()

    selected_year = None
    selected_term = None

    if selected_year_id:

        selected_year = (
            academic_years
            .filter(id=selected_year_id)
            .first()
        )

    if selected_term_id:

        selected_term = (
            terms
            .filter(id=selected_term_id)
            .first()
        )

    fee_records = FeeRecord.objects.none()

    receipts = FeePayment.objects.none()

    # --------------------------------------------------------
    # LOAD FEES
    # --------------------------------------------------------

    if selected_year:

        fee_records = (
            FeeRecord.objects
            .filter(
                student=student,
                academic_year=selected_year
            )
            .select_related(
                "academic_year",
                "term"
            )
            .prefetch_related("payments")
            .order_by(
                "term__order",
                "-id"
            )
        )

        if selected_term:

            fee_records = fee_records.filter(
                term=selected_term
            )

    # --------------------------------------------------------
    # LOAD RECEIPTS
    # --------------------------------------------------------

    load_receipts = (
        request.GET.get("load_receipts")
        == "1"
    )

    if load_receipts:

        receipt_filter = Q(
            fee_record__student=student
        )

        if selected_year:

            receipt_filter &= Q(
                fee_record__academic_year=selected_year
            )

        if selected_term:

            receipt_filter &= Q(
                fee_record__term=selected_term
            )

        receipts = (
            FeePayment.objects
            .filter(receipt_filter)
            .select_related(
                "fee_record",
                "fee_record__student",
                "fee_record__academic_year",
                "fee_record__term"
            )
            .order_by(
                "-payment_date",
                "-id"
            )
        )

    # --------------------------------------------------------
    # TOTALS
    # --------------------------------------------------------

    total_charged = sum(
        (
            record.amount_charged
            for record in fee_records
        ),
        0
    )

    total_paid = sum(
        (
            record.amount_paid
            for record in fee_records
        ),
        0
    )

    total_balance = sum(
        (
            record.balance
            for record in fee_records
        ),
        0
    )

    receipt_total = sum(
        (
            receipt.amount
            for receipt in receipts
        ),
        0
    )

    return render(
        request,
        "accounts/student_fees.html",
        {
            "student": student,
            "profile": profile,

            "academic_years":
                academic_years,

            "terms":
                terms,

            "selected_year":
                selected_year,

            "selected_term":
                selected_term,

            "fee_records":
                fee_records,

            "total_charged":
                total_charged,

            "total_paid":
                total_paid,

            "total_balance":
                total_balance,

            "receipts":
                receipts,

            "receipt_total":
                receipt_total,

            "load_receipts":
                load_receipts,
        }
    )


# ============================================================
# STUDENT PRINT RECEIPT
# ============================================================

@login_required
def student_print_receipt(
    request,
    payment_id
):

    student, profile = _get_student_for_portal(request)

    if not student:

        return redirect(
            "accounts:login"
        )

    payment = get_object_or_404(
        FeePayment.objects.select_related(
            "fee_record",
            "fee_record__student",
            "fee_record__academic_year",
            "fee_record__term",
        ).filter(
            fee_record__student=student
        ),
        id=payment_id,
    )

    fee_record = payment.fee_record

    academic_year_id = request.GET.get(
        "academic_year"
    )

    term_id = request.GET.get(
        "term"
    )

    if (
        academic_year_id
        and str(fee_record.academic_year_id)
        != str(academic_year_id)
    ):

        return redirect(
            "accounts:student_fees"
        )

    if (
        term_id
        and str(fee_record.term_id)
        != str(term_id)
    ):

        return redirect(
            "accounts:student_fees"
        )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    return render(
        request,
        "accounts/student_receipt.html",
        {
            "payment": payment,
            "fee_record": fee_record,
            "student": student,
            "profile": profile,
            "branding": branding,
            "selected_year":
                fee_record.academic_year,
            "selected_term":
                fee_record.term,
        },
    )


# ============================================================
# STUDENT TIMETABLE
# ============================================================

@login_required
def student_timetable(request):

    student, profile = _get_student_for_portal(request)

    if not student:
        return redirect("accounts:login")

    from timetable.models import (
        TimetableTerm,
        TimetableClass,
        TimetableDay,
        TimetablePeriod,
        TimetableLesson,
    )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    # Student is only allowed to view their own class.
    student_class_name = (
        str(getattr(student, "class_name", "") or "")
        .strip()
    )

    grade_options = (
        TimetableClass.objects
        .filter(active=True)
        .order_by("name", "id")
    )

    allowed_grade = (
        grade_options
        .filter(name__iexact=student_class_name)
        .first()
        if student_class_name
        else None
    )

    if allowed_grade:
        grades = [allowed_grade]
    else:
        grades = []

    academic_years = sorted(
        set(
            TimetableTerm.objects
            .filter(active=True)
            .values_list("academic_year", flat=True)
        ),
        reverse=True,
    )

    selected_year = (
        request.GET.get("academic_year", "").strip()
        or (academic_years[0] if academic_years else "")
    )

    terms = (
        TimetableTerm.objects
        .filter(
            active=True,
            academic_year=selected_year,
        )
        .order_by("term_name", "id")
    )

    selected_term_id = request.GET.get("term", "").strip()

    selected_term = (
        terms.filter(pk=selected_term_id).first()
        if selected_term_id
        else terms.first()
    )

    selected_grade_id = request.GET.get("grade", "").strip()

    selected_grade = (
        allowed_grade
        if allowed_grade
        and (
            not selected_grade_id
            or str(allowed_grade.pk) == str(selected_grade_id)
        )
        else None
    )

    timetable_rows = []

    if selected_term and selected_grade:

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

        lessons = (
            TimetableLesson.objects
            .filter(
                term=selected_term,
                class_group=selected_grade,
            )
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
                "id",
            )
        )

        lesson_map = {}

        for lesson in lessons:
            lesson_map[
                (lesson.day_id, lesson.period_id)
            ] = lesson

        for day in days:

            cells = []

            for period in periods:

                lesson = lesson_map.get(
                    (day.id, period.id)
                )

                cells.append({
                    "period": period,
                    "lesson": lesson,
                })

            timetable_rows.append({
                "day": day,
                "cells": cells,
            })

    return render(
        request,
        "accounts/student_timetable.html",
        {
            "student": student,
            "profile": profile,
            "branding": branding,
            "academic_years": academic_years,
            "selected_year": selected_year,
            "terms": terms,
            "selected_term": selected_term,
            "selected_term_id": (
                str(selected_term.pk)
                if selected_term
                else ""
            ),
            "grades": grades,
            "selected_grade": selected_grade,
            "selected_grade_id": (
                str(selected_grade.pk)
                if selected_grade
                else ""
            ),
            "timetable_rows": timetable_rows,
        },
    )



# ============================================================
# STUDENT ASSIGNMENTS
# ============================================================

@login_required
def student_assignments(request):

    student, profile = _get_student_for_portal(request)

    if not student:

        return redirect(
            "accounts:login"
        )

    assignments = (
        Assignment.objects
        .filter(is_published=True)
        .filter(
            Q(class_name="")
            | Q(class_name=student.class_name)
        )
        .order_by(
            "due_date",
            "-created_at"
        )
    )

    return render(
        request,
        "accounts/student_assignments.html",
        {
            "student": student,
            "profile": profile,
            "assignments": assignments,
        }
    )


# ============================================================
# STUDENT LEARNING
# ============================================================

@login_required
def student_learning(request):

    student, profile = _get_student_for_portal(request)

    if not student:

        return redirect(
            "accounts:login"
        )

    return render(
        request,
        "accounts/student_learning.html",
        {
            "student": student,
            "profile": profile,
        }
    )


# ============================================================
# STUDENT ATTENDANCE
# ============================================================

@login_required
def student_attendance(request):

    student, profile = _get_student_for_portal(request)

    if not student:

        return redirect(
            "accounts:login"
        )

    attendance_records = (
        Attendance.objects
        .filter(student=student)
        .order_by("-date")
    )

    present = attendance_records.filter(
        status="present"
    ).count()

    absent = attendance_records.filter(
        status="absent"
    ).count()

    late = attendance_records.filter(
        status="late"
    ).count()

    excused = attendance_records.filter(
        status="excused"
    ).count()

    total = (
        present
        + absent
        + late
        + excused
    )

    attendance_percentage = (
        round(
            (present / total) * 100,
            1
        )
        if total
        else 0
    )

    return render(
        request,
        "accounts/student_attendance.html",
        {
            "student": student,
            "profile": profile,
            "attendance_records":
                attendance_records,
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "attendance_percentage":
                attendance_percentage,
        }
    )


# ============================================================
# STUDENT PROFILE
# ============================================================

@login_required
def student_profile(request):

    student, profile = _get_student_for_portal(request)

    if not student:

        return redirect(
            "accounts:login"
        )

    return render(
        request,
        "accounts/student_profile.html",
        {
            "student": student,
            "profile": profile,
        }
    )


# ============================================================
# STUDENT ANNOUNCEMENTS
# ============================================================

@login_required
def student_announcements(request):

    student, profile = _get_student_for_portal(request)

    if not student:

        return redirect(
            "accounts:login"
        )

    now = timezone.now()

    announcements = (
        Notice.objects
        .filter(
            published=True,
            audience__in=[
                "everyone",
                "students",
            ],
        )
        .filter(
            Q(expiry_date__isnull=True)
            | Q(expiry_date__gte=now)
        )
        .order_by("-publish_date")
    )

    return render(
        request,
        "accounts/student_announcements.html",
        {
            "student": student,
            "profile": profile,
            "announcements": announcements,
        },
    )


# ============================================================
# STUDENT LIBRARY
# ============================================================

@login_required
def student_library(request):

    student, profile = _get_student_for_portal(request)

    if not student:

        return redirect(
            "accounts:login"
        )

    from library.models import (
        Book,
        BookIssue,
        LibraryMember,
    )

    books = (
        Book.objects
        .filter(
            status="available",
            available_copies__gt=0,
        )
        .select_related("category")
        .order_by("title")
    )

    member = (
        LibraryMember.objects
        .filter(
            admission_number=student.admission_no,
            member_type="student",
            active=True,
        )
        .first()
    )

    my_books = BookIssue.objects.none()

    if member:

        my_books = (
            BookIssue.objects
            .filter(member=member)
            .select_related("book")
            .order_by("-issue_date")
        )

    current_books = my_books.filter(
        status__in=[
            "issued",
            "overdue",
        ]
    )

    returned_books = my_books.filter(
        status="returned"
    )

    return render(
        request,
        "accounts/student_library.html",
        {
            "student": student,
            "profile": profile,
            "books": books,
            "member": member,
            "my_books": my_books,
            "current_books": current_books,
            "returned_books": returned_books,
        },
    )


# ============================================================
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import get_random_string
from decimal import Decimal

# ============================================================
# PARENT PORTAL HELPERS
# ============================================================

def _get_parent_child(request, student_id):
    parent = getattr(request.user, "parent", None)

    if parent is None:
        return None, None

    child = get_object_or_404(
        parent.children.all(),
        id=student_id
    )

    return parent, child


# ============================================================
# PARENT FEES
# ============================================================

@login_required
def parent_fees(request, student_id):

    parent, child = _get_parent_child(request, student_id)

    if parent is None:
        return redirect("accounts:login")

    academic_years = (
        AcademicYear.objects
        .filter(is_active=True)
        .order_by("-year")
    )

    terms = (
        Term.objects
        .filter(is_active=True)
        .order_by("order")
    )

    selected_year_id = request.GET.get(
        "academic_year", ""
    ).strip()

    selected_term_id = request.GET.get(
        "term", ""
    ).strip()

    selected_year = None
    selected_term = None

    if selected_year_id:
        selected_year = (
            academic_years
            .filter(id=selected_year_id)
            .first()
        )

    if selected_term_id:
        selected_term = (
            terms
            .filter(id=selected_term_id)
            .first()
        )

    fee_records = FeeRecord.objects.none()
    receipts = FeePayment.objects.none()

    if selected_year:

        fee_records = (
            FeeRecord.objects
            .filter(
                student=child,
                academic_year=selected_year
            )
            .select_related(
                "academic_year",
                "term"
            )
            .prefetch_related("payments")
            .order_by(
                "term__order",
                "-id"
            )
        )

        if selected_term:
            fee_records = fee_records.filter(
                term=selected_term
            )

    if request.GET.get("load_receipts") == "1":

        receipts = (
            FeePayment.objects
            .filter(
                fee_record__student=child
            )
            .select_related(
                "fee_record",
                "fee_record__academic_year",
                "fee_record__term"
            )
            .order_by("-payment_date", "-id")
        )

        if selected_year:
            receipts = receipts.filter(
                fee_record__academic_year=selected_year
            )

        if selected_term:
            receipts = receipts.filter(
                fee_record__term=selected_term
            )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    return render(
        request,
        "accounts/parent_fees.html",
        {
            "parent": parent,
            "student": child,
            "child": child,
            "academic_years": academic_years,
            "terms": terms,
            "selected_year": selected_year,
            "selected_term": selected_term,
            "fee_records": fee_records,
            "receipts": receipts,
            "load_receipts":
                request.GET.get("load_receipts") == "1",
            "branding": branding,
        }
    )


# ============================================================
# PARENT TIMETABLE
# ============================================================

@login_required
def parent_timetable(request, student_id):

    from timetable.models import (
        TimetableTerm,
        TimetableClass,
        TimetableDay,
        TimetablePeriod,
        TimetableLesson,
    )

    parent = getattr(request.user, "parent", None)

    if parent is None:
        messages.error(
            request,
            "Your account is not linked to a parent profile."
        )
        return redirect("accounts:login")

    # Security: child MUST belong to this parent.
    child = get_object_or_404(
        parent.children.all(),
        pk=student_id,
    )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    child_class_name = (
        str(getattr(child, "class_name", "") or "")
        .strip()
    )

    # Parent can only select the selected child's actual class.
    grade_options = (
        TimetableClass.objects
        .filter(active=True)
        .order_by("name", "id")
    )

    allowed_grade = (
        grade_options
        .filter(name__iexact=child_class_name)
        .first()
        if child_class_name
        else None
    )

    grades = [allowed_grade] if allowed_grade else []

    academic_years = sorted(
        set(
            TimetableTerm.objects
            .filter(active=True)
            .values_list("academic_year", flat=True)
        ),
        reverse=True,
    )

    selected_year = (
        request.GET.get("academic_year", "").strip()
        or (academic_years[0] if academic_years else "")
    )

    terms = (
        TimetableTerm.objects
        .filter(
            active=True,
            academic_year=selected_year,
        )
        .order_by("term_name", "id")
    )

    selected_term_id = request.GET.get("term", "").strip()

    selected_term = (
        terms.filter(pk=selected_term_id).first()
        if selected_term_id
        else terms.first()
    )

    selected_grade_id = request.GET.get("grade", "").strip()

    selected_grade = (
        allowed_grade
        if allowed_grade
        and (
            not selected_grade_id
            or str(allowed_grade.pk) == str(selected_grade_id)
        )
        else None
    )

    timetable_rows = []

    if selected_term and selected_grade:

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

        lessons = (
            TimetableLesson.objects
            .filter(
                term=selected_term,
                class_group=selected_grade,
            )
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
                "id",
            )
        )

        lesson_map = {}

        for lesson in lessons:
            lesson_map[
                (lesson.day_id, lesson.period_id)
            ] = lesson

        for day in days:

            cells = []

            for period in periods:

                lesson = lesson_map.get(
                    (day.id, period.id)
                )

                cells.append({
                    "period": period,
                    "lesson": lesson,
                })

            timetable_rows.append({
                "day": day,
                "cells": cells,
            })

    return render(
        request,
        "accounts/parent_timetable.html",
        {
            "child": child,
            "branding": branding,
            "academic_years": academic_years,
            "selected_year": selected_year,
            "terms": terms,
            "selected_term": selected_term,
            "selected_term_id": (
                str(selected_term.pk)
                if selected_term
                else ""
            ),
            "grades": grades,
            "selected_grade": selected_grade,
            "selected_grade_id": (
                str(selected_grade.pk)
                if selected_grade
                else ""
            ),
            "timetable_rows": timetable_rows,
        },
    )



# ============================================================
# PARENT ASSIGNMENTS
# ============================================================

@login_required
def parent_assignments(request, student_id):

    parent, child = _get_parent_child(request, student_id)

    if parent is None:
        return redirect("accounts:login")

    assignments = (
        Assignment.objects
        .filter(is_published=True)
        .filter(
            Q(class_name="")
            | Q(class_name=child.class_name)
        )
        .order_by(
            "due_date",
            "-created_at"
        )
    )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .first()
    )

    return render(
        request,
        "accounts/parent_assignments.html",
        {
            "parent": parent,
            "student": child,
            "child": child,
            "assignments": assignments,
            "branding": branding,
        }
    )


# ============================================================
# PARENT LEARNING
# ============================================================

@login_required
def parent_learning(request, student_id):

    parent, child = _get_parent_child(request, student_id)

    if parent is None:
        return redirect("accounts:login")

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .first()
    )

    return render(
        request,
        "accounts/parent_learning.html",
        {
            "parent": parent,
            "student": child,
            "child": child,
            "branding": branding,
        }
    )


# ============================================================
# PARENT ATTENDANCE
# ============================================================

@login_required
def parent_attendance(request, student_id):

    parent, child = _get_parent_child(request, student_id)

    if parent is None:
        return redirect("accounts:login")

    attendance_records = (
        Attendance.objects
        .filter(student=child)
        .order_by("-date")
    )

    present = attendance_records.filter(
        status="present"
    ).count()

    absent = attendance_records.filter(
        status="absent"
    ).count()

    late = attendance_records.filter(
        status="late"
    ).count()

    excused = attendance_records.filter(
        status="excused"
    ).count()

    total = (
        present
        + absent
        + late
        + excused
    )

    attendance_percentage = (
        round((present / total) * 100, 1)
        if total
        else 0
    )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .first()
    )

    return render(
        request,
        "accounts/parent_attendance.html",
        {
            "parent": parent,
            "student": child,
            "child": child,
            "attendance_records":
                attendance_records,
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "attendance_percentage":
                attendance_percentage,
            "branding": branding,
        }
    )


# ============================================================
# PARENT ANNOUNCEMENTS
# ============================================================

@login_required
def parent_announcements(request):

    parent = getattr(
        request.user,
        "parent",
        None
    )

    if parent is None:
        return redirect("accounts:login")

    now = timezone.now()

    announcements = (
        Notice.objects
        .filter(
            published=True,
            audience__in=[
                "everyone",
                "parents",
            ],
        )
        .filter(
            Q(expiry_date__isnull=True)
            | Q(expiry_date__gte=now)
        )
        .order_by("-publish_date")
    )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .first()
    )

    return render(
        request,
        "accounts/parent_announcements.html",
        {
            "parent": parent,
            "announcements": announcements,
            "branding": branding,
        }
    )


# ============================================================
# PARENT LIBRARY
# ============================================================

@login_required
def parent_library(request, student_id):

    parent, child = _get_parent_child(request, student_id)

    if parent is None:
        return redirect("accounts:login")

    from library.models import (
        Book,
        BookIssue,
        LibraryMember,
    )

    books = (
        Book.objects
        .filter(
            status="available",
            available_copies__gt=0,
        )
        .select_related("category")
        .order_by("title")
    )

    member = (
        LibraryMember.objects
        .filter(
            admission_number=child.admission_no,
            member_type="student",
            active=True,
        )
        .first()
    )

    my_books = BookIssue.objects.none()

    if member:
        my_books = (
            BookIssue.objects
            .filter(member=member)
            .select_related("book")
            .order_by("-issue_date")
        )

    current_books = my_books.filter(
        status__in=[
            "issued",
            "overdue",
        ]
    )

    returned_books = my_books.filter(
        status="returned"
    )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .first()
    )

    return render(
        request,
        "accounts/parent_library.html",
        {
            "parent": parent,
            "student": child,
            "child": child,
            "books": books,
            "member": member,
            "my_books": my_books,
            "current_books": current_books,
            "returned_books": returned_books,
            "branding": branding,
        }
    )



@login_required
def parent_print_receipt(request, payment_id):
    parent = getattr(request.user, "parent", None)

    if parent is None:
        return redirect("accounts:login")

    payment = get_object_or_404(
        FeePayment.objects.select_related(
            "fee_record",
            "fee_record__student",
            "fee_record__academic_year",
            "fee_record__term",
        ).filter(
            fee_record__student__in=parent.children.all()
        ),
        id=payment_id,
    )

    fee_record = payment.fee_record

    academic_year_id = request.GET.get("academic_year")
    term_id = request.GET.get("term")

    if academic_year_id:
        if str(fee_record.academic_year_id) != str(academic_year_id):
            return redirect(
                "accounts:parent_fees",
                fee_record.student_id
            )

    if term_id:
        if str(fee_record.term_id) != str(term_id):
            return redirect(
                "accounts:parent_fees",
                fee_record.student_id
            )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    return render(
        request,
        "accounts/student_receipt.html",
        {
            "payment": payment,
            "fee_record": fee_record,
            "student": fee_record.student,
            "profile": None,
            "branding": branding,
            "selected_year": fee_record.academic_year,
            "selected_term": fee_record.term,
            "parent": parent,
        }
    )

# PARENT ACADEMIC RESULTS
# ============================================================

@login_required
def parent_academic_results(
    request,
    student_id
):

    parent = getattr(
        request.user,
        "parent",
        None
    )

    if parent is None:

        return redirect(
            "accounts:parent_dashboard"
        )

    child = get_object_or_404(
        parent.children.all(),
        id=student_id
    )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .first()
    )

    academic_years = (
        AcademicYear.objects
        .filter(is_active=True)
        .order_by("-year")
    )

    terms = (
        Term.objects
        .filter(is_active=True)
        .order_by("order")
    )

    assessment_types = (
        AssessmentType.objects
        .filter(is_active=True)
        .order_by("order", "name")
    )

    results = Assessment.objects.none()

    selected_year = request.GET.get(
        "academic_year",
        ""
    )

    selected_class = request.GET.get(
        "class_name",
        child.class_name
    )

    selected_term = request.GET.get(
        "term",
        ""
    )

    selected_assessment = request.GET.get(
        "assessment_type",
        ""
    )

    if (
        selected_year
        and selected_term
        and selected_assessment
    ):

        results = (
            Assessment.objects
            .filter(
                student=child,
                student__class_name=selected_class,
                academic_year_id=selected_year,
                term_id=selected_term,
                assessment_type_id=selected_assessment,
            )
            .select_related(
                "subject",
                "academic_year",
                "term",
                "assessment_type",
            )
            .order_by("subject__name")
        )

    average = None

    if results.exists():

        scores = [
            float(result.score)
            for result in results
        ]

        average = round(
            sum(scores) / len(scores),
            2
        )

    return render(
        request,
        "accounts/parent_academic_results.html",
        {
            "parent": parent,
            "child": child,
            "branding": branding,
            "academic_years": academic_years,
            "terms": terms,
            "assessment_types":
                assessment_types,
            "results": results,
            "average": average,
            "selected_year":
                selected_year,
            "selected_class":
                selected_class,
            "selected_term":
                selected_term,
            "selected_assessment":
                selected_assessment,
        },
    )


# ============================================================
# ============================================================
# ROLE PERMISSION HELPER
# ============================================================

def user_has_role_permission(
    user,
    permission_codename,
    app_label=None
):

    if user.is_superuser:

        return True

    try:

        profile = user.profile

    except UserProfile.DoesNotExist:

        return False

    role = profile.custom_role

    if not role:

        return False

    if not role.is_active:

        return False

    permission_query = {
        "codename": permission_codename,
    }

    if app_label:
        permission_query[
            "content_type__app_label"
        ] = app_label

    return role.permissions.filter(
        **permission_query
    ).exists()

# ADMIN ACCESS
# ============================================================

def admin_required(request):

    if request.user.is_superuser:

        return True

    try:

        profile = request.user.profile

    except UserProfile.DoesNotExist:

        return False

    if profile.role == "ADMIN":

        return True

    return user_has_role_permission(
        request.user,
        "manage_staff"
    )


# ============================================================
# STAFF MANAGEMENT
# ============================================================

@login_required
def staff_management(request):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to manage staff."
        )

        return redirect_by_role(
            request.user
        )

    staff_members = (
        User.objects
        .filter(
            profile__role__in=[
                "ADMIN",
                "STAFF"
            ]
        )
        .select_related(
            "profile",
            "profile__department",
            "profile__custom_role"
        )
        .order_by(
            "first_name",
            "last_name",
            "username"
        )
    )

    return render(
        request,
        "accounts/staff_management.html",
        {
            "staff_members":
                staff_members,
        }
    )


# ============================================================
# ADD STAFF
# ============================================================

@login_required
def add_staff(request):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to add staff."
        )

        return redirect_by_role(request.user)

    departments = (
        Department.objects
        .filter(is_active=True)
        .order_by("name")
    )

    roles = (
        Role.objects
        .filter(is_active=True)
        .order_by("name")
    )

    groups = (
        Group.objects
        .all()
        .order_by("name")
    )

    if request.method == "POST":

        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        job_title = request.POST.get("job_title", "").strip()

        department_id = request.POST.get("department")
        role_id = request.POST.get("custom_role")
        group_id = request.POST.get("group")

        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        def form_context():
            return {
                "departments": departments,
                "roles": roles,
                "groups": groups,
            }

        if not first_name or not last_name:

            messages.error(
                request,
                "First name and last name are required."
            )

            return render(
                request,
                "accounts/add_staff.html",
                form_context()
            )

        if not username:

            messages.error(
                request,
                "Username is required."
            )

            return render(
                request,
                "accounts/add_staff.html",
                form_context()
            )

        if not password:

            messages.error(
                request,
                "Password is required."
            )

            return render(
                request,
                "accounts/add_staff.html",
                form_context()
            )

        if password != confirm_password:

            messages.error(
                request,
                "Passwords do not match."
            )

            return render(
                request,
                "accounts/add_staff.html",
                form_context()
            )

        candidate_user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )
        try:
            validate_password(password, user=candidate_user)
        except ValidationError as exc:
            for error in exc.messages:
                messages.error(request, error)
            return render(
                request,
                "accounts/add_staff.html",
                form_context()
            )

        if User.objects.filter(username=username).exists():

            messages.error(
                request,
                "That username already exists."
            )

            return render(
                request,
                "accounts/add_staff.html",
                form_context()
            )

        department = None

        if department_id:

            department = (
                Department.objects
                .filter(
                    id=department_id,
                    is_active=True
                )
                .first()
            )

        custom_role = None

        if role_id:

            custom_role = (
                Role.objects
                .filter(
                    id=role_id,
                    is_active=True
                )
                .first()
            )

        position = None

        if job_title:

            position = (
                JobPosition.objects
                .filter(
                    title__iexact=job_title
                )
                .first()
            )

        try:

            with transaction.atomic():

                employee_number = generate_employee_number()

                while (
                    Employee.objects
                    .filter(employee_number=employee_number)
                    .exists()
                    or UserProfile.objects
                    .filter(employee_number=employee_number)
                    .exists()
                    or User.objects
                    .filter(username=employee_number)
                    .exists()
                ):

                    employee_number = generate_employee_number()

                employee = Employee.objects.create(
                    employee_number=employee_number,
                    first_name=first_name,
                    last_name=last_name,
                    phone=phone,
                    email=email,
                    department=department,
                    position=position,
                    employment_status="ACTIVE",
                    is_active=True,
                )

                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name
                )

                user.is_active = True

                user.save(
                    update_fields=[
                        "is_active"
                    ]
                )

                profile = UserProfile.objects.create(
                    user=user,
                    employee=employee,
                    role="STAFF",
                    custom_role=custom_role,
                    employee_number=employee_number,
                    phone=phone,
                    job_title=job_title,
                    department=department,
                    is_active=True
                )

                if group_id:

                    group = (
                        Group.objects
                        .filter(id=group_id)
                        .first()
                    )

                    if group:

                        user.groups.add(group)

            messages.success(
                request,
                f"Staff member created successfully. "
                f"{user.get_full_name() or user.username} "
                f"has been added to Staff Management and HR & Payroll. "
                f"Employee Number: {employee_number}"
            )

            return redirect(
                "accounts:staff_management"
            )

        except IntegrityError:

            messages.error(
                request,
                "The staff account could not be created. "
                "Please try again."
            )

    return render(
        request,
        "accounts/add_staff.html",
        {
            "departments": departments,
            "roles": roles,
            "groups": groups,
        }
    )


# ============================================================
# VIEW STAFF
# ============================================================

@login_required
def view_staff(
    request,
    user_id
):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to view staff details."
        )

        return redirect_by_role(
            request.user
        )

    staff = get_object_or_404(
        User.objects.select_related(
            "profile",
            "profile__department",
            "profile__custom_role"
        ).prefetch_related(
            "groups"
        ),
        id=user_id
    )

    profile = get_object_or_404(
        UserProfile,
        user=staff
    )

    return render(
        request,
        "accounts/view_staff.html",
        {
            "staff": staff,
            "profile": profile,
        }
    )


# ============================================================
# EDIT STAFF
# ============================================================

@login_required
def edit_staff(
    request,
    user_id
):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to edit staff."
        )

        return redirect_by_role(
            request.user
        )

    staff = get_object_or_404(
        User,
        id=user_id
    )

    profile = get_object_or_404(
        UserProfile,
        user=staff
    )

    departments = (
        Department.objects
        .filter(is_active=True)
        .order_by("name")
    )

    roles = (
        Role.objects
        .filter(is_active=True)
        .order_by("name")
    )

    groups = (
        Group.objects
        .all()
        .order_by("name")
    )

    if request.method == "POST":

        first_name = request.POST.get(
            "first_name",
            ""
        ).strip()

        last_name = request.POST.get(
            "last_name",
            ""
        ).strip()

        email = request.POST.get(
            "email",
            ""
        ).strip()

        phone = request.POST.get(
            "phone",
            ""
        ).strip()

        job_title = request.POST.get(
            "job_title",
            ""
        ).strip()

        if not first_name or not last_name:

            messages.error(
                request,
                "First name and last name are required."
            )

            return render(
                request,
                "accounts/edit_staff.html",
                {
                    "staff": staff,
                    "profile": profile,
                    "departments": departments,
                    "roles": roles,
                    "groups": groups,
                }
            )

        staff.first_name = first_name
        staff.last_name = last_name
        staff.email = email

        staff.save()

        profile.phone = phone
        profile.job_title = job_title

        department_id = request.POST.get(
            "department"
        )

        if department_id:

            profile.department = (
                Department.objects
                .filter(
                    id=department_id,
                    is_active=True
                )
                .first()
            )

        else:

            profile.department = None

        role_id = request.POST.get(
            "custom_role"
        )

        if role_id:

            profile.custom_role = (
                Role.objects
                .filter(
                    id=role_id,
                    is_active=True
                )
                .first()
            )

        else:

            profile.custom_role = None

        profile.save()

        group_id = request.POST.get(
            "group"
        )

        staff.groups.clear()

        if group_id:

            group = (
                Group.objects
                .filter(id=group_id)
                .first()
            )

            if group:

                staff.groups.add(group)

        messages.success(
            request,
            f"{staff.get_full_name() or staff.username} "
            "staff information updated successfully."
        )

        return redirect(
            "accounts:staff_management"
        )

    return render(
        request,
        "accounts/edit_staff.html",
        {
            "staff": staff,
            "profile": profile,
            "departments": departments,
            "roles": roles,
            "groups": groups,
        }
    )


# ============================================================
# DELETE STAFF
# ============================================================

@login_required
def delete_staff(
    request,
    user_id
):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to delete staff."
        )

        return redirect_by_role(
            request.user
        )

    staff = get_object_or_404(
        User,
        id=user_id
    )

    if staff == request.user:

        messages.error(
            request,
            "You cannot delete your own account."
        )

        return redirect(
            "accounts:staff_management"
        )

    staff_name = (
        staff.get_full_name()
        or staff.username
    )

    if request.method != "POST":

        messages.error(
            request,
            "Invalid request. Staff accounts can only be deleted using the delete button."
        )

        return redirect(
            "accounts:staff_management"
        )

    try:

        with transaction.atomic():

            staff.delete()

        messages.success(
            request,
            f"{staff_name} was deleted successfully."
        )

    except IntegrityError:

        messages.error(
            request,
            f"{staff_name} could not be deleted because "
            "the account is linked to other records."
        )

    return redirect(
        "accounts:staff_management"
    )


# ============================================================
# TOGGLE STAFF STATUS
# ============================================================

@login_required
def toggle_staff_status(
    request,
    user_id
):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to change staff status."
        )

        return redirect_by_role(
            request.user
        )

    user = get_object_or_404(
        User,
        id=user_id
    )

    profile = get_object_or_404(
        UserProfile,
        user=user
    )

    if user == request.user:

        messages.error(
            request,
            "You cannot deactivate your own account."
        )

        return redirect(
            "accounts:staff_management"
        )

    if request.method != "POST":

        messages.error(
            request,
            "Invalid request."
        )

        return redirect(
            "accounts:staff_management"
        )

    user.is_active = not user.is_active

    user.save(
        update_fields=[
            "is_active"
        ]
    )

    profile.is_active = user.is_active

    profile.save(
        update_fields=[
            "is_active"
        ]
    )

    # --------------------------------------------------------
    # SYNC HR & PAYROLL EMPLOYEE STATUS
    # --------------------------------------------------------
    employee = getattr(profile, "employee", None)

    if employee:
        employee.is_active = user.is_active
        employee.save(
            update_fields=[
                "is_active"
            ]
        )

    if user.is_active:

        messages.success(
            request,
            f"{user.get_full_name() or user.username} "
            "has been activated."
        )

    else:

        messages.success(
            request,
            f"{user.get_full_name() or user.username} "
            "has been deactivated."
        )

    return redirect(
        "accounts:staff_management"
    )


# ============================================================
# DEPARTMENT MANAGEMENT
# ============================================================

@login_required
def department_management(request):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to manage departments."
        )

        return redirect_by_role(
            request.user
        )

    departments = (
        Department.objects
        .all()
        .order_by("name")
    )

    return render(
        request,
        "accounts/department_management.html",
        {
            "departments": departments,
        }
    )


# ============================================================
# ADD DEPARTMENT
# ============================================================

@login_required
def add_department(request):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to add departments."
        )

        return redirect_by_role(
            request.user
        )

    if request.method == "POST":

        name = request.POST.get(
            "name",
            ""
        ).strip()

        description = request.POST.get(
            "description",
            ""
        ).strip()

        if not name:

            messages.error(
                request,
                "Department name is required."
            )

            return render(
                request,
                "accounts/add_department.html"
            )

        if Department.objects.filter(
            name__iexact=name
        ).exists():

            messages.error(
                request,
                "That department already exists."
            )

            return render(
                request,
                "accounts/add_department.html"
            )

        Department.objects.create(
            name=name,
            description=description,
            is_active=True
        )

        messages.success(
            request,
            f"{name} department was created successfully."
        )

        return redirect(
            "accounts:department_management"
        )

    return render(
        request,
        "accounts/add_department.html"
    )


# ============================================================
# EDIT DEPARTMENT
# ============================================================

@login_required
def edit_department(
    request,
    department_id
):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to edit departments."
        )

        return redirect_by_role(
            request.user
        )

    department = get_object_or_404(
        Department,
        id=department_id
    )

    if request.method == "POST":

        name = request.POST.get(
            "name",
            ""
        ).strip()

        description = request.POST.get(
            "description",
            ""
        ).strip()

        if not name:

            messages.error(
                request,
                "Department name is required."
            )

            return render(
                request,
                "accounts/edit_department.html",
                {
                    "department": department,
                }
            )

        duplicate = (
            Department.objects
            .filter(name__iexact=name)
            .exclude(id=department.id)
            .exists()
        )

        if duplicate:

            messages.error(
                request,
                "Another department already has that name."
            )

            return render(
                request,
                "accounts/edit_department.html",
                {
                    "department": department,
                }
            )

        department.name = name
        department.description = description

        department.save()

        messages.success(
            request,
            "Department updated successfully."
        )

        return redirect(
            "accounts:department_management"
        )

    return render(
        request,
        "accounts/edit_department.html",
        {
            "department": department,
        }
    )


# ============================================================
# TOGGLE DEPARTMENT STATUS
# ============================================================

@login_required
def toggle_department_status(
    request,
    department_id
):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to change department status."
        )

        return redirect_by_role(
            request.user
        )

    department = get_object_or_404(
        Department,
        id=department_id
    )

    if request.method != "POST":

        return redirect(
            "accounts:department_management"
        )

    department.is_active = not department.is_active

    department.save(
        update_fields=[
            "is_active"
        ]
    )

    if department.is_active:

        messages.success(
            request,
            f"{department.name} has been activated."
        )

    else:

        messages.success(
            request,
            f"{department.name} has been deactivated."
        )

    return redirect(
        "accounts:department_management"
    )


# ============================================================
# ROLE MANAGEMENT
# ============================================================

@login_required
def role_management(request):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to manage roles."
        )

        return redirect_by_role(
            request.user
        )

    roles = (
        Role.objects
        .prefetch_related(
            "permissions",
            "staff_members"
        )
        .order_by("name")
    )

    return render(
        request,
        "accounts/role_management.html",
        {
            "roles": roles,
        }
    )


# ============================================================
# ADD ROLE
# ============================================================

@login_required
def add_role(request):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to add roles."
        )

        return redirect_by_role(
            request.user
        )

    permissions = (
        Permission.objects
        .select_related("content_type")
        .order_by(
            "content_type__app_label",
            "content_type__model",
            "codename"
        )
    )

    if request.method == "POST":

        name = request.POST.get(
            "name",
            ""
        ).strip()

        description = request.POST.get(
            "description",
            ""
        ).strip()

        permission_ids = request.POST.getlist(
            "permissions"
        )

        if not name:

            messages.error(
                request,
                "Role name is required."
            )

            return render(
                request,
                "accounts/add_role.html",
                {
                    "permissions": permissions,
                }
            )

        if Role.objects.filter(
            name__iexact=name
        ).exists():

            messages.error(
                request,
                "A role with that name already exists."
            )

            return render(
                request,
                "accounts/add_role.html",
                {
                    "permissions": permissions,
                }
            )

        try:

            with transaction.atomic():

                role = Role.objects.create(
                    name=name,
                    description=description,
                    is_active=True
                )

                selected_permissions = (
                    Permission.objects
                    .filter(id__in=permission_ids)
                )

                role.permissions.set(
                    selected_permissions
                )

            messages.success(
                request,
                f"{name} role was created successfully."
            )

            return redirect(
                "accounts:role_management"
            )

        except IntegrityError:

            messages.error(
                request,
                "The role could not be created."
            )

    return render(
        request,
        "accounts/add_role.html",
        {
            "permissions": permissions,
        }
    )


# ============================================================
# EDIT ROLE
# ============================================================

@login_required
def edit_role(
    request,
    role_id
):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to edit roles."
        )

        return redirect_by_role(
            request.user
        )

    # CORRECTED
    role = get_object_or_404(
        Role,
        id=role_id
    )

    permissions = (
        Permission.objects
        .select_related("content_type")
        .order_by(
            "content_type__app_label",
            "content_type__model",
            "codename"
        )
    )

    if request.method == "POST":

        name = request.POST.get(
            "name",
            ""
        ).strip()

        description = request.POST.get(
            "description",
            ""
        ).strip()

        permission_ids = request.POST.getlist(
            "permissions"
        )

        if not name:

            messages.error(
                request,
                "Role name is required."
            )

            return render(
                request,
                "accounts/edit_role.html",
                {
                    "role": role,
                    "permissions": permissions,
                }
            )

        duplicate = (
            Role.objects
            .filter(name__iexact=name)
            .exclude(id=role.id)
            .exists()
        )

        if duplicate:

            messages.error(
                request,
                "Another role already has that name."
            )

            return render(
                request,
                "accounts/edit_role.html",
                {
                    "role": role,
                    "permissions": permissions,
                }
            )

        try:

            with transaction.atomic():

                role.name = name
                role.description = description

                role.save()

                selected_permissions = (
                    Permission.objects
                    .filter(id__in=permission_ids)
                )

                role.permissions.set(
                    selected_permissions
                )

            messages.success(
                request,
                "Role and permissions updated successfully."
            )

            return redirect(
                "accounts:role_management"
            )

        except IntegrityError:

            messages.error(
                request,
                "The role could not be updated."
            )

    return render(
        request,
        "accounts/edit_role.html",
        {
            "role": role,
            "permissions": permissions,
        }
    )


# ============================================================
# TOGGLE ROLE STATUS
# ============================================================

@login_required
def toggle_role_status(
    request,
    role_id
):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to change role status."
        )

        return redirect_by_role(
            request.user
        )

    # CORRECTED
    role = get_object_or_404(
        Role,
        id=role_id
    )

    if request.method != "POST":

        return redirect(
            "accounts:role_management"
        )

    role.is_active = not role.is_active

    role.save(
        update_fields=[
            "is_active"
        ]
    )

    if role.is_active:

        messages.success(
            request,
            f"{role.name} has been activated."
        )

    else:

        messages.success(
            request,
            f"{role.name} has been deactivated."
        )

    return redirect(
        "accounts:role_management"
    )


# ============================================================


# ============================================================
# STAFF ROLE MANAGEMENT (SEPARATE FROM STAFF CREATION)
# ============================================================

@login_required
def staff_role_management(request):
    """Assign or change custom ERP roles for existing staff accounts."""
    if not admin_required(request):
        messages.error(request, "You do not have permission to assign staff roles.")
        return redirect_by_role(request.user)

    staff_profiles = (
        UserProfile.objects
        .filter(role="STAFF")
        .select_related("user", "department", "custom_role")
        .order_by("user__last_name", "user__first_name", "user__username")
    )
    unassigned_profiles = staff_profiles.filter(custom_role__isnull=True)
    assigned_profiles = staff_profiles.filter(custom_role__isnull=False)
    active_roles = Role.objects.filter(is_active=True).order_by("name")

    if request.method == "POST":
        profile_id = request.POST.get("profile_id", "").strip()
        role_id = request.POST.get("custom_role", "").strip()
        profile = get_object_or_404(UserProfile, id=profile_id, role="STAFF")

        if not role_id:
            profile.custom_role = None
            profile.save(update_fields=["custom_role"])
            messages.success(request, f"Role removed from {profile.user.get_full_name() or profile.user.username}. Their account remains a staff account.")
            return redirect("accounts:staff_role_management")

        selected_role = Role.objects.filter(id=role_id, is_active=True).first()
        if selected_role is None:
            messages.error(request, "Select a valid active role.")
            return redirect("accounts:staff_role_management")

        profile.custom_role = selected_role
        profile.save(update_fields=["custom_role"])
        messages.success(request, f"{selected_role.name} assigned to {profile.user.get_full_name() or profile.user.username}.")
        return redirect("accounts:staff_role_management")

    return render(request, "accounts/staff_role_management.html", {
        "unassigned_profiles": unassigned_profiles,
        "assigned_profiles": assigned_profiles,
        "active_roles": active_roles,
        "unassigned_count": unassigned_profiles.count(),
    })


# SCHOOL BRANDING MANAGEMENT
# ============================================================

@login_required
def branding_management(request):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to manage school branding."
        )

        return redirect_by_role(
            request.user
        )

    branding = (
        SchoolBranding.objects
        .order_by("-id")
        .first()
    )

    if not branding:

        branding = SchoolBranding.objects.create(
            school_name="Luhan School",
            motto="Igniting curiosity, fueling innovation",
            is_active=True
        )

    if request.method == "POST":

        branding.school_name = request.POST.get(
            "school_name",
            ""
        ).strip()

        branding.motto = request.POST.get(
            "motto",
            ""
        ).strip()

        branding.phone = request.POST.get(
            "phone",
            ""
        ).strip()

        branding.alternative_phone = request.POST.get(
            "alternative_phone",
            ""
        ).strip()

        branding.email = request.POST.get(
            "email",
            ""
        ).strip()

        branding.website = request.POST.get(
            "website",
            ""
        ).strip()

        branding.physical_address = request.POST.get(
            "physical_address",
            ""
        ).strip()

        branding.postal_address = request.POST.get(
            "postal_address",
            ""
        ).strip()

        branding.school_code = request.POST.get(
            "school_code",
            ""
        ).strip()

        branding.additional_information = request.POST.get(
            "additional_information",
            ""
        ).strip()

        if request.FILES.get("logo"):

            branding.logo = request.FILES["logo"]

        branding.is_active = (
            request.POST.get("is_active")
            == "on"
        )

        branding.save()

        messages.success(
            request,
            "School branding has been updated successfully."
        )

        return redirect(
            "accounts:branding_management"
        )

    return render(
        request,
        "accounts/branding_management.html",
        {
            "branding": branding,
        }
    )


# ============================================================
# SCHOOL BRANDING
# ============================================================

@login_required
def school_branding(request):

    if not admin_required(request):

        messages.error(
            request,
            "You do not have permission to manage school branding."
        )

        return redirect_by_role(
            request.user
        )

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    if not branding:

        branding = SchoolBranding.objects.create(
            school_name="Luhan School",
            motto="Igniting curiosity, fueling innovation",
            is_active=True
        )

    if request.method == "POST":

        branding.school_name = request.POST.get(
            "school_name",
            ""
        ).strip()

        branding.motto = request.POST.get(
            "motto",
            ""
        ).strip()

        branding.phone = request.POST.get(
            "phone",
            ""
        ).strip()

        branding.alternative_phone = request.POST.get(
            "alternative_phone",
            ""
        ).strip()

        branding.email = request.POST.get(
            "email",
            ""
        ).strip()

        branding.website = request.POST.get(
            "website",
            ""
        ).strip()

        branding.physical_address = request.POST.get(
            "physical_address",
            ""
        ).strip()

        branding.postal_address = request.POST.get(
            "postal_address",
            ""
        ).strip()

        branding.school_code = request.POST.get(
            "school_code",
            ""
        ).strip()

        branding.additional_information = request.POST.get(
            "additional_information",
            ""
        ).strip()

        branding.is_active = True

        if request.FILES.get("logo"):

            branding.logo = request.FILES["logo"]

        branding.save()

        messages.success(
            request,
            "School branding information updated successfully."
        )

        return redirect(
            "accounts:school_branding"
        )

    return render(
        request,
        "accounts/school_branding.html",
        {
            "branding": branding,
        }
    )

@login_required
def profile_settings(request):
    user = request.user

    if request.method == "POST":
        new_username = request.POST.get("username", "").strip()
        new_password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        if not new_username:
            messages.error(request, "Username cannot be empty.")
            return redirect("accounts:profile_settings")

        if User.objects.filter(username=new_username).exclude(id=user.id).exists():
            messages.error(request, "That username is already taken.")
            return redirect("accounts:profile_settings")

        password_changed = False

        if new_password:
            if new_password != confirm_password:
                messages.error(request, "The passwords do not match.")
                return redirect("accounts:profile_settings")

            try:
                validate_password(new_password, user=user)
            except ValidationError as exc:
                for error in exc.messages:
                    messages.error(request, error)
                return redirect("accounts:profile_settings")

            user.set_password(new_password)
            password_changed = True

        user.username = new_username
        user.save()

        if password_changed:
            login(request, user)

        messages.success(
            request,
            "Your username and password have been updated successfully."
        )

        return redirect("accounts:profile_settings")

    profile = getattr(user, "profile", None)

    return render(
        request,
        "accounts/profile_settings.html",
        {
            "user": user,
            "profile": profile,
        }
    )




# ========================================================
# SECURE ROLE-BASED LOGIN
# ========================================================

def _role_login(request, expected_role, template_name, portal_url):
    """
    Secure login handler.

    The credentials must be valid AND the user's actual
    account role must match the selected login portal.
    """

    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    if request.method == "POST":

        username = request.POST.get(
            "username",
            ""
        ).strip()

        password = request.POST.get(
            "password",
            ""
        )

        if not username or not password:
            messages.error(
                request,
                "Please enter your username and password."
            )

            return render(
                request,
                template_name,
                {
                    "branding": branding,
                    "role": expected_role,
                }
            )

        user = authenticate(
            request,
            username=username,
            password=password
        )

        # ----------------------------------------------------
        # INVALID CREDENTIALS
        # ----------------------------------------------------

        if user is None:
            messages.error(
                request,
                "Invalid login."
            )

            return render(
                request,
                template_name,
                {
                    "branding": branding,
                    "role": expected_role,
                }
            )

        # ----------------------------------------------------
        # INACTIVE ACCOUNT
        # ----------------------------------------------------

        if not user.is_active:
            messages.error(
                request,
                "Your account is inactive."
            )

            return render(
                request,
                template_name,
                {
                    "branding": branding,
                    "role": expected_role,
                }
            )

        # ----------------------------------------------------
        # GET ACTUAL ROLE FROM DATABASE
        # ----------------------------------------------------

        actual_role = None

        if user.is_superuser:

            actual_role = "ADMIN"

        else:

            try:
                profile = user.profile
            except UserProfile.DoesNotExist:
                profile = None

            if profile is not None:

                if not profile.is_active:
                    messages.error(
                        request,
                        "Your account is inactive."
                    )

                    return render(
                        request,
                        template_name,
                        {
                            "branding": branding,
                            "role": expected_role,
                        }
                    )

                actual_role = profile.role

        # ----------------------------------------------------
        # ROLE MISMATCH
        # ----------------------------------------------------

        if actual_role != expected_role:

            messages.error(
                request,
                "Invalid login."
            )

            return render(
                request,
                template_name,
                {
                    "branding": branding,
                    "role": expected_role,
                }
            )

        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        login(
            request,
            user
        )

        return redirect(
            portal_url
        )

    return render(
        request,
        template_name,
        {
            "branding": branding,
            "role": expected_role,
        }
    )


def admin_login(request):

    return _role_login(
        request=request,
        expected_role="ADMIN",
        template_name="accounts/admin_login.html",
        portal_url="accounts:admin_dashboard",
    )


def staff_login(request):

    return _role_login(
        request=request,
        expected_role="STAFF",
        template_name="accounts/staff_login.html",
        portal_url="accounts:staff_dashboard",
    )


def student_login(request):

    return _role_login(
        request=request,
        expected_role="STUDENT",
        template_name="accounts/student_login.html",
        portal_url="accounts:student_dashboard",
    )


def parent_login(request):

    return _role_login(
        request=request,
        expected_role="PARENT",
        template_name="accounts/parent_login.html",
        portal_url="accounts:parent_dashboard",
    )


# ========================================================
# STAFF TYPE SELECTION
# ========================================================

def staff_selection(request):
    """
    Allows staff members to choose between
    Teaching Staff and Support Staff login.
    """

    if request.user.is_authenticated:
        return redirect_by_role(request.user)

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    return render(
        request,
        "accounts/staff_selection.html",
        {
            "branding": branding,
        }
    )


def teaching_staff_login(request):
    return _role_login(
        request=request,
        expected_role="STAFF",
        template_name="accounts/teaching_staff_login.html",
        portal_url="accounts:staff_academic_portal",
    )


def support_staff_login(request):
    return _role_login(
        request=request,
        expected_role="STAFF",
        template_name="accounts/support_staff_login.html",
        portal_url="accounts:staff_dashboard",
    )


def _staff_details_context(request):
    departments = (
        Department.objects
        .filter(is_active=True)
        .order_by("name")
    )

    roles = (
        Role.objects
        .filter(is_active=True)
        .order_by("name")
    )

    groups = (
        Group.objects
        .all()
        .order_by("name")
    )

    return {
        "departments": departments,
        "roles": roles,
        "groups": groups,
    }


    
def _generate_staff_credentials():
    employee_number = generate_employee_number()

    while (
        Employee.objects.filter(
            employee_number=employee_number
        ).exists()
        or UserProfile.objects.filter(
            employee_number=employee_number
        ).exists()
        or User.objects.filter(
            username=employee_number
        ).exists()
    ):
        employee_number = generate_employee_number()

    username = employee_number

    candidate_user = User(username=username)
    alphabet = (
        "ABCDEFGHJKLMNPQRSTUVWXYZ"
        "abcdefghijkmnopqrstuvwxyz"
        "23456789!@#$%^&*-_"
    )

    password = None
    for _ in range(50):
        candidate = get_random_string(24, allowed_chars=alphabet)
        try:
            validate_password(candidate, user=candidate_user)
        except ValidationError:
            continue
        password = candidate
        break

    if password is None:
        raise RuntimeError(
            "Could not generate a password satisfying configured validators."
        )

    return employee_number, username, password

@login_required
def teaching_staff_details(request):
    if not admin_required(request):
        messages.error(
            request,
            "You do not have permission to add staff."
        )
        return redirect_by_role(request.user)

    if request.method == "POST":
        data = {
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "phone": request.POST.get("phone", "").strip(),
            "job_title": request.POST.get("job_title", "").strip(),
            "department": request.POST.get("department", "").strip(),
            "staff_type": "TEACHING",
        }

        if not data["first_name"] or not data["last_name"]:
            messages.error(
                request,
                "First name and last name are required."
            )
            return render(
                request,
                "accounts/teaching_staff_details.html",
                _staff_details_context(request)
            )

        employee_number, username, password = _generate_staff_credentials()
        data["employee_number"] = employee_number
        data["username"] = username
        data["password"] = password
        data["confirm_password"] = password

        request.session["staff_wizard"] = data
        request.session.modified = True

        return redirect("accounts:staff_role_assignment")

    context = _staff_details_context(request)
    context["staff_type"] = "TEACHING"

    return render(
        request,
        "accounts/teaching_staff_details.html",
        context
    )


@login_required
def support_staff_details(request):
    if not admin_required(request):
        messages.error(
            request,
            "You do not have permission to add staff."
        )
        return redirect_by_role(request.user)

    if request.method == "POST":
        data = {
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "phone": request.POST.get("phone", "").strip(),
            "job_title": request.POST.get("job_title", "").strip(),
            "department": request.POST.get("department", "").strip(),
            "staff_type": "SUPPORT",
        }

        if not data["first_name"] or not data["last_name"]:
            messages.error(
                request,
                "First name and last name are required."
            )
            return render(
                request,
                "accounts/support_staff_details.html",
                _staff_details_context(request)
            )

        employee_number, username, password = _generate_staff_credentials()
        data["employee_number"] = employee_number
        data["username"] = username
        data["password"] = password
        data["confirm_password"] = password

        request.session["staff_wizard"] = data
        request.session.modified = True

        return redirect("accounts:staff_role_assignment")

    context = _staff_details_context(request)
    context["staff_type"] = "SUPPORT"

    return render(
        request,
        "accounts/support_staff_details.html",
        context
    )

def staff_type_selection(request):
    if not admin_required(request):
        messages.error(
            request,
            "You do not have permission to add staff."
        )
        return redirect_by_role(request.user)

    branding = (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    return render(
        request,
        "accounts/staff_type_selection.html",
        {
            "branding": branding,
        }
    )

def _create_staff_from_wizard(data, custom_role, subject_ids=None):

    username = data["username"]
    password = data["password"]

    try:
        validate_password(
            password or "",
            user=User(
                username=username or "",
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
                email=data.get("email", ""),
            ),
        )
    except ValidationError as exc:
        raise IntegrityError(
            "The staff password failed the configured security rules. "
            "Restart staff registration and try again."
        ) from exc

    if User.objects.filter(username=username).exists():
        raise IntegrityError(
            f"The generated username {username} already exists."
        )

    employee_number = data.get("employee_number")

    if not employee_number:
        employee_number = generate_employee_number()

    if (
        Employee.objects.filter(
            employee_number=employee_number
        ).exists()
        or UserProfile.objects.filter(
            employee_number=employee_number
        ).exists()
    ):
        raise IntegrityError(
            f"The employee number {employee_number} already exists."
        )

    department = None

    if data.get("department"):
        department = (
            Department.objects
            .filter(
                id=data.get("department"),
                is_active=True
            )
            .first()
        )

    with transaction.atomic():

        user = User.objects.create_user(
            username=username,
            email=data.get("email", ""),
            password=password,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", "")
        )

        user.is_active = True
        user.save(update_fields=["is_active"])

        employee = Employee.objects.create(
            employee_number=employee_number,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            is_active=True
        )

        UserProfile.objects.create(
            user=user,
            role="STAFF",
            custom_role=custom_role,
            employee_number=employee_number,
            phone=data.get("phone", ""),
            job_title=data.get("job_title", ""),
            department=department,
            employee=employee,
            is_active=True
        )

        assigned_subject_names = []
        assigned_class_names = []
        class_teacher_names = []

        if data.get("staff_type") == "TEACHING":

            teacher = TimetableTeacher.objects.create(
                employee=employee,
                name=(
                    f"{data.get('first_name', '')} "
                    f"{data.get('last_name', '')}"
                ).strip(),
                employee_no=employee_number,
                phone=data.get("phone", ""),
                email=data.get("email", ""),
                is_active=True
            )

            effective_subject_ids = (
                subject_ids
                or data.get("subject_ids", [])
            )

            subjects = (
                TimetableSubject.objects
                .filter(
                    id__in=effective_subject_ids,
                    is_active=True
                )
                .order_by("name")
            )

            for subject in subjects:

                TimetableTeacherSubject.objects.get_or_create(
                    teacher=teacher,
                    subject=subject,
                    defaults={
                        "is_active": True
                    }
                )

                assigned_subject_names.append(
                    subject.name
                )

            # --------------------------------------------
            # TEACHER + SUBJECT + CLASS ASSIGNMENTS
            # --------------------------------------------

            teaching_assignments = data.get(
                "teaching_assignments",
                []
            )

            for assignment in teaching_assignments:

                subject = (
                    TimetableSubject.objects
                    .filter(
                        id=assignment.get("subject_id"),
                        is_active=True
                    )
                    .first()
                )

                class_name = (
                    assignment.get("class_name", "")
                    or ""
                ).strip()

                stream = (
                    assignment.get("stream", "")
                    or ""
                ).strip()

                if not subject or not class_name:
                    continue

                TimetableTeacherTeachingAssignment.objects.get_or_create(
                    teacher=teacher,
                    subject=subject,
                    class_name=class_name,
                    stream=stream or None,
                    defaults={
                        "is_active": True
                    }
                )

                display_class = class_name

                if stream:
                    display_class = (
                        f"{class_name} - {stream}"
                    )

                assigned_class_names.append(
                    f"{subject.name} -> {display_class}"
                )

                # ----------------------------------------
                # GENERAL CLASS ACCESS
                # ----------------------------------------

                TimetableTeacherClassAssignment.objects.get_or_create(
                    teacher=teacher,
                    class_name=class_name,
                    stream=stream or None,
                    defaults={
                        "is_class_teacher": False,
                        "is_active": True
                    }
                )

            # --------------------------------------------
            # CLASS TEACHER ASSIGNMENTS
            # --------------------------------------------

            class_teachers = data.get(
                "class_teachers",
                []
            )

            for assignment in class_teachers:

                class_name = (
                    assignment.get("class_name", "")
                    or ""
                ).strip()

                stream = (
                    assignment.get("stream", "")
                    or ""
                ).strip()

                if not class_name:
                    continue

                class_assignment, created = (
                    TimetableTeacherClassAssignment.objects.get_or_create(
                        teacher=teacher,
                        class_name=class_name,
                        stream=stream or None,
                        defaults={
                            "is_class_teacher": True,
                            "is_active": True
                        }
                    )
                )

                if not created:
                    class_assignment.is_class_teacher = True
                    class_assignment.is_active = True
                    class_assignment.save(
                        update_fields=[
                            "is_class_teacher",
                            "is_active"
                        ]
                    )

                display_class = class_name

                if stream:
                    display_class = (
                        f"{class_name} - {stream}"
                    )

                class_teacher_names.append(
                    display_class
                )

        return {
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
            "username": username,
            "password": password,
            "employee_number": employee_number,
            "role": custom_role.name if custom_role else "Unassigned",
            "staff_type": data.get("staff_type", ""),
            "subjects": assigned_subject_names,
            "classes": assigned_class_names,
            "class_teachers": class_teacher_names,
        }

@login_required
def staff_role_assignment(request):

    if not admin_required(request):
        messages.error(
            request,
            "You do not have permission to add staff."
        )
        return redirect_by_role(request.user)

    data = request.session.get("staff_wizard")

    if not data:
        messages.error(
            request,
            "Staff details were not found. Please start the staff registration again."
        )
        return redirect("accounts:staff_type_selection")

    roles = (
        Role.objects
        .filter(is_active=True)
        .order_by("name")
    )

    if request.method == "POST":

        role_id = request.POST.get("custom_role")

        custom_role = None
        if role_id:
            custom_role = (
                Role.objects
                .filter(id=role_id, is_active=True)
                .first()
            )
            if custom_role is None:
                messages.error(request, "The selected staff role is invalid or inactive.")
                return render(
                    request,
                    "accounts/staff_role_assignment.html",
                    {"data": data, "roles": roles},
                )
            data["custom_role"] = custom_role.id
            data["custom_role_name"] = custom_role.name
        else:
            data.pop("custom_role", None)
            data.pop("custom_role_name", None)

        request.session["staff_wizard"] = data
        request.session.modified = True

        if data.get("staff_type") == "TEACHING":
            return redirect(
                "accounts:staff_subject_assignment"
            )

        try:

            result = _create_staff_from_wizard(
                data,
                custom_role
            )

            request.session["staff_created"] = result
            request.session.pop("staff_wizard", None)
            request.session.modified = True

            messages.success(
                request,
                "Staff account created successfully. "
                "Open the staff creation success page to view the initial credentials."
            )

            return redirect(
                "accounts:staff_creation_success"
            )

        except IntegrityError as exc:

            messages.error(
                request,
                str(exc)
            )

    return render(
        request,
        "accounts/staff_role_assignment.html",
        {
            "data": data,
            "roles": roles,
        }
    )


@login_required
def staff_subject_assignment(request):

    if not admin_required(request):
        messages.error(
            request,
            "You do not have permission to assign subjects."
        )
        return redirect_by_role(request.user)

    data = request.session.get("staff_wizard")

    if not data:
        messages.error(
            request,
            "Staff details were not found. Please start the staff registration again."
        )
        return redirect("accounts:staff_type_selection")

    if data.get("staff_type") != "TEACHING":
        messages.error(
            request,
            "Subject assignment is only available for teaching staff."
        )
        return redirect(
            "accounts:staff_role_assignment"
        )

    subjects = (
        TimetableSubject.objects
        .filter(is_active=True)
        .order_by("name")
    )

    if request.method == "POST":

        subject_ids = request.POST.getlist("subjects")

        if not subject_ids:
            messages.error(
                request,
                "Please assign at least one subject to the teaching staff."
            )

            return render(
                request,
                "accounts/staff_subject_assignment.html",
                {
                    "data": data,
                    "subjects": subjects,
                }
            )

        valid_subject_ids = list(
            subjects
            .filter(id__in=subject_ids)
            .values_list("id", flat=True)
        )

        if not valid_subject_ids:
            messages.error(
                request,
                "The selected subjects are invalid."
            )

            return render(
                request,
                "accounts/staff_subject_assignment.html",
                {
                    "data": data,
                    "subjects": subjects,
                }
            )

        custom_role = None
        if data.get("custom_role"):
            custom_role = (
                Role.objects
                .filter(id=data.get("custom_role"), is_active=True)
                .first()
            )
            if custom_role is None:
                messages.error(request, "The saved role is no longer active. You may continue without a role.")
                data.pop("custom_role", None)
                data.pop("custom_role_name", None)
                request.session["staff_wizard"] = data
                request.session.modified = True

        try:

            result = _create_staff_from_wizard(
                data,
                custom_role,
                valid_subject_ids
            )

            request.session["staff_created"] = result
            request.session.pop("staff_wizard", None)
            request.session.modified = True

            messages.success(
                request,
                "Staff account created successfully. "
                "Open the staff creation success page to view the initial credentials."
            )

            return redirect(
                "accounts:staff_creation_success"
            )

        except IntegrityError as exc:

            messages.error(
                request,
                str(exc)
            )

    return render(
        request,
        "accounts/staff_subject_assignment.html",
        {
            "data": data,
            "subjects": subjects,
        }
    )


@login_required
def staff_class_assignment(request):

    if not admin_required(request):
        messages.error(
            request,
            "You do not have permission to assign teaching classes."
        )
        return redirect_by_role(request.user)

    data = request.session.get("staff_wizard")

    if not data:
        messages.error(
            request,
            "Staff details were not found. Please start the staff registration again."
        )
        return redirect("accounts:staff_type_selection")

    if data.get("staff_type") != "TEACHING":
        messages.error(
            request,
            "Class assignment is only available for teaching staff."
        )
        return redirect("accounts:staff_role_assignment")

    subject_ids = data.get("subject_ids", [])

    if not subject_ids:
        messages.error(
            request,
            "Please assign at least one subject first."
        )
        return redirect("accounts:staff_subject_assignment")

    selected_subjects = (
        TimetableSubject.objects
        .filter(
            id__in=subject_ids,
            is_active=True
        )
        .order_by("name")
    )

    class_pairs = list(
        Student.objects
        .values_list(
            "class_name",
            "stream"
        )
        .distinct()
        .order_by(
            "class_name",
            "stream"
        )
    )

    if request.method == "POST":

        assignment_values = request.POST.getlist(
            "teaching_assignments"
        )

        class_teacher_values = request.POST.getlist(
            "class_teachers"
        )

        parsed_assignments = []
        valid_assignment_count = 0

        for value in assignment_values:

            parts = value.split("|", 2)

            if len(parts) != 3:
                continue

            subject_id, class_name, stream = parts

            try:
                subject_id = int(subject_id)
            except (TypeError, ValueError):
                continue

            subject_exists = selected_subjects.filter(
                id=subject_id
            ).exists()

            if not subject_exists or not class_name:
                continue

            parsed_assignments.append({
                "subject_id": subject_id,
                "class_name": class_name,
                "stream": stream,
            })

            valid_assignment_count += 1

        if valid_assignment_count == 0:
            messages.error(
                request,
                "Please assign at least one subject to at least one class."
            )

            return render(
                request,
                "accounts/staff_class_assignment.html",
                {
                    "data": data,
                    "subjects": selected_subjects,
                    "class_pairs": class_pairs,
                    "selected_assignments": assignment_values,
                    "selected_class_teachers": class_teacher_values,
                }
            )

        valid_class_teachers = []

        for value in class_teacher_values:

            parts = value.split("|", 1)

            if len(parts) != 2:
                continue

            class_name, stream = parts

            pair_exists = any(
                pair[0] == class_name
                and (pair[1] or "") == (stream or "")
                for pair in class_pairs
            )

            if pair_exists:
                valid_class_teachers.append({
                    "class_name": class_name,
                    "stream": stream,
                })

        data["teaching_assignments"] = parsed_assignments
        data["class_teachers"] = valid_class_teachers

        request.session["staff_wizard"] = data
        request.session.modified = True

        custom_role = None
        if data.get("custom_role"):
            custom_role = (
                Role.objects
                .filter(id=data.get("custom_role"), is_active=True)
                .first()
            )
            if custom_role is None:
                messages.error(request, "The saved role is no longer active. The staff account will be created without a role.")
                data.pop("custom_role", None)
                data.pop("custom_role_name", None)

        try:

            result = _create_staff_from_wizard(
                data,
                custom_role
            )

            request.session["staff_created"] = result
            request.session.pop("staff_wizard", None)
            request.session.modified = True

            messages.success(
                request,
                "Teaching staff account, subjects, classes and class-teacher assignments created successfully."
            )

            return redirect(
                "accounts:staff_creation_success"
            )

        except IntegrityError as exc:

            messages.error(
                request,
                str(exc)
            )

    return render(
        request,
        "accounts/staff_class_assignment.html",
        {
            "data": data,
            "subjects": selected_subjects,
            "class_pairs": class_pairs,
        }
    )
@login_required
def staff_creation_success(request):

    if not admin_required(request):
        messages.error(
            request,
            "You do not have permission to view this page."
        )
        return redirect_by_role(request.user)

    staff = request.session.pop("staff_created", None)

    if not staff:
        messages.info(
            request,
            "No recent staff account creation was found."
        )
        return redirect("accounts:staff_management")

    response = render(

        request,
        "accounts/staff_creation_success.html",
        {
            "staff": staff,
        }
    )

    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"

    response["Pragma"] = "no-cache"

    response["Expires"] = "0"

    return response


























# ============================================================
# TEACHING STAFF PUBLISHED TIMETABLE
# ============================================================

@login_required
def staff_published_timetable(request):
    if not (
        is_admin_user(request.user)
        or user_has_role_permission(
            request.user,
            "view_timetablelesson",
            "timetable",
        )
    ):
        return redirect("accounts:staff_dashboard")


    from django.shortcuts import render
    from timetable.complete_timetable_system import (
        teacher_entries,
    )

    teacher = None

    try:

        profile = request.user.profile

        if profile.employee_id:

            teacher = getattr(
                profile.employee,
                "timetable_teacher",
                None,
            )

    except Exception:

        teacher = None

    entries = teacher_entries(
        teacher
    )

    return render(
        request,
        "accounts/staff_published_timetable.html",
        {
            "teacher": teacher,
            "timetable": entries,
        }
    )


# ============================================================
# STAFF MY TIMETABLE
# ============================================================

# ============================================================
# STAFF MY TIMETABLE
# ============================================================

@login_required
@role_permission_required(
    "view_timetablelesson",
    "timetable",
)
def staff_my_timetable(request):
    if not is_admin_user(request.user):
        profile = getattr(request.user, "profile", None)

        if not profile or profile.role != "STAFF":
            return redirect_by_role(request.user)

    """
    Secure teacher self-service timetable.

    The logged-in user is resolved through:
        UserProfile -> Employee -> TimetableTeacher

    Matching priority:
        1. Employee number
        2. Email
        3. Unique full name
    """

    from timetable.models import (
        TimetableTerm,
        TimetableTeacher,
        TimetableLesson,
        TimetableDay,
        TimetablePeriod,
    )

    # --------------------------------------------------------
    # Resolve logged-in staff member
    # --------------------------------------------------------

    profile = get_object_or_404(
        UserProfile.objects.select_related("employee"),
        user=request.user,
    )

    employee = profile.employee

    if not employee:
        messages.error(
            request,
            "Your account is not linked to an employee record."
        )
        return redirect("accounts:staff_dashboard")

    # --------------------------------------------------------
    # Resolve timetable teacher securely
    # --------------------------------------------------------

    teacher = None

    employee_number = (
        str(getattr(employee, "employee_number", "") or "")
        .strip()
    )

    employee_email = (
        str(getattr(employee, "email", "") or "")
        .strip()
        .lower()
    )

    if employee_number:
        teacher = (
            TimetableTeacher.objects
            .filter(
                active=True,
                staff_number__iexact=employee_number,
            )
            .first()
        )

    if teacher is None and employee_email:
        teacher = (
            TimetableTeacher.objects
            .filter(
                active=True,
                email__iexact=employee_email,
            )
            .first()
        )

    if teacher is None:
        first = str(getattr(employee, "first_name", "") or "").strip()
        middle = str(getattr(employee, "middle_name", "") or "").strip()
        last = str(getattr(employee, "last_name", "") or "").strip()

        full_name = " ".join(
            part for part in [first, middle, last] if part
        ).strip()

        if full_name:
            name_matches = list(
                TimetableTeacher.objects
                .filter(
                    active=True,
                    name__iexact=full_name,
                )[:2]
            )

            if len(name_matches) == 1:
                teacher = name_matches[0]

    # --------------------------------------------------------
    # No timetable teacher linked
    # --------------------------------------------------------

    if teacher is None:
        return render(
            request,
            "accounts/staff_my_timetable.html",
            {
                "branding": SchoolBranding.objects.filter(
                    is_active=True
                ).first(),
                "teacher": None,
                "terms": TimetableTerm.objects.filter(
                    active=True
                ).order_by(
                    "-academic_year",
                    "term_name",
                ),
                "academic_years": [],
                "selected_year": "",
                "selected_term_id": "",
                "timetable_rows": [],
                "error_message": (
                    "Your staff account is linked to an employee, "
                    "but no matching timetable teacher was found. "
                    "Please ask the administrator to check your "
                    "employee number, email, or timetable teacher record."
                ),
            },
        )

    # --------------------------------------------------------
    # Academic years
    # --------------------------------------------------------

    active_terms = (
        TimetableTerm.objects
        .filter(active=True)
        .order_by("-academic_year", "term_name")
    )

    academic_years = sorted(
        {
            term.academic_year
            for term in active_terms
            if term.academic_year
        },
        reverse=True,
    )

    selected_year = (
        request.POST.get("academic_year")
        or request.GET.get("academic_year")
        or (
            academic_years[0]
            if academic_years
            else ""
        )
    )

    # --------------------------------------------------------
    # Terms for selected academic year
    # --------------------------------------------------------

    terms = active_terms.filter(
        academic_year=selected_year
    )

    selected_term_id = (
        request.POST.get("term")
        or request.GET.get("term")
        or ""
    )

    selected_term = None

    if selected_term_id:
        selected_term = (
            terms.filter(pk=selected_term_id)
            .first()
        )

    # Automatically use first available term if nothing selected
    if selected_term is None and terms.exists():
        selected_term = terms.first()
        selected_term_id = str(selected_term.pk)

    # --------------------------------------------------------
    # Build teacher timetable
    # --------------------------------------------------------

    timetable_rows = []

    if selected_term:

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

        lessons = (
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
                "period__order",
                "id",
            )
        )

        lesson_map = {}

        for lesson in lessons:
            lesson_map[
                (lesson.day_id, lesson.period_id)
            ] = lesson

        for day in days:

            cells = []

            for period in periods:

                lesson = lesson_map.get(
                    (day.id, period.id)
                )

                cells.append(
                    {
                        "period": period,
                        "lesson": lesson,
                    }
                )

            timetable_rows.append(
                {
                    "day": day,
                    "cells": cells,
                }
            )

    context = {
        "branding": SchoolBranding.objects.filter(
            is_active=True
        ).first(),

        "teacher": teacher,

        "academic_years": academic_years,
        "selected_year": selected_year,

        "terms": terms,
        "selected_term_id": str(selected_term_id),

        "selected_term": selected_term,
        "timetable_rows": timetable_rows,
    }

    return render(
        request,
        "accounts/staff_my_timetable.html",
        context,
    )
























