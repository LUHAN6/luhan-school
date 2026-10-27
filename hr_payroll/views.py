from datetime import date
from django.db.models import Q
from decimal import Decimal
import calendar

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django import forms
from django.http import FileResponse, HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor, white
from django.apps import apps
from accounts.models import SchoolBranding
from accounts.views import user_has_role_permission
from accounts.staff_access import get_staff_teacher, role_permission_required

from .models import (
    Employee,
    Department,
    JobPosition,
    Attendance,
    LeaveType,
    LeaveApplication,
    EmployeeDocument,
    EmployeeExit,
    AllowanceType,
    EmployeeAllowance,
    DeductionType,
    PAYETaxBand,
    PAYERelief,
    NSSFRule,
    EmployeeDeduction,
    StaffLoan,
    LoanApplication,
    PayrollPeriod,
    PayrollRecord,
    Payslip,
    PerformanceAppraisal,
)


# ============================================================
# GENERIC MODEL FORM FACTORY
# ============================================================

def get_active_school_years():
    """
    Discover the project's school/academic year model and return
    active years configured by the administrator.

    The function supports common model naming conventions without
    hard-coding an app name.
    """

    preferred_names = {
        "academicyear",
        "schoolyear",
        "academicschoolyear",
        "schoolacademicyear",
        "academic_session",
        "academicsession",
    }

    candidates = []

    for model in apps.get_models():

        model_name = model.__name__.lower()

        field_names = {
            field.name.lower()
            for field in model._meta.get_fields()
            if hasattr(field, "name")
        }

        has_active = "is_active" in field_names
        has_year = "year" in field_names
        has_name = "name" in field_names

        if model_name in preferred_names and has_active:
            candidates.append(model)
            continue

        if has_active and has_year:
            candidates.append(model)
            continue

        if has_active and has_name and (
            "year" in model_name
            or "academic" in model_name
        ):
            candidates.append(model)

    if not candidates:
        return []

    # Prefer models whose names explicitly indicate school/academic years.
    candidates.sort(
        key=lambda model: (
            0 if model.__name__.lower() in preferred_names else 1,
            model.__name__,
        )
    )

    year_model = candidates[0]

    objects = year_model.objects.filter(
        is_active=True,
    ).order_by("-id")

    years = []

    for obj in objects:

        value = None

        field_names = {
            field.name.lower()
            for field in obj._meta.get_fields()
            if hasattr(field, "name")
        }

        if "year" in field_names:
            value = getattr(obj, "year", None)

        if value is None and hasattr(obj, "name"):
            raw_name = str(obj.name)

            # Extract a four-digit school year from the name.
            import re

            match = re.search(r"\b(20\d{2}|19\d{2})\b", raw_name)

            if match:
                value = int(match.group(1))

        if value is not None:

            try:
                year_value = int(value)
            except (TypeError, ValueError):
                continue

            if year_value not in years:
                years.append(year_value)

    return sorted(years, reverse=True)


def apply_hr_form_widgets(form_class, model):
    """
    Make HR forms user-friendly:
    - DateField -> browser calendar
    - DateTimeField -> browser date/time picker
    - BooleanField -> checkbox
    """

    for field_name, field in form_class.base_fields.items():

        model_field = model._meta.get_field(field_name)

        if model_field.get_internal_type() == "DateField":

            field.widget = forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "hr-date-field",
                },
                format="%Y-%m-%d",
            )

        elif model_field.get_internal_type() == "DateTimeField":

            field.widget = forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "hr-datetime-field",
                },
                format="%Y-%m-%dT%H:%M",
            )


def model_form(model, exclude=None, widgets=None):

    exclude = exclude or [
        "created_at",
        "updated_at",
        "uploaded_at",
        "processed_at",
        "generated_at",
        "sent_at",
    ]

    attrs = {
        "Meta": type(
            "Meta",
            (),
            {
                "model": model,
                "fields": "__all__",
                "exclude": exclude,
            },
        )
    }

    form_class = type(
        f"{model.__name__}Form",
        (forms.ModelForm,),
        attrs,
    )

    apply_hr_form_widgets(
        form_class,
        model,
    )

    if widgets:

        for field_name, widget in widgets.items():

            if field_name in form_class.base_fields:
                form_class.base_fields[
                    field_name
                ].widget = widget

    return form_class


    def clean(self):
        cleaned = super().clean()

        year = cleaned.get("year")
        month = cleaned.get("month")

        if year and month:
            import calendar

            first_day = date(
                int(year),
                int(month),
                1,
            )

            last_day = date(
                int(year),
                int(month),
                calendar.monthrange(
                    int(year),
                    int(month),
                )[1],
            )

            cleaned["start_date"] = first_day
            cleaned["end_date"] = last_day

        return cleaned
EmployeeForm = model_form(Employee)
DepartmentForm = model_form(Department)
JobPositionForm = model_form(JobPosition)
AttendanceForm = model_form(Attendance)
LeaveTypeForm = model_form(LeaveType)
LeaveApplicationForm = model_form(LeaveApplication)
EmployeeDocumentForm = model_form(EmployeeDocument)
EmployeeExitForm = model_form(EmployeeExit)

class PAYETaxBandForm(forms.ModelForm):

    class Meta:
        model = PAYETaxBand
        fields = [
            "name",
            "lower_limit",
            "upper_limit",
            "rate",
            "effective_from",
            "effective_to",
            "is_active",
        ]


class PAYEReliefForm(forms.ModelForm):

    class Meta:
        model = PAYERelief
        fields = [
            "name",
            "monthly_amount",
            "effective_from",
            "effective_to",
            "is_active",
        ]


class NSSFRuleForm(forms.ModelForm):

    class Meta:
        model = NSSFRule
        fields = [
            "name",
            "lower_limit",
            "upper_limit",
            "employee_percentage",
            "employee_cap",
            "effective_from",
            "effective_to",
            "is_active",
        ]


AllowanceTypeForm = model_form(AllowanceType)
EmployeeAllowanceForm = model_form(EmployeeAllowance)
class DeductionTypeForm(forms.ModelForm):

    class Meta:
        model = DeductionType
        fields = [
            "name",
            "code",
            "description",
            "is_statutory",
            "is_compulsory",
            "calculation_method",
            "calculation_base",
            "percentage",
            "fixed_amount",
            "minimum_amount",
            "maximum_amount",
            "effective_from",
            "effective_to",
            "is_active",
        ]

        widgets = {
            "percentage": forms.NumberInput(
                attrs={
                    "step": "0.0001",
                    "min": "0",
                }
            ),
            "fixed_amount": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "minimum_amount": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "maximum_amount": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "effective_from": forms.DateInput(
                attrs={"type": "date"}
            ),
            "effective_to": forms.DateInput(
                attrs={"type": "date"}
            ),
        }

    def clean(self):
        cleaned = super().clean()

        method = cleaned.get("calculation_method")
        percentage = cleaned.get("percentage") or Decimal("0.00")
        fixed_amount = cleaned.get("fixed_amount") or Decimal("0.00")
        minimum_amount = cleaned.get("minimum_amount") or Decimal("0.00")
        maximum_amount = cleaned.get("maximum_amount") or Decimal("0.00")

        if method == "PERCENTAGE" and percentage <= Decimal("0.00"):
            self.add_error(
                "percentage",
                "Enter a percentage greater than zero."
            )

        if method == "FIXED" and fixed_amount < Decimal("0.00"):
            self.add_error(
                "fixed_amount",
                "Fixed amount cannot be negative."
            )

        if maximum_amount > Decimal("0.00") and (
            minimum_amount > maximum_amount
        ):
            self.add_error(
                "maximum_amount",
                "Maximum amount cannot be lower than minimum amount."
            )

        return cleaned
EmployeeDeductionForm = model_form(EmployeeDeduction)
StaffLoanForm = model_form(StaffLoan)

# ============================================================
# STAFF SELF-SERVICE LEAVE FORM
# ============================================================

class StaffLeaveApplicationForm(forms.ModelForm):

    class Meta:
        model = LeaveApplication
        fields = [
            "leave_type",
            "start_date",
            "end_date",
            "reason",
        ]
        widgets = {
            "leave_type": forms.Select(
                attrs={
                    "class": "form-select",
                }
            ),
            "start_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
            "end_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
            "reason": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Enter the reason for your leave application.",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["leave_type"].queryset = (
            LeaveType.objects
            .filter(is_active=True)
            .order_by("name")
        )

    def clean(self):
        cleaned = super().clean()

        start_date = cleaned.get("start_date")
        end_date = cleaned.get("end_date")

        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError(
                "Leave end date cannot be before the start date."
            )

        return cleaned

PerformanceAppraisalForm = model_form(PerformanceAppraisal)


class PayrollPeriodForm(
    forms.ModelForm
):

    MONTH_CHOICES = [
        (1, "January"),
        (2, "February"),
        (3, "March"),
        (4, "April"),
        (5, "May"),
        (6, "June"),
        (7, "July"),
        (8, "August"),
        (9, "September"),
        (10, "October"),
        (11, "November"),
        (12, "December"),
    ]

    year = forms.TypedChoiceField(
        choices=[],
        coerce=int,
        empty_value=None,
        label="Payroll Year",
    )

    month = forms.TypedChoiceField(
        choices=MONTH_CHOICES,
        coerce=int,
        label="Payroll Month",
    )

    class Meta:
        model = PayrollPeriod
        fields = "__all__"
        exclude = [
            "created_at",
            "processed_at",
        ]

        widgets = {
            "start_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "hr-date-field",
                },
                format="%Y-%m-%d",
            ),

            "end_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "hr-date-field",
                },
                format="%Y-%m-%d",
            ),
        }

    def __init__(
        self,
        *args,
        **kwargs,
    ):

        super().__init__(
            *args,
            **kwargs,
        )

        active_years = get_active_school_years()

        self.fields["year"].choices = [
            ("", "Select active school year")
        ] + [
            (year, str(year))
            for year in active_years
        ]

        self.fields["name"].required = False
        self.fields["start_date"].required = False
        self.fields["end_date"].required = False
        self.fields["status"].required = False
        self.fields["start_date"].input_formats = [
            "%Y-%m-%d"
        ]

        self.fields["end_date"].input_formats = [
            "%Y-%m-%d"
        ]
    def clean(self):
        cleaned = super().clean()

        year = cleaned.get("year")
        month = cleaned.get("month")

        if year and month:
            import calendar

            first_day = date(
                int(year),
                int(month),
                1,
            )

            last_day = date(
                int(year),
                int(month),
                calendar.monthrange(
                    int(year),
                    int(month),
                )[1],
            )

            cleaned["start_date"] = first_day
            cleaned["end_date"] = last_day

        return cleaned
EmployeeForm = model_form(Employee)
DepartmentForm = model_form(Department)
JobPositionForm = model_form(JobPosition)
AttendanceForm = model_form(Attendance)
LeaveTypeForm = model_form(LeaveType)
LeaveApplicationForm = model_form(LeaveApplication)
EmployeeDocumentForm = model_form(EmployeeDocument)
EmployeeExitForm = model_form(EmployeeExit)
AllowanceTypeForm = model_form(AllowanceType)
EmployeeAllowanceForm = model_form(EmployeeAllowance)
class DeductionTypeForm(forms.ModelForm):

    class Meta:
        model = DeductionType
        fields = [
            "name",
            "code",
            "description",
            "is_statutory",
            "is_compulsory",
            "calculation_method",
            "calculation_base",
            "percentage",
            "fixed_amount",
            "minimum_amount",
            "maximum_amount",
            "effective_from",
            "effective_to",
            "is_active",
        ]

        widgets = {
            "percentage": forms.NumberInput(
                attrs={
                    "step": "0.0001",
                    "min": "0",
                }
            ),
            "fixed_amount": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "minimum_amount": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "maximum_amount": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),
            "effective_from": forms.DateInput(
                attrs={"type": "date"}
            ),
            "effective_to": forms.DateInput(
                attrs={"type": "date"}
            ),
        }

    def clean(self):
        cleaned = super().clean()

        method = cleaned.get("calculation_method")
        percentage = cleaned.get("percentage") or Decimal("0.00")
        fixed_amount = cleaned.get("fixed_amount") or Decimal("0.00")
        minimum_amount = cleaned.get("minimum_amount") or Decimal("0.00")
        maximum_amount = cleaned.get("maximum_amount") or Decimal("0.00")

        if method == "PERCENTAGE" and percentage <= Decimal("0.00"):
            self.add_error(
                "percentage",
                "Enter a percentage greater than zero."
            )

        if method == "FIXED" and fixed_amount < Decimal("0.00"):
            self.add_error(
                "fixed_amount",
                "Fixed amount cannot be negative."
            )

        if maximum_amount > Decimal("0.00") and (
            minimum_amount > maximum_amount
        ):
            self.add_error(
                "maximum_amount",
                "Maximum amount cannot be lower than minimum amount."
            )

        return cleaned
EmployeeDeductionForm = model_form(EmployeeDeduction)
StaffLoanForm = model_form(StaffLoan)
PerformanceAppraisalForm = model_form(PerformanceAppraisal)


# ============================================================
# COMMON FORM VIEW
# ============================================================

def form_page(
    request,
    form_class,
    title,
    success_url,
    instance=None,
    template="hr_payroll/form.html",
    form_kwargs=None,
    success_url_kwargs=None,
    success_message=None,
):
    form_kwargs = form_kwargs or {}
    success_url_kwargs = success_url_kwargs or {}

    if request.method == "POST":
        form = form_class(
            request.POST,
            request.FILES,
            instance=instance,
            **form_kwargs,
        )

        if form.is_valid():
            obj = form.save()

            messages.success(
                request,
                success_message or f"{title} saved successfully.",
            )

            return redirect(
                success_url,
                **success_url_kwargs,
            )

    else:
        form = form_class(
            instance=instance,
            **form_kwargs,
        )

    return render(
        request,
        template,
        {
            "form": form,
            "title": title,
            "cancel_url": success_url,
            "cancel_url_kwargs": success_url_kwargs,
        },
    )


# ============================================================
# DASHBOARD
# ============================================================

@login_required
@role_permission_required("view_employee", "hr_payroll")
def hr_payroll_dashboard(request):

    total_employees = Employee.objects.count()

    active_employees = Employee.objects.filter(
        employment_status="ACTIVE",
        is_active=True,
    ).count()

    inactive_employees = Employee.objects.exclude(
        employment_status="ACTIVE",
    ).count()

    total_departments = Department.objects.filter(
        is_active=True,
    ).count()

    active_loans = StaffLoan.objects.filter(
        status="ACTIVE",
    ).count()

    context = {
        "total_employees": total_employees,
        "active_employees": active_employees,
        "inactive_employees": inactive_employees,
        "total_departments": total_departments,
        "active_loans": active_loans,
    }

    return render(
        request,
        "hr_payroll/dashboard.html",
        context,
    )


# ============================================================
# EMPLOYEES
# ============================================================

@login_required
@role_permission_required("view_employee", "hr_payroll")
def employee_list(request):

    employees = Employee.objects.select_related(
        "department",
        "position",
    ).order_by(
        "first_name",
        "last_name",
    )

    return render(
        request,
        "hr_payroll/employee_list.html",
        {
            "employees": employees,
            "employee_count": employees.count(),
        },
    )


@login_required
@role_permission_required("view_employee", "hr_payroll")
def employee_detail(request, pk):

    employee = get_object_or_404(
        Employee.objects.select_related(
            "department",
            "position",
        ),
        pk=pk,
    )

    return render(
        request,
        "hr_payroll/employee_detail.html",
        {"employee": employee},
    )


@login_required
@role_permission_required("add_employee", "hr_payroll")
def employee_add(request):
    return form_page(
        request,
        EmployeeForm,
        "Add Employee",
        "hr_payroll:employee_list",
    )


@login_required
@role_permission_required("change_employee", "hr_payroll")
def employee_edit(request, pk):
    employee = get_object_or_404(Employee, pk=pk)

    return form_page(
        request,
        EmployeeForm,
        "Edit Employee",
        "hr_payroll:employee_detail",
        instance=employee,
        success_url_kwargs={
            "pk": employee.pk,
        },
    )


@login_required
@role_permission_required("change_employee", "hr_payroll")
def employee_deactivate(request, pk):
    employee = get_object_or_404(Employee, pk=pk)

    if request.method == "POST":
        employee.is_active = False

        if hasattr(employee, "employment_status"):
            employee.employment_status = "INACTIVE"

        employee.save()

        messages.success(
            request,
            f"{employee.full_name} has been deactivated.",
        )

    return redirect(
        "hr_payroll:employee_detail",
        pk=employee.pk,
    )


# ============================================================
# DEPARTMENTS
# ============================================================

@login_required
@role_permission_required("view_department", "hr_payroll")
def department_list(request):

    departments = Department.objects.order_by("name")

    return render(
        request,
        "hr_payroll/department_list.html",
        {"departments": departments},
    )


@login_required
@role_permission_required("add_department", "hr_payroll")
def department_add(request):
    return form_page(
        request,
        DepartmentForm,
        "Add Department",
        "hr_payroll:department_list",
    )


@login_required
@role_permission_required("change_department", "hr_payroll")
def department_edit(request, pk):
    obj = get_object_or_404(Department, pk=pk)

    return form_page(
        request,
        DepartmentForm,
        "Edit Department",
        "hr_payroll:department_list",
        instance=obj,
    )


# ============================================================
# JOB POSITIONS
# ============================================================

@login_required
@role_permission_required("view_jobposition", "hr_payroll")
def position_list(request):

    positions = JobPosition.objects.select_related(
        "department",
    ).order_by("title")

    return render(
        request,
        "hr_payroll/position_list.html",
        {
            "positions": positions,
            "position_count": positions.count(),
        },
    )


@login_required
@role_permission_required("add_jobposition", "hr_payroll")
def position_add(request):
    return form_page(
        request,
        JobPositionForm,
        "Add Job Position",
        "hr_payroll:position_list",
    )


@login_required
@role_permission_required("change_jobposition", "hr_payroll")
def position_edit(request, pk):
    obj = get_object_or_404(JobPosition, pk=pk)

    return form_page(
        request,
        JobPositionForm,
        "Edit Job Position",
        "hr_payroll:position_list",
        instance=obj,
    )


# ============================================================
# ATTENDANCE
# ============================================================

@login_required
@role_permission_required("view_attendance", "hr_payroll")
def attendance_list(request):

    attendance_records = Attendance.objects.select_related(
        "employee",
    ).order_by(
        "-date",
        "employee__first_name",
    )

    return render(
        request,
        "hr_payroll/attendance_list.html",
        {"attendance_records": attendance_records},
    )


@login_required
@role_permission_required("add_attendance", "hr_payroll")
def attendance_add(request):
    return form_page(
        request,
        AttendanceForm,
        "Record Staff Attendance",
        "hr_payroll:attendance_list",
    )


@login_required
@role_permission_required("change_attendance", "hr_payroll")
def attendance_edit(request, pk):
    obj = get_object_or_404(Attendance, pk=pk)

    return form_page(
        request,
        AttendanceForm,
        "Edit Staff Attendance",
        "hr_payroll:attendance_list",
        instance=obj,
    )


@login_required
@role_permission_required("delete_attendance", "hr_payroll")
def attendance_delete(request, pk):
    obj = get_object_or_404(Attendance, pk=pk)

    if request.method == "POST":
        obj.delete()
        messages.success(
            request,
            "Attendance record deleted successfully.",
        )
        return redirect("hr_payroll:attendance_list")

    return render(
        request,
        "hr_payroll/confirm_delete.html",
        {
            "object": obj,
            "title": "Delete Attendance Record",
            "cancel_url": "hr_payroll:attendance_list",
        },
    )


# ============================================================
# LEAVE TYPES
# ============================================================

@login_required
@role_permission_required("view_leavetype", "hr_payroll")
def leave_type_list(request):

    leave_types = LeaveType.objects.order_by("name")

    return render(
        request,
        "hr_payroll/leave_type_list.html",
        {"leave_types": leave_types},
    )


@login_required
@role_permission_required("add_leavetype", "hr_payroll")
def leave_type_add(request):
    return form_page(
        request,
        LeaveTypeForm,
        "Add Leave Type",
        "hr_payroll:leave_type_list",
    )


# ============================================================
# LEAVE APPLICATIONS
# ============================================================

@login_required
@role_permission_required("view_leaveapplication", "hr_payroll")
def leave_list(request):

    leave_applications = LeaveApplication.objects.select_related(
        "employee",
        "leave_type",
        "approved_by",
    ).order_by(
        "-created_at",
    )

    return render(
        request,
        "hr_payroll/leave_list.html",
        {"leave_applications": leave_applications},
    )


@login_required
@role_permission_required("add_leaveapplication", "hr_payroll")
def leave_add(request):

    return form_page(
        request,
        LeaveApplicationForm,
        "Apply for Leave",
        "hr_payroll:leave_list",
    )


@login_required
@role_permission_required("change_leaveapplication", "hr_payroll")
def leave_approve(request, pk):

    application = get_object_or_404(
        LeaveApplication,
        pk=pk,
    )

    if request.method == "POST":

        application.status = "APPROVED"
        application.approved_at = timezone.now()

        approver = Employee.objects.filter(
            is_active=True,
        ).first()

        if approver:
            application.approved_by = approver

        application.save()

        messages.success(
            request,
            "Leave application approved.",
        )

    return redirect("hr_payroll:leave_list")


@login_required
@role_permission_required("change_leaveapplication", "hr_payroll")
def leave_reject(request, pk):

    application = get_object_or_404(
        LeaveApplication,
        pk=pk,
    )

    if request.method == "POST":

        application.status = "REJECTED"
        application.approved_at = None
        application.approved_by = None
        application.save()

        messages.success(
            request,
            "Leave application rejected.",
        )

    return redirect("hr_payroll:leave_list")


@login_required
@role_permission_required("change_leaveapplication", "hr_payroll")
def leave_cancel(request, pk):

    application = get_object_or_404(
        LeaveApplication,
        pk=pk,
    )

    if request.method == "POST":

        application.status = "CANCELLED"
        application.save()

        messages.success(
            request,
            "Leave application cancelled.",
        )

    return redirect("hr_payroll:leave_list")


# ============================================================
# DOCUMENTS
# ============================================================

@login_required
@role_permission_required("view_employeedocument", "hr_payroll")
def document_list(request):

    documents = EmployeeDocument.objects.select_related(
        "employee",
    ).order_by(
        "-uploaded_at",
    )

    return render(
        request,
        "hr_payroll/document_list.html",
        {"documents": documents},
    )


@login_required
@role_permission_required("add_employeedocument", "hr_payroll")
def document_add(request):
    return form_page(
        request,
        EmployeeDocumentForm,
        "Upload Employee Document",
        "hr_payroll:document_list",
    )


@login_required
@role_permission_required("delete_employeedocument", "hr_payroll")
def document_delete(request, pk):

    document = get_object_or_404(
        EmployeeDocument,
        pk=pk,
    )

    if request.method == "POST":
        document.delete()

        messages.success(
            request,
            "Employee document deleted.",
        )

        return redirect(
            "hr_payroll:document_list",
        )

    return render(
        request,
        "hr_payroll/confirm_delete.html",
        {
            "object": document,
            "title": "Delete Employee Document",
            "cancel_url": "hr_payroll:document_list",
        },
    )


# ============================================================
# EMPLOYEE EXIT
# ============================================================

@login_required
@role_permission_required("view_employeeexit", "hr_payroll")
def employee_exit_list(request):

    exits = EmployeeExit.objects.select_related(
        "employee",
    ).order_by(
        "-exit_date",
    )

    return render(
        request,
        "hr_payroll/employee_exit_list.html",
        {"exits": exits},
    )


@login_required
@role_permission_required("add_employeeexit", "hr_payroll")
def employee_exit_add(request):
    return form_page(
        request,
        EmployeeExitForm,
        "Record Employee Exit",
        "hr_payroll:employee_exit_list",
    )


# ============================================================
# ALLOWANCE TYPES
# ============================================================

@login_required
@role_permission_required("view_allowancetype", "hr_payroll")
def allowance_type_list(request):

    allowance_types = AllowanceType.objects.order_by(
        "name",
    )

    return render(
        request,
        "hr_payroll/allowance_type_list.html",
        {"allowance_types": allowance_types},
    )


@login_required
@role_permission_required("add_allowancetype", "hr_payroll")
def allowance_type_add(request):

    return form_page(
        request,
        AllowanceTypeForm,
        "Add Allowance Type",
        "hr_payroll:allowance_type_list",
    )


# ============================================================
# EMPLOYEE ALLOWANCES
# ============================================================

@login_required
@role_permission_required("view_employeeallowance", "hr_payroll")
def allowance_list(request):

    allowances = EmployeeAllowance.objects.select_related(
        "employee",
        "allowance_type",
    ).order_by(
        "employee__first_name",
    )

    return render(
        request,
        "hr_payroll/allowance_list.html",
        {"allowances": allowances},
    )


@login_required
@role_permission_required("add_employeeallowance", "hr_payroll")
def allowance_add(request):

    return form_page(
        request,
        EmployeeAllowanceForm,
        "Add Employee Allowance",
        "hr_payroll:allowance_list",
    )


@login_required
@role_permission_required("change_employeeallowance", "hr_payroll")
def allowance_edit(request, pk):

    obj = get_object_or_404(
        EmployeeAllowance,
        pk=pk,
    )

    return form_page(
        request,
        EmployeeAllowanceForm,
        "Edit Employee Allowance",
        "hr_payroll:allowance_list",
        instance=obj,
    )


@login_required
@role_permission_required("change_employeeallowance", "hr_payroll")
def allowance_deactivate(request, pk):

    obj = get_object_or_404(
        EmployeeAllowance,
        pk=pk,
    )

    if request.method == "POST":
        obj.is_active = False
        obj.save()

        messages.success(
            request,
            "Allowance deactivated.",
        )

    return redirect(
        "hr_payroll:allowance_list",
    )


# ============================================================
# DEDUCTION TYPES
# ============================================================

@login_required
@role_permission_required("view_deductiontype", "hr_payroll")
def get_current_personal_relief_amount():
    """
    Return the currently active/effective monthly Personal Relief.
    """
    today = timezone.localdate()

    relief = (
        PAYERelief.objects
        .filter(
            name="Personal Relief",
            is_active=True,
        )
        .order_by("-effective_from", "-id")
        .first()
    )

    if not relief:
        return Decimal("0.00")

    if relief.effective_from and today < relief.effective_from:
        return Decimal("0.00")

    if relief.effective_to and today > relief.effective_to:
        return Decimal("0.00")

    return (
        relief.monthly_amount or
        Decimal("0.00")
    ).quantize(Decimal("0.01"))

@login_required
@role_permission_required("change_deductiontype", "hr_payroll")
def statutory_deduction_toggle(request, category, pk):

    if request.method != "POST":
        return redirect("hr_payroll:statutory_deductions")

    if category == "deduction":
        obj = get_object_or_404(
            DeductionType,
            pk=pk,
        )

    elif category == "paye":
        obj = get_object_or_404(
            PAYETaxBand,
            pk=pk,
        )

    elif category == "relief":
        obj = get_object_or_404(
            PAYERelief,
            pk=pk,
        )

    elif category == "nssf":
        obj = get_object_or_404(
            NSSFRule,
            pk=pk,
        )

    else:
        messages.error(
            request,
            "Invalid statutory deduction category.",
        )
        return redirect(
            "hr_payroll:statutory_deductions"
        )

    obj.is_active = not obj.is_active
    obj.save(update_fields=["is_active"])

    state = "enabled" if obj.is_active else "disabled"

    messages.success(
        request,
        f'"{getattr(obj, "name", "Statutory rule")}" {state}. '
        "The change will apply to future payroll calculations.",
    )

    return redirect(
        "hr_payroll:statutory_deductions"
    )

def statutory_deductions(request):

    deduction_types = (
        DeductionType.objects
        .filter(is_statutory=True)
        .order_by("name")
    )

    paye_bands = (
        PAYETaxBand.objects
        .order_by("lower_limit")
    )

    paye_reliefs = (
        PAYERelief.objects
        .order_by("name")
    )

    nssf_rules = (
        NSSFRule.objects
        .order_by("lower_limit")
    )

    return render(
        request,
        "hr_payroll/statutory_deductions.html",
        {
            "deduction_types": deduction_types,
            "paye_bands": paye_bands,
            "paye_reliefs": paye_reliefs,
            "nssf_rules": nssf_rules,
        },
    )

def deduction_type_list(request):

    deduction_types = DeductionType.objects.order_by(
        "name",
    )

    return render(
        request,
        "hr_payroll/deduction_type_list.html",
        {"deduction_types": deduction_types},
    )


@login_required
@role_permission_required("add_deductiontype", "hr_payroll")
def deduction_type_add(request):
    return form_page(
        request,
        DeductionTypeForm,
        "Add Deduction Type",
        "hr_payroll:deduction_type_list",
    )


@login_required
@role_permission_required("change_deductiontype", "hr_payroll")

@login_required
@role_permission_required("delete_deductiontype", "hr_payroll")
def deduction_type_delete(request, pk):
    obj = get_object_or_404(
        DeductionType,
        pk=pk,
    )

    if request.method == "POST":
        name = obj.name

        try:
            obj.delete()
            messages.success(
                request,
                f'Deduction rule "{name}" deleted successfully.',
            )
        except Exception:
            messages.error(
                request,
                f'Cannot delete "{name}" because it is currently being used.',
            )

        return redirect("hr_payroll:deduction_type_list")

    return redirect("hr_payroll:deduction_type_list")

def deduction_type_edit(request, pk):

    obj = get_object_or_404(
        DeductionType,
        pk=pk,
    )

    return form_page(
        request,
        DeductionTypeForm,
        f"Edit Deduction Rule - {obj.name}",
        "hr_payroll:deduction_type_list",
        instance=obj,
    )



    return form_page(
        request,
        DeductionTypeForm,
        "Add Deduction Type",
        "hr_payroll:deduction_type_list",
    )



# ============================================================
# STATUTORY PAYROLL RULE MANAGEMENT
# ============================================================

@login_required
@role_permission_required("view_payetaxband", "hr_payroll")
def paye_tax_band_list(request):

    bands = PAYETaxBand.objects.order_by(
        "lower_limit"
    )

    return render(
        request,
        "hr_payroll/paye_tax_band_list.html",
        {"bands": bands},
    )


@login_required
@role_permission_required("add_payetaxband", "hr_payroll")
def paye_tax_band_add(request):

    return form_page(
        request,
        PAYETaxBandForm,
        "Add PAYE Tax Band",
        "hr_payroll:paye_tax_band_list",
    )


@login_required
@role_permission_required("change_payetaxband", "hr_payroll")
def paye_tax_band_edit(request, pk):

    obj = get_object_or_404(
        PAYETaxBand,
        pk=pk,
    )

    return form_page(
        request,
        PAYETaxBandForm,
        f"Edit PAYE Tax Band - {obj.name}",
        "hr_payroll:paye_tax_band_list",
        instance=obj,
    )


@login_required
@role_permission_required("view_payerelief", "hr_payroll")
def paye_relief_list(request):

    reliefs = PAYERelief.objects.order_by(
        "name"
    )

    return render(
        request,
        "hr_payroll/paye_relief_list.html",
        {"reliefs": reliefs},
    )


@login_required
@role_permission_required("add_payerelief", "hr_payroll")
def paye_relief_add(request):

    return form_page(
        request,
        PAYEReliefForm,
        "Add PAYE Relief",
        "hr_payroll:paye_relief_list",
    )


@login_required
@role_permission_required("change_payerelief", "hr_payroll")
def paye_relief_edit(request, pk):

    obj = get_object_or_404(
        PAYERelief,
        pk=pk,
    )

    return form_page(
        request,
        PAYEReliefForm,
        f"Edit PAYE Relief - {obj.name}",
        "hr_payroll:paye_relief_list",
        instance=obj,
    )


@login_required
@role_permission_required("view_nssfrule", "hr_payroll")
def nssf_rule_list(request):

    rules = NSSFRule.objects.order_by(
        "lower_limit"
    )

    return render(
        request,
        "hr_payroll/nssf_rule_list.html",
        {"rules": rules},
    )


@login_required
@role_permission_required("add_nssfrule", "hr_payroll")
def nssf_rule_add(request):

    return form_page(
        request,
        NSSFRuleForm,
        "Add NSSF Rule",
        "hr_payroll:nssf_rule_list",
    )


@login_required
@role_permission_required("change_nssfrule", "hr_payroll")
def nssf_rule_edit(request, pk):

    obj = get_object_or_404(
        NSSFRule,
        pk=pk,
    )

    return form_page(
        request,
        NSSFRuleForm,
        f"Edit NSSF Rule - {obj.name}",
        "hr_payroll:nssf_rule_list",
        instance=obj,
    )


# ============================================================
# EMPLOYEE DEDUCTIONS
# ============================================================

@login_required
@role_permission_required("view_employeededuction", "hr_payroll")
def deduction_list(request):

    deductions = EmployeeDeduction.objects.select_related(
        "employee",
        "deduction_type",
    ).order_by(
        "employee__first_name",
    )

    return render(
        request,
        "hr_payroll/deduction_list.html",
        {"deductions": deductions},
    )


@login_required
@role_permission_required("add_employeededuction", "hr_payroll")
def deduction_add(request):

    return form_page(
        request,
        EmployeeDeductionForm,
        "Add Employee Deduction",
        "hr_payroll:deduction_list",
    )


@login_required
@role_permission_required("change_employeededuction", "hr_payroll")
def deduction_edit(request, pk):

    obj = get_object_or_404(
        EmployeeDeduction,
        pk=pk,
    )

    return form_page(
        request,
        EmployeeDeductionForm,
        "Edit Employee Deduction",
        "hr_payroll:deduction_list",
        instance=obj,
    )


@login_required
@role_permission_required("change_employeededuction", "hr_payroll")
def deduction_deactivate(request, pk):

    obj = get_object_or_404(
        EmployeeDeduction,
        pk=pk,
    )

    if request.method == "POST":
        obj.is_active = False
        obj.save()

        messages.success(
            request,
            "Deduction deactivated.",
        )

    return redirect(
        "hr_payroll:deduction_list",
    )


# ============================================================
# STAFF LOANS
# ============================================================

@login_required
@role_permission_required("view_staffloan", "hr_payroll")
def loan_list(request):

    loans = StaffLoan.objects.select_related(
        "employee",
    ).order_by(
        "-created_at",
    )

    return render(
        request,
        "hr_payroll/loan_list.html",
        {"loans": loans},
    )


@login_required
@role_permission_required("add_staffloan", "hr_payroll")
def loan_add(request):

    return form_page(
        request,
        StaffLoanForm,
        "Add Staff Loan",
        "hr_payroll:loan_list",
    )


@login_required
@role_permission_required("change_staffloan", "hr_payroll")
def loan_edit(request, pk):

    obj = get_object_or_404(
        StaffLoan,
        pk=pk,
    )

    return form_page(
        request,
        StaffLoanForm,
        "Edit Staff Loan",
        "hr_payroll:loan_list",
        instance=obj,
    )


@login_required
@role_permission_required("change_staffloan", "hr_payroll")
def loan_repayment(request, pk):

    loan = get_object_or_404(
        StaffLoan,
        pk=pk,
    )

    class RepaymentForm(forms.Form):
        amount = forms.DecimalField(
            min_value=Decimal("0.01"),
            max_digits=12,
            decimal_places=2,
            label="Repayment Amount",
        )

    if request.method == "POST":

        form = RepaymentForm(request.POST)

        if form.is_valid():

            amount = form.cleaned_data["amount"]

            loan.amount_paid += amount

            if loan.amount_paid >= loan.principal_amount:
                loan.amount_paid = loan.principal_amount
                loan.status = "COMPLETED"

            loan.save()

            messages.success(
                request,
                "Loan repayment recorded.",
            )

            return redirect(
                "hr_payroll:loan_list",
            )

    else:
        form = RepaymentForm()

    return render(
        request,
        "hr_payroll/form.html",
        {
            "form": form,
            "title": f"Record Loan Repayment - {loan}",
            "cancel_url": "hr_payroll:loan_list",
        },
    )


# ============================================================
# PAYROLL
# ============================================================

@login_required
@role_permission_required("view_payrollperiod", "hr_payroll")
def payroll_list(request):
    selected_month = request.GET.get("month", "")
    selected_year = request.GET.get("year", "")

    payroll_periods = PayrollPeriod.objects.all()

    if selected_month:
        try:
            payroll_periods = payroll_periods.filter(month=int(selected_month))
        except (ValueError, TypeError):
            selected_month = ""

    if selected_year:
        try:
            payroll_periods = payroll_periods.filter(year=int(selected_year))
        except (ValueError, TypeError):
            selected_year = ""

    payroll_periods = payroll_periods.order_by("-year", "-month")

    selected_period = None
    payroll_records = PayrollRecord.objects.none()

    period_id = request.GET.get("period")

    if period_id:
        try:
            selected_period = PayrollPeriod.objects.get(pk=int(period_id))
            payroll_records = PayrollRecord.objects.select_related(
                "employee",
                "payroll_period",
            ).filter(
                payroll_period=selected_period
            ).order_by(
                "employee__first_name",
                "employee__middle_name",
                "employee__last_name",
            )
        except (PayrollPeriod.DoesNotExist, ValueError, TypeError):
            selected_period = None
            payroll_records = PayrollRecord.objects.none()

    return render(
        request,
        "hr_payroll/payroll_list.html",
        {
            "payroll_periods": payroll_periods,
            "selected_period": selected_period,
            "payroll_records": payroll_records,
            "selected_month": selected_month,
            "selected_year": selected_year,
        },
    )

@login_required
@role_permission_required("add_payrollperiod", "hr_payroll")

@login_required
@role_permission_required("delete_payrollperiod", "hr_payroll")
def payroll_period_delete(request, pk):
    period = get_object_or_404(PayrollPeriod, pk=pk)

    if request.method != "POST":
        return redirect("hr_payroll:payroll_list")

    if period.status in {"APPROVED", "PAID", "CLOSED"}:
        messages.error(
            request,
            f"{period.name} cannot be deleted because it is {period.get_status_display()}."
        )
        return redirect("hr_payroll:payroll_list")

    period_name = period.name
    try:
        PayrollRecord.objects.filter(payroll_period=period).delete()
        period.delete()
        messages.success(request, f"{period_name} deleted successfully.")
    except Exception as exc:
        messages.error(request, f"Could not delete {period_name}: {exc}")

    return redirect("hr_payroll:payroll_list")

def payroll_period_add(request):
    """
    Create a monthly payroll period using Month and Year only.
    Name and dates are generated automatically.
    """

    if request.method == "POST":
        form = PayrollPeriodForm(request.POST)

        if form.is_valid():
            year = form.cleaned_data["year"]
            month = form.cleaned_data["month"]

            existing = PayrollPeriod.objects.filter(
                year=year,
                month=month,
            ).first()

            if existing:
                messages.warning(
                    request,
                    f"{existing.name} already exists.",
                )
                return redirect(
                    "hr_payroll:payroll_process",
                    pk=existing.pk,
                )

            month_name = calendar.month_name[month]
            start_date = date(year, month, 1)
            last_day = calendar.monthrange(year, month)[1]
            end_date = date(year, month, last_day)

            period = PayrollPeriod.objects.create(
                name=f"{month_name} {year} Payroll",
                year=year,
                month=month,
                start_date=start_date,
                end_date=end_date,
                status="DRAFT",
                processed_at=None,
            )

            messages.success(
                request,
                f"{period.name} created successfully as Draft.",
            )

            return redirect(
                "hr_payroll:payroll_process",
                pk=period.pk,
            )

    else:
        form = PayrollPeriodForm()

    return render(
        request,
        "hr_payroll/payroll_period_form.html",
        {
            "form": form,
            "title": "Create Monthly Payroll",
            "cancel_url": "hr_payroll:payroll_list",
        },
    )


def _calculate_monthly_payroll_preview(period):
    """
    Calculate payroll without saving records or changing loans.
    Uses the existing statutory deduction engine.
    """

    employees = Employee.objects.filter(
        is_active=True,
        employment_status="ACTIVE",
    ).order_by(
        "first_name",
        "middle_name",
        "last_name",
    )

    preview = []

    totals = {
        "employees": 0,
        "basic_salary": Decimal("0.00"),
        "allowances": Decimal("0.00"),
        "gross_salary": Decimal("0.00"),
        "paye": Decimal("0.00"),
        "nssf": Decimal("0.00"),
        "sha": Decimal("0.00"),
        "housing_levy": Decimal("0.00"),
        "loan_deductions": Decimal("0.00"),
        "other_deductions": Decimal("0.00"),
        "total_deductions": Decimal("0.00"),
        "net_salary": Decimal("0.00"),
    }

    for employee in employees:

        basic = (
            employee.basic_salary or Decimal("0.00")
        ).quantize(Decimal("0.01"))

        allowances = EmployeeAllowance.objects.filter(
            employee=employee,
            is_active=True,
            effective_from__lte=period.end_date,
        ).filter(
            Q(effective_to__isnull=True)
            | Q(effective_to__gte=period.start_date)
        )

        deductions = EmployeeDeduction.objects.filter(
            employee=employee,
            is_active=True,
            effective_from__lte=period.end_date,
        ).filter(
            Q(effective_to__isnull=True)
            | Q(effective_to__gte=period.start_date)
        )

        total_allowances = sum(
            (
                item.amount
                for item in allowances
            ),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))

        other_deductions = sum(
            (
                item.amount
                for item in deductions
            ),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))

        loan_deductions = Decimal("0.00")

        active_loans = StaffLoan.objects.filter(
            employee=employee,
            status="ACTIVE",
        )

        for loan in active_loans:
            principal = (
                loan.principal_amount or Decimal("0.00")
            )
            amount_paid = (
                loan.amount_paid or Decimal("0.00")
            )
            balance = (
                principal - amount_paid
            ).quantize(Decimal("0.01"))

            if balance <= Decimal("0.00"):
                continue

            installment = (
                loan.monthly_installment or Decimal("0.00")
            )

            loan_deductions += min(
                installment,
                balance,
            )

        loan_deductions = loan_deductions.quantize(
            Decimal("0.01")
        )

        gross = (
            basic + total_allowances
        ).quantize(Decimal("0.01"))

        taxable_income = gross

        statutory = calculate_compulsory_deductions(
            basic_salary=basic,
            gross_salary=gross,
            taxable_income=taxable_income,
        )

        paye = (
            statutory.get("paye", Decimal("0.00"))
            or Decimal("0.00")
        ).quantize(Decimal("0.01"))

        nssf = (
            statutory.get("nssf", Decimal("0.00"))
            or Decimal("0.00")
        ).quantize(Decimal("0.01"))

        sha = (
            statutory.get("sha", Decimal("0.00"))
            or Decimal("0.00")
        ).quantize(Decimal("0.01"))

        housing_levy = (
            statutory.get(
                "housing_levy",
                Decimal("0.00"),
            )
            or Decimal("0.00")
        ).quantize(Decimal("0.01"))

        statutory_other = (
            statutory.get(
                "other",
                Decimal("0.00"),
            )
            or Decimal("0.00")
        ).quantize(Decimal("0.01"))

        total_deductions = (
            other_deductions
            + loan_deductions
            + paye
            + nssf
            + sha
            + housing_levy
            + statutory_other
        ).quantize(Decimal("0.01"))

        net_salary = (
            gross - total_deductions
        ).quantize(Decimal("0.01"))

        employee_name = " ".join(
            part
            for part in [
                getattr(employee, "first_name", ""),
                getattr(employee, "middle_name", ""),
                getattr(employee, "last_name", ""),
            ]
            if part
        ).strip()

        preview.append(
            {
                "employee": employee,
                "employee_name": employee_name or str(employee),
                "employee_id": employee.pk,
                "basic_salary": basic,
                "total_allowances": total_allowances,
                "gross_salary": gross,
                "paye": paye,
                "nssf": nssf,
                "sha": sha,
                "housing_levy": housing_levy,
                "loan_deductions": loan_deductions,
                "other_deductions": (
                    other_deductions + statutory_other
                ).quantize(Decimal("0.01")),
                "total_deductions": total_deductions,
                "net_salary": net_salary,
            }
        )

        totals["employees"] += 1
        totals["basic_salary"] += basic
        totals["allowances"] += total_allowances
        totals["gross_salary"] += gross
        totals["paye"] += paye
        totals["nssf"] += nssf
        totals["sha"] += sha
        totals["housing_levy"] += housing_levy
        totals["loan_deductions"] += loan_deductions
        totals["other_deductions"] += (
            other_deductions + statutory_other
        ).quantize(Decimal("0.01"))
        totals["total_deductions"] += total_deductions
        totals["net_salary"] += net_salary

    for key in totals:
        if key != "employees":
            totals[key] = totals[key].quantize(
                Decimal("0.01")
            )

    return preview, totals


@login_required
@role_permission_required("add_payrollrecord", "hr_payroll")
@transaction.atomic
def payroll_process(request, pk):
    """
    Preview and save monthly payroll.

    Saving payroll records keeps the period in DRAFT.
    Loan balances are never changed here.
    """

    period = get_object_or_404(
        PayrollPeriod,
        pk=pk,
    )

    # ---------------------------------------------------------
    # PAID PAYROLLS MUST DISPLAY THE SAVED HISTORICAL RECORDS.
    # Do not recalculate them because loan balances may have
    # changed during finalization.
    # ---------------------------------------------------------

    if period.status == "PAID":

        payroll_records = list(
            PayrollRecord.objects.select_related(
                "employee",
                "payroll_period",
            ).filter(
                payroll_period=period,
            ).order_by(
                "employee__first_name",
                "employee__middle_name",
                "employee__last_name",
            )
        )

        preview = []

        for record in payroll_records:

            preview.append(
                {
                    "employee": record.employee,
                    "employee_name": str(record.employee),
                    "employee_id": getattr(
                        record.employee,
                        "employee_number",
                        "",
                    ),
                    "basic_salary": record.basic_salary,
                    "total_allowances": record.total_allowances,
                    "gross_salary": record.gross_salary,
                    "paye": record.paye,
                    "nssf": record.nssf,
                    "sha": record.sha,
                    "housing_levy": record.housing_levy,
                    "loan_deductions": record.loan_deductions,
                    "other_deductions": record.other_deductions,
                    "total_deductions": record.total_deductions,
                    "net_salary": record.net_salary,
                }
            )

        totals = {
            "employees": len(preview),
            "basic_salary": sum(
                (item["basic_salary"] or Decimal("0.00"))
                for item in preview
            ),
            "allowances": sum(
                (item["total_allowances"] or Decimal("0.00"))
                for item in preview
            ),
            "gross_salary": sum(
                (item["gross_salary"] or Decimal("0.00"))
                for item in preview
            ),
            "paye": sum(
                (item["paye"] or Decimal("0.00"))
                for item in preview
            ),
            "nssf": sum(
                (item["nssf"] or Decimal("0.00"))
                for item in preview
            ),
            "sha": sum(
                (item["sha"] or Decimal("0.00"))
                for item in preview
            ),
            "housing_levy": sum(
                (item["housing_levy"] or Decimal("0.00"))
                for item in preview
            ),
            "loan_deductions": sum(
                (item["loan_deductions"] or Decimal("0.00"))
                for item in preview
            ),
            "other_deductions": sum(
                (item["other_deductions"] or Decimal("0.00"))
                for item in preview
            ),
            "total_deductions": sum(
                (item["total_deductions"] or Decimal("0.00"))
                for item in preview
            ),
            "net_salary": sum(
                (item["net_salary"] or Decimal("0.00"))
                for item in preview
            ),
        }

    else:

        preview, totals = _calculate_monthly_payroll_preview(
            period
        )

    if request.method == "POST":

        if period.status not in ("DRAFT", "PROCESSING"):
            messages.error(
                request,
                f"{period.name} cannot be recalculated because it is "
                f"already {period.get_status_display()}.",
            )

            return redirect(
                "hr_payroll:payroll_process",
                pk=period.pk,
            )

        for item in preview:

            PayrollRecord.objects.update_or_create(
                employee=item["employee"],
                payroll_period=period,
                defaults={
                    "basic_salary": item["basic_salary"],
                    "total_allowances": item["total_allowances"],
                    "gross_salary": item["gross_salary"],
                    "total_deductions": item["total_deductions"],
                    "taxable_income": item["gross_salary"],
                    "paye": item["paye"],
                    "nssf": item["nssf"],
                    "sha": item["sha"],
                    "housing_levy": item["housing_levy"],
                    "loan_deductions": item["loan_deductions"],
                    "other_deductions": item["other_deductions"],
                    "net_salary": item["net_salary"],
                },
            )

        period.status = "DRAFT"
        period.processed_at = None

        period.save(
            update_fields=[
                "status",
                "processed_at",
            ]
        )

        messages.success(
            request,
            f"{period.name} saved successfully as Draft. "
            "Loan balances have not been changed.",
        )

        return redirect(
            "hr_payroll:payroll_process",
            pk=period.pk,
        )

    return render(
        request,
        "hr_payroll/payroll_preview.html",
        {
            "period": period,
            "preview": preview,
            "totals": totals,
            "employee_count": totals.get("employees", len(preview)),
            "readonly": period.status not in (
                "DRAFT",
                "PROCESSING",
            ),
        },
    )



@login_required
@role_permission_required("change_payrollrecord", "hr_payroll")
@transaction.atomic
def finalize_payroll(request, pk):
    """
    Finalize and pay a saved payroll period.

    PayrollRecord values are already saved before this function runs.
    Loan balances are updated only at this finalization stage.
    """

    period = get_object_or_404(
        PayrollPeriod.objects.select_for_update(),
        pk=pk,
    )

    if request.method != "POST":
        return redirect(
            "hr_payroll:payroll_process",
            pk=period.pk,
        )

    if period.status not in ("DRAFT", "PROCESSING"):
        messages.error(
            request,
            f"{period.name} cannot be finalized because it is "
            f"already {period.get_status_display()}.",
        )

        return redirect(
            "hr_payroll:payroll_process",
            pk=period.pk,
        )

    payroll_records = list(
        PayrollRecord.objects.select_related(
            "employee",
            "payroll_period",
        ).filter(
            payroll_period=period,
        ).order_by(
            "employee__first_name",
            "employee__middle_name",
            "employee__last_name",
        )
    )

    if not payroll_records:
        messages.error(
            request,
            f"{period.name} cannot be finalized because it has "
            "no saved payroll records. Save the payroll first.",
        )

        return redirect(
            "hr_payroll:payroll_process",
            pk=period.pk,
        )

    # ---------------------------------------------------------
    # STEP 1: Lock and validate all loan deductions first.
    # No loan balances are changed during this stage.
    # ---------------------------------------------------------

    repayment_plan = []
    total_loan_repayments = Decimal("0.00")
    employees_with_loans = 0
    completed_loans = 0

    for record in payroll_records:

        deduction = (
            record.loan_deductions
            or Decimal("0.00")
        ).quantize(
            Decimal("0.01")
        )

        if deduction <= Decimal("0.00"):
            continue

        remaining = deduction
        employee_plan = []

        loans = list(
            StaffLoan.objects.select_for_update().filter(
                employee=record.employee,
                status="ACTIVE",
            ).order_by(
                "start_date",
                "id",
            )
        )

        if not loans:
            employee_name = getattr(
                record.employee,
                "full_name",
                str(record.employee),
            )

            messages.error(
                request,
                f"Payroll cannot be finalized. "
                f"{employee_name} has a saved loan deduction of "
                f"{deduction:.2f}, but no active staff loan was found.",
            )

            return redirect(
                "hr_payroll:payroll_process",
                pk=period.pk,
            )

        for loan in loans:

            if remaining <= Decimal("0.00"):
                break

            principal = (
                loan.principal_amount
                or Decimal("0.00")
            )

            amount_paid = (
                loan.amount_paid
                or Decimal("0.00")
            )

            balance = (
                principal - amount_paid
            ).quantize(
                Decimal("0.01")
            )

            if balance <= Decimal("0.00"):
                continue

            repayment = min(
                remaining,
                balance,
            ).quantize(
                Decimal("0.01")
            )

            if repayment <= Decimal("0.00"):
                continue

            employee_plan.append(
                {
                    "loan": loan,
                    "repayment": repayment,
                    "principal": principal,
                    "amount_paid": amount_paid,
                }
            )

            remaining -= repayment
            total_loan_repayments += repayment

        if remaining > Decimal("0.00"):

            employee_name = getattr(
                record.employee,
                "full_name",
                str(record.employee),
            )

            messages.error(
                request,
                f"Payroll cannot be finalized. "
                f"The saved loan deduction of {deduction:.2f} "
                f"for {employee_name} cannot be fully allocated "
                f"against active loan balances. "
                f"Unallocated amount: {remaining:.2f}.",
            )

            return redirect(
                "hr_payroll:payroll_process",
                pk=period.pk,
            )

        if employee_plan:
            employees_with_loans += 1

        repayment_plan.append(employee_plan)

    # ---------------------------------------------------------
    # STEP 2: Apply validated loan repayments.
    # ---------------------------------------------------------

    for employee_plan in repayment_plan:

        for item in employee_plan:

            loan = item["loan"]
            repayment = item["repayment"]
            principal = item["principal"]
            amount_paid = item["amount_paid"]

            new_amount_paid = (
                amount_paid + repayment
            ).quantize(
                Decimal("0.01")
            )

            if new_amount_paid >= principal:
                new_amount_paid = principal
                loan.status = "COMPLETED"
                completed_loans += 1

            loan.amount_paid = new_amount_paid

            loan.save(
                update_fields=[
                    "amount_paid",
                    "status",
                ]
            )

    # ---------------------------------------------------------
    # STEP 3: Mark payroll as PAID.
    # ---------------------------------------------------------

    period.status = "PAID"
    period.processed_at = timezone.now()

    period.save(
        update_fields=[
            "status",
            "processed_at",
        ]
    )

    messages.success(
        request,
        f"{period.name} has been finalized and marked PAID. "
        f"Loan repayments applied: "
        f"{total_loan_repayments:.2f}. "
        f"Employees with loan repayments: "
        f"{employees_with_loans}. "
        f"Loans completed: "
        f"{completed_loans}.",
    )

    return redirect(
        "hr_payroll:payroll_process",
        pk=period.pk,
    )

def calculate_configured_deduction(
    deduction_type,
    basic_salary,
    gross_salary,
    taxable_income,
):
    today = timezone.localdate()

    if not deduction_type.is_active:
        return Decimal("0.00")

    if deduction_type.effective_from:
        if today < deduction_type.effective_from:
            return Decimal("0.00")

    if deduction_type.effective_to:
        if today > deduction_type.effective_to:
            return Decimal("0.00")

    if deduction_type.calculation_method == "PERCENTAGE":

        if deduction_type.calculation_base == "GROSS":
            base = gross_salary

        elif deduction_type.calculation_base == "TAXABLE":
            base = taxable_income

        else:
            base = basic_salary

        amount = (
            base *
            deduction_type.percentage /
            Decimal("100.00")
        )

    else:
        amount = (
            deduction_type.fixed_amount or
            Decimal("0.00")
        )

    minimum_amount = (
        deduction_type.minimum_amount or
        Decimal("0.00")
    )

    maximum_amount = (
        deduction_type.maximum_amount or
        Decimal("0.00")
    )

    if minimum_amount > Decimal("0.00"):
        amount = max(amount, minimum_amount)

    if maximum_amount > Decimal("0.00"):
        amount = min(amount, maximum_amount)

    return amount.quantize(
        Decimal("0.01")
    )


def calculate_paye_from_tax_bands(
    taxable_income,
):
    remaining = max(
        taxable_income,
        Decimal("0.00"),
    )

    tax = Decimal("0.00")
    today = timezone.localdate()

    bands = PAYETaxBand.objects.filter(
        is_active=True,
    ).order_by("lower_limit")

    for band in bands:

        if band.effective_from:
            if today < band.effective_from:
                continue

        if band.effective_to:
            if today > band.effective_to:
                continue

        lower = (
            band.lower_limit or
            Decimal("0.00")
        )

        if band.upper_limit is None:
            taxable_in_band = remaining

        else:
            width = (
                band.upper_limit -
                lower
            )

            if width <= Decimal("0.00"):
                continue

            taxable_in_band = min(
                remaining,
                width,
            )

        if taxable_in_band <= Decimal("0.00"):
            continue

        tax += (
            taxable_in_band *
            band.rate /
            Decimal("100.00")
        )

        remaining -= taxable_in_band

        if remaining <= Decimal("0.00"):
            break

    relief = PAYERelief.objects.filter(
        name="Personal Relief",
        is_active=True,
    ).first()

    if relief:

        valid = True

        if relief.effective_from:
            if today < relief.effective_from:
                valid = False

        if relief.effective_to:
            if today > relief.effective_to:
                valid = False

        if valid:
            tax -= (
                relief.monthly_amount or
                Decimal("0.00")
            )

    return max(
        tax,
        Decimal("0.00"),
    ).quantize(
        Decimal("0.01")
    )


def calculate_nssf_from_rules(
    basic_salary,
):
    salary = max(
        basic_salary,
        Decimal("0.00"),
    )

    today = timezone.localdate()
    total = Decimal("0.00")

    rules = NSSFRule.objects.filter(
        is_active=True,
    ).order_by("lower_limit")

    for rule in rules:

        if rule.effective_from:
            if today < rule.effective_from:
                continue

        if rule.effective_to:
            if today > rule.effective_to:
                continue

        lower = (
            rule.lower_limit or
            Decimal("0.00")
        )

        if salary <= lower:
            continue

        if rule.upper_limit is None:
            applicable = salary - lower

        else:
            applicable = (
                min(
                    salary,
                    rule.upper_limit,
                ) - lower
            )

        if applicable <= Decimal("0.00"):
            continue

        contribution = (
            applicable *
            rule.employee_percentage /
            Decimal("100.00")
        )

        if rule.employee_cap > Decimal("0.00"):
            contribution = min(
                contribution,
                rule.employee_cap,
            )

        total += contribution

    return total.quantize(
        Decimal("0.01")
    )


def calculate_compulsory_deductions(
    basic_salary,
    gross_salary,
    taxable_income,
):
    results = {
        "paye": calculate_paye_from_tax_bands(
            taxable_income
        ),
        "nssf": calculate_nssf_from_rules(
            basic_salary
        ),
        "sha": Decimal("0.00"),
        "housing_levy": Decimal("0.00"),
        "other": Decimal("0.00"),
    }

    rules = DeductionType.objects.filter(
        is_active=True,
        is_compulsory=True,
    ).order_by("name")

    for rule in rules:

        code = (
            (rule.code or "")
            .strip()
            .upper()
        )

        if code in (
            "PAYE",
            "PAYEE",
            "NSSF",
        ):
            continue

        amount = calculate_configured_deduction(
            rule,
            basic_salary,
            gross_salary,
            taxable_income,
        )

        if code in (
            "SHA",
            "SHIF",
        ):
            results["sha"] += amount

        elif code in (
            "AHL",
            "HOUSING",
            "HOUSING_LEVY",
            "HOUSE LEVY",
        ):
            results["housing_levy"] += amount

        else:
            results["other"] += amount

    results["total"] = (
        results["paye"] +
        results["nssf"] +
        results["sha"] +
        results["housing_levy"] +
        results["other"]
    )

    return results


# ============================================================
# PAYSLIPS
# ============================================================

@login_required
@role_permission_required("view_payslip", "hr_payroll")
def payslip_list(request):
    """
    HR payslip search page.

    Default:
        No payslips are loaded.

    Search modes:
        1. One employee + payroll period.
        2. All employees + payroll period.
    """

    payslips = Payslip.objects.none()

    employees = Employee.objects.all().order_by(
        "first_name",
        "middle_name",
        "last_name",
    )

    payroll_periods = PayrollPeriod.objects.all().order_by(
        "-year",
        "-month",
    )

    search_performed = False
    search_mode = ""
    selected_employee_id = request.GET.get("employee_id", "").strip()
    selected_period_id = request.GET.get("payroll_period_id", "").strip()

    if request.GET.get("search_one") == "1":
        search_performed = True
        search_mode = "one"

        if selected_employee_id and selected_period_id:

            payslips = Payslip.objects.select_related(
                "payroll_record",
                "payroll_record__employee",
                "payroll_record__payroll_period",
            ).filter(
                payroll_record__employee_id=selected_employee_id,
                payroll_record__payroll_period_id=selected_period_id,
            ).order_by(
                "-generated_at",
            )

    elif request.GET.get("search_all") == "1":
        search_performed = True
        search_mode = "all"

        if selected_period_id:

            payslips = Payslip.objects.select_related(
                "payroll_record",
                "payroll_record__employee",
                "payroll_record__payroll_period",
            ).filter(
                payroll_record__payroll_period_id=selected_period_id,
            ).order_by(
                "payroll_record__employee__first_name",
                "payroll_record__employee__last_name",
            )

    selected_employee = None
    if selected_employee_id:
        selected_employee = Employee.objects.filter(
            pk=selected_employee_id,
        ).first()

    selected_period = None
    if selected_period_id:
        selected_period = PayrollPeriod.objects.filter(
            pk=selected_period_id,
        ).first()

    return render(
        request,
        "hr_payroll/payslip_list.html",
        {
            "payslips": payslips,
            "employees": employees,
            "payroll_periods": payroll_periods,
            "selected_employee": selected_employee,
            "selected_period": selected_period,
            "selected_employee_id": selected_employee_id,
            "selected_period_id": selected_period_id,
            "search_performed": search_performed,
            "search_mode": search_mode,
        },
    )



@login_required
@role_permission_required("add_payslip", "hr_payroll")
def payslip_generate(request, payroll_record_id):

    record = get_object_or_404(
        PayrollRecord,
        pk=payroll_record_id,
    )

    if request.method == "POST":

        payslip, created = Payslip.objects.get_or_create(
            payroll_record=record,
            defaults={
                "payslip_number": (
                    f"PS-{record.payroll_period.year}"
                    f"{record.payroll_period.month:02d}-"
                    f"{record.employee.employee_number}"
                ),
            },
        )

        if not created:
            messages.info(
                request,
                "Payslip already exists.",
            )
        else:
            messages.success(
                request,
                f"Payslip {payslip.payslip_number} generated.",
            )

    return redirect(
        "hr_payroll:payslip_list",
    )



@login_required
@role_permission_required("add_payslip", "hr_payroll")
def payslip_generate_all(request, payroll_period_id):
    """
    Generate payslips for every PayrollRecord belonging to a payroll period.

    This function ONLY creates missing Payslip records.

    It does NOT:
    - recalculate payroll;
    - modify PayrollRecord figures;
    - modify staff loans;
    - finalize payroll;
    - change payroll status.
    """

    period = get_object_or_404(
        PayrollPeriod,
        pk=payroll_period_id,
    )

    if request.method != "POST":
        messages.error(
            request,
            "Bulk payslip generation must be submitted using POST.",
        )
        return redirect(
            "hr_payroll:payroll_process",
            period.pk,
        )

    records = (
        PayrollRecord.objects
        .filter(payroll_period=period)
        .select_related("employee", "payroll_period")
        .order_by("employee__employee_number")
    )

    total_records = records.count()
    generated_count = 0
    existing_count = 0

    for record in records:
        payslip_number = (
            f"PS-{record.payroll_period.year}"
            f"{record.payroll_period.month:02d}-"
            f"{record.employee.employee_number}"
        )

        payslip, created = Payslip.objects.get_or_create(
            payroll_record=record,
            defaults={
                "payslip_number": payslip_number,
            },
        )

        if created:
            generated_count += 1
        else:
            existing_count += 1

    if total_records == 0:
        messages.warning(
            request,
            (
                f"No saved payroll records were found for "
                f"{period.year}/{period.month:02d}. "
                "No payslips were generated."
            ),
        )
    elif generated_count == 0:
        messages.info(
            request,
            (
                f"All {existing_count} payroll records already have "
                "payslips. No duplicates were created."
            ),
        )
    else:
        messages.success(
            request,
            (
                f"Bulk payslip generation complete: "
                f"{generated_count} new payslip(s) generated; "
                f"{existing_count} already existed; "
                f"{total_records} payroll record(s) checked."
            ),
        )

    return redirect(
        "hr_payroll:payroll_process",
        period.pk,
    )

@login_required
@role_permission_required("change_payslip", "hr_payroll")
def payslip_mark_sent(request, pk):

    payslip = get_object_or_404(
        Payslip,
        pk=pk,
    )

    if request.method == "POST":

        payslip.is_sent = True
        payslip.sent_at = timezone.now()
        payslip.save(
            update_fields=[
                "is_sent",
                "sent_at",
            ],
        )

        messages.success(
            request,
            "Payslip marked as sent.",
        )

    return redirect(
        "hr_payroll:payslip_list",
    )


# ============================================================
# STAFF SELF-SERVICE PAYSLIPS
# ============================================================

def _get_logged_in_staff_employee(request):
    """
    Resolve the Employee linked to the logged-in staff account.
    Staff members can only access their own payroll information.
    """

    try:
        profile = request.user.profile
    except Exception:
        return None

    employee = getattr(
        profile,
        "employee",
        None,
    )

    return employee




# ============================================================
# STAFF SELF-SERVICE
# ============================================================

@login_required
def staff_attendance(request):

    support_staff = (
        getattr(getattr(request.user, "profile", None), "role", None) == "STAFF"
        and get_staff_teacher(request.user) is None
    )

    if not (
        support_staff
        or user_has_role_permission(request.user, "view_attendance")
    ):
        messages.error(
            request,
            "You do not have permission to access Attendance."
        )
        return redirect("accounts:staff_dashboard")
    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        messages.error(
            request,
            "Your staff account is not linked to an employee record.",
        )
        return redirect("accounts:staff_dashboard")

    attendance_records = (
        Attendance.objects
        .filter(employee=employee)
        .order_by("-date", "-id")
    )

    return render(
        request,
        "hr_payroll/staff_attendance.html",
        {
            "employee": employee,
            "attendance_records": attendance_records,
        },
    )


@login_required
def staff_leave_list(request):

    support_staff = (
        getattr(getattr(request.user, "profile", None), "role", None) == "STAFF"
        and get_staff_teacher(request.user) is None
    )

    if not (
        support_staff
        or user_has_role_permission(request.user, "view_leaveapplication")
    ):
        messages.error(
            request,
            "You do not have permission to access Leave."
        )
        return redirect("accounts:staff_dashboard")
    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        messages.error(
            request,
            "Your staff account is not linked to an employee record.",
        )
        return redirect("accounts:staff_dashboard")

    leave_applications = (
        LeaveApplication.objects
        .filter(employee=employee)
        .select_related("leave_type", "approved_by")
        .order_by("-created_at", "-id")
    )

    return render(
        request,
        "hr_payroll/staff_leave.html",
        {
            "employee": employee,
            "leave_applications": leave_applications,
        },
    )


@login_required
def staff_leave_apply(request):

    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        messages.error(
            request,
            "Your staff account is not linked to an employee record.",
        )
        return redirect("accounts:staff_dashboard")

    if request.method == "POST":

        form = StaffLeaveApplicationForm(request.POST)

        if form.is_valid():

            leave_type = form.cleaned_data["leave_type"]
            start_date = form.cleaned_data["start_date"]
            end_date = form.cleaned_data["end_date"]
            reason = form.cleaned_data.get("reason")

            days = (end_date - start_date).days + 1

            if leave_type.days_allowed and days > leave_type.days_allowed:
                form.add_error(
                    None,
                    (
                        f"{leave_type.name} allows a maximum of "
                        f"{leave_type.days_allowed} day(s). "
                        f"You selected {days} day(s)."
                    ),
                )
            else:

                overlapping = (
                    LeaveApplication.objects
                    .filter(
                        employee=employee,
                        status__in=["PENDING", "APPROVED"],
                        start_date__lte=end_date,
                        end_date__gte=start_date,
                    )
                    .exists()
                )

                if overlapping:
                    form.add_error(
                        None,
                        (
                            "You already have a pending or approved "
                            "leave application covering part of these dates."
                        ),
                    )
                else:

                    application = LeaveApplication(
                        employee=employee,
                        leave_type=leave_type,
                        start_date=start_date,
                        end_date=end_date,
                        days=days,
                        reason=reason,
                        status="PENDING",
                    )

                    application.full_clean(
                        exclude=[
                            "approved_by",
                            "approved_at",
                        ]
                    )

                    application.save()

                    messages.success(
                        request,
                        (
                            "Your leave application has been submitted "
                            "successfully and is awaiting approval."
                        ),
                    )

                    return redirect("hr_payroll:staff_leave_list")

    else:
        form = StaffLeaveApplicationForm()

    return render(
        request,
        "hr_payroll/staff_leave_apply.html",
        {
            "employee": employee,
            "form": form,
        },
    )


@login_required
def staff_leave_cancel(request, pk):

    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        messages.error(
            request,
            "Your staff account is not linked to an employee record.",
        )
        return redirect("accounts:staff_dashboard")

    application = get_object_or_404(
        LeaveApplication,
        pk=pk,
        employee=employee,
    )

    if request.method != "POST":
        return redirect("hr_payroll:staff_leave_list")

    if application.status != "PENDING":
        messages.error(
            request,
            "Only pending leave applications can be cancelled.",
        )
        return redirect("hr_payroll:staff_leave_list")

    application.status = "CANCELLED"
    application.save(update_fields=["status"])

    messages.success(
        request,
        "Your leave application has been cancelled.",
    )

    return redirect("hr_payroll:staff_leave_list")


@login_required
def staff_loan_list(request):

    support_staff = (
        getattr(getattr(request.user, "profile", None), "role", None) == "STAFF"
        and get_staff_teacher(request.user) is None
    )

    if not (
        support_staff
        or user_has_role_permission(request.user, "view_staffloan")
    ):
        messages.error(
            request,
            "You do not have permission to access Loans."
        )
        return redirect("accounts:staff_dashboard")
    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        messages.error(
            request,
            "Your staff account is not linked to an employee record.",
        )
        return redirect("accounts:staff_dashboard")

    loans = (
        StaffLoan.objects
        .filter(employee=employee)
        .order_by("-created_at", "-id")
    )

    active_loans = loans.filter(status="ACTIVE")

    outstanding_balance = sum(
        (
            (loan.principal_amount or Decimal("0.00"))
            - (loan.amount_paid or Decimal("0.00"))
            for loan in active_loans
        ),
        Decimal("0.00"),
    )

    outstanding_balance = max(
        outstanding_balance,
        Decimal("0.00"),
    )

    total_principal = sum(
        (
            loan.principal_amount or Decimal("0.00")
            for loan in loans
        ),
        Decimal("0.00"),
    )

    total_paid = sum(
        (
            loan.amount_paid or Decimal("0.00")
            for loan in loans
        ),
        Decimal("0.00"),
    )

    applications = (
        LoanApplication.objects
        .filter(employee=employee)
        .order_by("-created_at", "-id")
    )

    pending_applications_count = applications.filter(
        status__in=[
            "SUBMITTED",
            "UNDER_REVIEW",
            "APPROVED",
        ]
    ).count()

    return render(
        request,
        "hr_payroll/staff_loans.html",
        {
            "employee": employee,
            "loans": loans,
            "active_loans": active_loans,
            "outstanding_balance": outstanding_balance,
            "total_principal": total_principal,
            "total_paid": total_paid,
            "applications": applications,
            "pending_applications_count": pending_applications_count,
        },
    )


@login_required
def staff_document_list(request):

    support_staff = (
        getattr(getattr(request.user, "profile", None), "role", None) == "STAFF"
        and get_staff_teacher(request.user) is None
    )

    if not (
        support_staff
        or user_has_role_permission(request.user, "view_employeedocument")
    ):
        messages.error(
            request,
            "You do not have permission to access Documents."
        )
        return redirect("accounts:staff_dashboard")
    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        messages.error(
            request,
            "Your staff account is not linked to an employee record.",
        )
        return redirect("accounts:staff_dashboard")

    documents = (
        EmployeeDocument.objects
        .filter(employee=employee)
        .order_by("-uploaded_at", "-id")
    )

    return render(
        request,
        "hr_payroll/staff_documents.html",
        {
            "employee": employee,
            "documents": documents,
        },
    )


@login_required
def staff_document_download(request, pk):

    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        return HttpResponse(
            "Staff account is not linked to an employee record.",
            status=403,
        )

    document = get_object_or_404(
        EmployeeDocument,
        pk=pk,
        employee=employee,
    )

    if not document.file:
        return HttpResponse(
            "This document has no file attached.",
            status=404,
        )

    try:
        file_handle = document.file.open("rb")
    except Exception:
        return HttpResponse(
            "The requested document could not be opened.",
            status=404,
        )

    filename = Path(document.file.name).name

    return FileResponse(
        file_handle,
        as_attachment=True,
        filename=filename,
    )


@login_required
def staff_payslip_list(request):

    support_staff = (
        getattr(getattr(request.user, "profile", None), "role", None) == "STAFF"
        and get_staff_teacher(request.user) is None
    )

    if not (
        support_staff
        or user_has_role_permission(request.user, "view_payslip")
    ):
        messages.error(
            request,
            "You do not have permission to access Payroll."
        )
        return redirect("accounts:staff_dashboard")
    employee = _get_logged_in_staff_employee(request)

    month = request.GET.get("month", "").strip()
    year = request.GET.get("year", "").strip()

    payslips = Payslip.objects.none()

    active_years = get_active_school_years()

    period_selected = False
    period_valid = False

    month_number = None
    year_number = None

    try:
        month_number = int(month)
        year_number = int(year)

        if (
            1 <= month_number <= 12
            and year_number in active_years
        ):
            period_selected = True
            period_valid = True

    except (TypeError, ValueError):
        pass

    if employee and period_valid:

        payslips = Payslip.objects.filter(
            payroll_record__employee=employee,
            payroll_record__payroll_period__month=month_number,
            payroll_record__payroll_period__year=year_number,
        ).select_related(
            "payroll_record",
            "payroll_record__employee",
            "payroll_record__payroll_period",
        ).order_by(
            "-generated_at",
        )

    return render(
        request,
        "hr_payroll/staff_payslip_list.html",
        {
            "payslips": payslips,
            "active_years": active_years,
            "selected_month": month,
            "selected_year": year,
            "employee": employee,
            "period_selected": period_selected,
            "period_valid": period_valid,
        },
    )


PAYSLIP_NAVY = HexColor("#123B7A")
PAYSLIP_BLUE = HexColor("#1769E0")
PAYSLIP_TEAL = HexColor("#008C95")
PAYSLIP_SKY = HexColor("#EAF4FF")
PAYSLIP_MINT = HexColor("#E9F8F5")
PAYSLIP_GOLD = HexColor("#F4B400")
PAYSLIP_LIGHT = HexColor("#F5F8FC")
PAYSLIP_DARK = HexColor("#1F2937")
PAYSLIP_BORDER = HexColor("#D7E1EE")
PAYSLIP_LIGHT_BLUE = HexColor("#EFF6FF")
PAYSLIP_LIGHT_TEAL = HexColor("#ECFDF5")
PAYSLIP_GREEN = HexColor("#15803D")





# ============================================================
# COLOURFUL PAYSLIP TABLE DRAWER
# ============================================================

def _draw_colourful_table(
    pdf,
    left,
    right,
    y,
    rows,
    header_title,
    header_colour,
    amount_prefix="KSh ",
    label_width=None,
    highlight_last=False,
):
    """
    Draws a professional colourful payslip table.

    rows:
        list of (label, value)

    Returns the new y position below the table.
    """

    table_width = right - left

    if label_width is None:
        label_width = table_width * 0.64

    amount_width = table_width - label_width

    row_height = 7 * mm
    header_height = 9 * mm

    # --------------------------------------------------------
    # TABLE HEADER
    # --------------------------------------------------------

    pdf.setFillColor(header_colour)

    pdf.roundRect(
        left,
        y - header_height,
        table_width,
        header_height,
        2 * mm,
        fill=1,
        stroke=0,
    )

    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 10)

    pdf.drawString(
        left + 4 * mm,
        y - 6 * mm,
        header_title,
    )

    pdf.drawRightString(
        right - 4 * mm,
        y - 6 * mm,
        "AMOUNT (KSh)",
    )

    y -= header_height

    # --------------------------------------------------------
    # TABLE ROWS
    # --------------------------------------------------------

    for index, (label, value) in enumerate(rows):

        row_top = y
        row_bottom = y - row_height

        # Alternating background
        if index % 2 == 0:
            pdf.setFillColor(PAYSLIP_LIGHT_BLUE)
        else:
            pdf.setFillColor(white)

        pdf.rect(
            left,
            row_bottom,
            table_width,
            row_height,
            fill=1,
            stroke=0,
        )

        # Highlight final row
        if highlight_last and index == len(rows) - 1:
            pdf.setFillColor(PAYSLIP_LIGHT_TEAL)

            pdf.rect(
                left,
                row_bottom,
                table_width,
                row_height,
                fill=1,
                stroke=0,
            )

        # Borders
        pdf.setStrokeColor(PAYSLIP_BORDER)
        pdf.setLineWidth(0.45)

        pdf.rect(
            left,
            row_bottom,
            table_width,
            row_height,
            fill=0,
            stroke=1,
        )

        # Vertical divider
        pdf.line(
            left + label_width,
            row_bottom,
            left + label_width,
            row_top,
        )

        # Text
        if highlight_last and index == len(rows) - 1:
            pdf.setFillColor(PAYSLIP_GREEN)
            pdf.setFont("Helvetica-Bold", 9)
        else:
            pdf.setFillColor(PAYSLIP_DARK)
            pdf.setFont("Helvetica", 8.8)

        pdf.drawString(
            left + 3 * mm,
            row_bottom + 2.3 * mm,
            str(label),
        )

        try:
            numeric_value = float(value)
            amount_text = f"{numeric_value:,.2f}"
        except (TypeError, ValueError):
            amount_text = str(value)

        if highlight_last and index == len(rows) - 1:
            pdf.setFillColor(PAYSLIP_GREEN)
            pdf.setFont("Helvetica-Bold", 10)
        else:
            pdf.setFillColor(PAYSLIP_DARK)
            pdf.setFont("Helvetica", 8.8)

        pdf.drawRightString(
            right - 3 * mm,
            row_bottom + 2.3 * mm,
            amount_text,
        )

        y = row_bottom

    return y - 5 * mm


def _draw_employee_information_table(
    pdf,
    left,
    right,
    y,
    rows,
):
    """
    Draws the employee information as a colourful
    two-column label/value table.
    """

    table_width = right - left
    label_width = 48 * mm
    row_height = 7 * mm
    header_height = 9 * mm

    # --------------------------------------------------------
    # HEADER
    # --------------------------------------------------------

    pdf.setFillColor(PAYSLIP_BLUE)

    pdf.roundRect(
        left,
        y - header_height,
        table_width,
        header_height,
        2 * mm,
        fill=1,
        stroke=0,
    )

    pdf.setFillColor(white)
    pdf.setFont("Helvetica-Bold", 10)

    pdf.drawString(
        left + 4 * mm,
        y - 6 * mm,
        "EMPLOYEE INFORMATION",
    )

    y -= header_height

    # --------------------------------------------------------
    # ROWS
    # --------------------------------------------------------

    for index, (label, value) in enumerate(rows):

        row_top = y
        row_bottom = y - row_height

        if index % 2 == 0:
            pdf.setFillColor(PAYSLIP_LIGHT_BLUE)
        else:
            pdf.setFillColor(white)

        pdf.rect(
            left,
            row_bottom,
            table_width,
            row_height,
            fill=1,
            stroke=0,
        )

        pdf.setStrokeColor(PAYSLIP_BORDER)
        pdf.setLineWidth(0.45)

        pdf.rect(
            left,
            row_bottom,
            table_width,
            row_height,
            fill=0,
            stroke=1,
        )

        pdf.line(
            left + label_width,
            row_bottom,
            left + label_width,
            row_top,
        )

        pdf.setFillColor(PAYSLIP_NAVY)
        pdf.setFont("Helvetica-Bold", 8.7)

        pdf.drawString(
            left + 3 * mm,
            row_bottom + 2.3 * mm,
            str(label),
        )

        pdf.setFillColor(PAYSLIP_DARK)
        pdf.setFont("Helvetica", 8.7)

        pdf.drawString(
            left + label_width + 3 * mm,
            row_bottom + 2.3 * mm,
            str(value),
        )

        y = row_bottom

    return y - 5 * mm


def _draw_net_salary_box(
    pdf,
    left,
    right,
    y,
    amount,
):
    """
    Large green net salary summary box.
    """

    height = 17 * mm

    pdf.setFillColor(PAYSLIP_GREEN)

    pdf.roundRect(
        left,
        y - height,
        right - left,
        height,
        3 * mm,
        fill=1,
        stroke=0,
    )

    pdf.setFillColor(white)

    pdf.setFont(
        "Helvetica-Bold",
        12,
    )

    pdf.drawString(
        left + 5 * mm,
        y - 7 * mm,
        "NET SALARY",
    )

    pdf.setFont(
        "Helvetica-Bold",
        15,
    )

    pdf.drawRightString(
        right - 5 * mm,
        y - 8 * mm,
        f"KSh {amount:,.2f}",
    )

    return y - height - 6 * mm


def _get_active_school_branding():
    return (
        SchoolBranding.objects
        .filter(is_active=True)
        .order_by("-updated_at")
        .first()
    )


@login_required
def staff_payslip_view(request, pk):

    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        messages.error(
            request,
            "Your staff account is not linked to an employee record.",
        )
        return redirect("accounts:staff_dashboard")

    payslip = get_object_or_404(
        Payslip.objects.select_related(
            "payroll_record",
            "payroll_record__employee",
            "payroll_record__payroll_period",
        ),
        pk=pk,
        payroll_record__employee=employee,
    )

    record = payslip.payroll_record

    loan_remaining_balance = _get_employee_loan_remaining_balance(
        employee
    )

    return render(
        request,
        "hr_payroll/staff_payslip_detail.html",
        {
            "payslip": payslip,
            "record": record,
            "employee": employee,
            "period": record.payroll_period,
            "personal_relief": get_current_personal_relief_amount(),
            "loan_remaining_balance": loan_remaining_balance,
            "branding": _get_active_school_branding(),
        },
    )


@login_required
def staff_payslip_print(request, pk):

    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        messages.error(
            request,
            "Your staff account is not linked to an employee record.",
        )
        return redirect("accounts:staff_dashboard")

    payslip = get_object_or_404(
        Payslip.objects.select_related(
            "payroll_record",
            "payroll_record__employee",
            "payroll_record__payroll_period",
        ),
        pk=pk,
        payroll_record__employee=employee,
    )

    record = payslip.payroll_record

    loan_remaining_balance = _get_employee_loan_remaining_balance(
        employee
    )

    return render(
        request,
        "hr_payroll/staff_payslip_print.html",
        {
            "payslip": payslip,
            "record": record,
            "employee": employee,
            "period": record.payroll_period,
            "personal_relief": get_current_personal_relief_amount(),
            "loan_remaining_balance": loan_remaining_balance,
        },
    )


# ============================================================
# STAFF PAYSLIP PDF
# ============================================================

@login_required
def staff_payslip_pdf(request, pk):

    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        return HttpResponse(
            "Staff account is not linked to an employee record.",
            status=403,
        )

    payslip = get_object_or_404(
        Payslip.objects.select_related(
            "payroll_record",
            "payroll_record__employee",
            "payroll_record__payroll_period",
        ),
        pk=pk,
        payroll_record__employee=employee,
    )

    record = payslip.payroll_record
    period = record.payroll_period

    response = HttpResponse(
        content_type="application/pdf"
    )

    response[
        "Content-Disposition"
    ] = (
        f'inline; filename="Payslip-'
        f'{payslip.payslip_number}.pdf"'
    )

    pdf = canvas.Canvas(
        response,
        pagesize=A4,
    )

    width, height = A4

    left = 20 * mm
    right = width - (20 * mm)

    y = height - (22 * mm)

    # --------------------------------------------------------
    # COLOURFUL DYNAMIC SCHOOL HEADER
    # --------------------------------------------------------

    branding = _get_active_school_branding()

    school_name = (
        branding.school_name
        if branding and branding.school_name
        else "School"
    )

    motto = (
        branding.motto
        if branding and branding.motto
        else ""
    )

    contact_parts = []

    if branding:
        if branding.phone:
            contact_parts.append(str(branding.phone))

        if branding.alternative_phone:
            contact_parts.append(
                str(branding.alternative_phone)
            )

        if branding.email:
            contact_parts.append(
                str(branding.email)
            )

        if branding.website:
            contact_parts.append(
                str(branding.website)
            )

    # Header background
    pdf.setFillColor(PAYSLIP_NAVY)
    pdf.roundRect(
        left - 5 * mm,
        y - 52 * mm,
        right - left + 10 * mm,
        56 * mm,
        5 * mm,
        fill=1,
        stroke=0,
    )

    # --------------------------------------------------------
    # CENTERED LOGO
    # --------------------------------------------------------

    if branding and branding.logo:
        try:
            logo_size = 25 * mm

            pdf.drawImage(
                ImageReader(branding.logo.path),
                (width - logo_size) / 2,
                y - 23 * mm,
                width=logo_size,
                height=logo_size,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
        except Exception:
            pass

    y -= 27 * mm

    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.setFont(
        "Helvetica-Bold",
        19,
    )

    pdf.drawCentredString(
        width / 2,
        y,
        school_name,
    )

    y -= 7 * mm

    if motto:
        pdf.setFont(
            "Helvetica-Oblique",
            9,
        )

        pdf.drawCentredString(
            width / 2,
            y,
            motto,
        )

        y -= 5 * mm

    if contact_parts:
        pdf.setFont(
            "Helvetica",
            7.5,
        )

        pdf.drawCentredString(
            width / 2,
            y,
            " | ".join(contact_parts),
        )

        y -= 5 * mm

    # Payslip banner
    pdf.setFillColor(PAYSLIP_TEAL)
    pdf.roundRect(
        left + 20 * mm,
        y - 10 * mm,
        right - left - 40 * mm,
        13 * mm,
        3 * mm,
        fill=1,
        stroke=0,
    )

    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.setFont(
        "Helvetica-Bold",
        13,
    )

    pdf.drawCentredString(
        width / 2,
        y - 5.5 * mm,
        "STAFF PAYSLIP",
    )

    y -= 15 * mm

    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.setFont(
        "Helvetica",
        8.5,
    )

    pdf.drawCentredString(
        width / 2,
        y,
        f"Payslip No: {payslip.payslip_number}",
    )

    y -= 7 * mm

    # White separator
    pdf.setStrokeColor(HexColor("#FFFFFF"))
    pdf.setLineWidth(0.8)
    pdf.line(
        left,
        y,
        right,
        y,
    )

    y -= 12 * mm

    # Reset text colour
    pdf.setFillColor(PAYSLIP_DARK)


    # --------------------------------------------------------
    # EMPLOYEE INFORMATION TABLE
    # --------------------------------------------------------

    employee_rows = [
        (
            "Employee Number",
            employee.employee_number or "â€”",
        ),
        (
            "Employee Name",
            employee.full_name or "â€”",
        ),
        (
            "Department",
            str(employee.department)
            if employee.department
            else "â€”",
        ),
        (
            "Position",
            str(employee.position)
            if employee.position
            else "â€”",
        ),
        (
            "Payroll Period",
            str(period.name),
        ),
    ]

    y = _draw_employee_information_table(
        pdf,
        left,
        right,
        y,
        employee_rows,
    )

    # --------------------------------------------------------
    # EARNINGS TABLE
    # --------------------------------------------------------

    earnings = [
        (
            "Basic Salary",
            record.basic_salary,
        ),
        (
            "Total Allowances",
            record.total_allowances,
        ),
        (
            "Gross Salary",
            record.gross_salary,
        ),
    ]

    y = _draw_colourful_table(
        pdf,
        left,
        right,
        y,
        earnings,
        "EARNINGS",
        PAYSLIP_TEAL,
        highlight_last=True,
    )

    # --------------------------------------------------------
    # DEDUCTIONS TABLE
    # --------------------------------------------------------

    deductions = [
        (
            "PAYE",
            record.paye,
        ),
        (
            "Personal Relief",
            personal_relief,
        ),
        (
            "NSSF",
            record.nssf,
        ),
        (
            "SHA",
            record.sha,
        ),
        (
            "Housing Levy",
            record.housing_levy,
        ),
        (
            "Loan Deduction",
            f"{record.loan_deductions or Decimal('0.00'):.2f} "
            f"(Balance Remaining: "
            f"{_get_employee_loan_remaining_balance(record.employee):.2f})",
        ),
        (
            "Other Deductions",
            record.other_deductions,
        ),
        (
            "Total Deductions",
            record.total_deductions,
        ),
    ]

    y = _draw_colourful_table(
        pdf,
        left,
        right,
        y,
        deductions,
        "DEDUCTIONS",
        PAYSLIP_NAVY,
        highlight_last=True,
    )

    # --------------------------------------------------------
    # NET SALARY
    # --------------------------------------------------------

    y = _draw_net_salary_box(
        pdf,
        left,
        right,
        y,
        record.net_salary,
    )

    # --------------------------------------------------------
    # FOOTER
    # --------------------------------------------------------

    pdf.setStrokeColor(PAYSLIP_BORDER)
    pdf.setLineWidth(0.5)

    pdf.line(
        left,
        y + 2 * mm,
        right,
        y + 2 * mm,
    )

    pdf.setFillColor(PAYSLIP_DARK)
    pdf.setFont(
        "Helvetica",
        7.5,
    )

    pdf.drawString(
        left,
        y - 3 * mm,
        "Generated by Luhan School ERP",
    )

    pdf.drawRightString(
        right,
        y - 3 * mm,
        f"Payslip: {payslip.payslip_number}",
    )

    pdf.showPage()
    pdf.save()

    return response


def _get_employee_loan_remaining_balance(employee):
    """
    Return the employee's current remaining balance across active staff loans.
    This is display-only and does not modify any loan or payroll record.
    """

    loans = StaffLoan.objects.filter(
        employee=employee,
        status="ACTIVE",
    )

    remaining_balance = Decimal("0.00")

    for loan in loans:
        principal = (
            loan.principal_amount
            or Decimal("0.00")
        )

        amount_paid = (
            loan.amount_paid
            or Decimal("0.00")
        )

        balance = (
            principal - amount_paid
        ).quantize(
            Decimal("0.01")
        )

        if balance > Decimal("0.00"):
            remaining_balance += balance

    return remaining_balance.quantize(
        Decimal("0.01")
    )


# ============================================================
# PAYSLIP VIEW
# ============================================================

@login_required
@role_permission_required("view_payslip", "hr_payroll")
def payslip_view(request, pk):

    payslip = get_object_or_404(
        Payslip.objects.select_related(
            "payroll_record",
            "payroll_record__employee",
            "payroll_record__payroll_period",
        ),
        pk=pk,
    )

    record = payslip.payroll_record
    employee = record.employee

    loan_remaining_balance = _get_employee_loan_remaining_balance(
        employee
    )

    return render(
        request,
        "hr_payroll/payslip_detail.html",
        {
            "payslip": payslip,
            "record": record,
            "employee": employee,
            "period": record.payroll_period,
            "loan_remaining_balance": loan_remaining_balance,
            "branding": _get_active_school_branding(),
        },
    )


# ============================================================
# PAYSLIP EDIT
# ============================================================

class PayslipEditForm(forms.ModelForm):

    class Meta:
        model = PayrollRecord

        fields = [
            "basic_salary",
            "total_allowances",
            "gross_salary",
            "total_deductions",
            "taxable_income",
            "paye",
            "nssf",
            "sha",
            "housing_levy",
            "loan_deductions",
            "other_deductions",
            "net_salary",
        ]

        widgets = {
            "basic_salary": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "total_allowances": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "gross_salary": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "total_deductions": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "taxable_income": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "paye": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "nssf": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "sha": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "housing_levy": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "loan_deductions": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "other_deductions": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),

            "net_salary": forms.NumberInput(
                attrs={
                    "step": "0.01",
                    "min": "0",
                }
            ),
        }


@login_required
@role_permission_required("change_payslip", "hr_payroll")
def payslip_edit(request, pk):

    payslip = get_object_or_404(
        Payslip.objects.select_related(
            "payroll_record",
            "payroll_record__employee",
            "payroll_record__payroll_period",
        ),
        pk=pk,
    )

    record = payslip.payroll_record

    if request.method == "POST":

        form = PayslipEditForm(
            request.POST,
            instance=record,
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                f"Payslip {payslip.payslip_number} updated successfully.",
            )

            return redirect(
                "hr_payroll:payslip_view",
                pk=payslip.pk,
            )

    else:

        form = PayslipEditForm(
            instance=record,
        )

    return render(
        request,
        "hr_payroll/payslip_edit.html",
        {
            "form": form,
            "payslip": payslip,
            "record": record,
            "employee": record.employee,
            "period": record.payroll_period,
            "title": f"Edit Payslip - {payslip.payslip_number}",
            "cancel_url": "hr_payroll:payslip_view",
            "cancel_pk": payslip.pk,
        },
    )


# ============================================================
# PAYSLIP PRINT
# ============================================================

@login_required
@role_permission_required("view_payslip", "hr_payroll")
def payslip_print(request, pk):

    payslip = get_object_or_404(
        Payslip.objects.select_related(
            "payroll_record",
            "payroll_record__employee",
            "payroll_record__payroll_period",
        ),
        pk=pk,
    )

    record = payslip.payroll_record
    employee = record.employee
    period = record.payroll_period

    response = HttpResponse(
        content_type="application/pdf"
    )

    response[
        "Content-Disposition"
    ] = (
        f'inline; filename="Payslip-'
        f'{payslip.payslip_number}.pdf"'
    )

    pdf = canvas.Canvas(
        response,
        pagesize=A4,
    )

    width, height = A4

    left = 20 * mm
    right = width - (20 * mm)

    y = height - (22 * mm)

    # ========================================================
    # COLOURFUL DYNAMIC SCHOOL HEADER
    # ========================================================

    branding = _get_active_school_branding()

    school_name = (
        branding.school_name
        if branding and branding.school_name
        else "School"
    )

    motto = (
        branding.motto
        if branding and branding.motto
        else ""
    )

    contact_parts = []

    if branding:
        if branding.phone:
            contact_parts.append(str(branding.phone))

        if branding.alternative_phone:
            contact_parts.append(
                str(branding.alternative_phone)
            )

        if branding.email:
            contact_parts.append(
                str(branding.email)
            )

        if branding.website:
            contact_parts.append(
                str(branding.website)
            )

    # Header background
    pdf.setFillColor(PAYSLIP_NAVY)
    pdf.roundRect(
        left - 5 * mm,
        y - 52 * mm,
        right - left + 10 * mm,
        56 * mm,
        5 * mm,
        fill=1,
        stroke=0,
    )

    # Centered logo
    if branding and branding.logo:
        try:
            logo_size = 25 * mm

            pdf.drawImage(
                ImageReader(branding.logo.path),
                (width - logo_size) / 2,
                y - 23 * mm,
                width=logo_size,
                height=logo_size,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
        except Exception:
            pass

    y -= 27 * mm

    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.setFont(
        "Helvetica-Bold",
        19,
    )

    pdf.drawCentredString(
        width / 2,
        y,
        school_name,
    )

    y -= 7 * mm

    if motto:
        pdf.setFont(
            "Helvetica-Oblique",
            9,
        )

        pdf.drawCentredString(
            width / 2,
            y,
            motto,
        )

        y -= 5 * mm

    if contact_parts:
        pdf.setFont(
            "Helvetica",
            7.5,
        )

        pdf.drawCentredString(
            width / 2,
            y,
            " | ".join(contact_parts),
        )

        y -= 5 * mm

    pdf.setFillColor(PAYSLIP_TEAL)
    pdf.roundRect(
        left + 20 * mm,
        y - 10 * mm,
        right - left - 40 * mm,
        13 * mm,
        3 * mm,
        fill=1,
        stroke=0,
    )

    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.setFont(
        "Helvetica-Bold",
        13,
    )

    pdf.drawCentredString(
        width / 2,
        y - 5.5 * mm,
        "STAFF PAYSLIP",
    )

    y -= 15 * mm

    pdf.setFont(
        "Helvetica",
        8.5,
    )

    pdf.drawCentredString(
        width / 2,
        y,
        f"Payslip No: {payslip.payslip_number}",
    )

    y -= 7 * mm

    pdf.setStrokeColor(HexColor("#FFFFFF"))
    pdf.setLineWidth(0.8)

    pdf.line(
        left,
        y,
        right,
        y,
    )

    y -= 12 * mm

    pdf.setFillColor(PAYSLIP_DARK)


    # ========================================================
    # EMPLOYEE INFORMATION TABLE
    # ========================================================

    employee_data = [
        (
            "Employee Number",
            str(employee.employee_number or "â€”"),
        ),
        (
            "Employee Name",
            str(employee.full_name or "â€”"),
        ),
        (
            "Department",
            str(employee.department or "â€”"),
        ),
        (
            "Position",
            str(employee.position or "â€”"),
        ),
        (
            "Payroll Period",
            str(period.name or "â€”"),
        ),
        (
            "Generated",
            payslip.generated_at.strftime(
                "%d %b %Y %H:%M"
            ),
        ),
    ]

    y = _draw_employee_information_table(
        pdf,
        left,
        right,
        y,
        employee_data,
    )

    # ========================================================
    # EARNINGS TABLE
    # ========================================================

    earnings = [
        (
            "Basic Salary",
            record.basic_salary,
        ),
        (
            "Total Allowances",
            record.total_allowances,
        ),
        (
            "Gross Salary",
            record.gross_salary,
        ),
    ]

    y = _draw_colourful_table(
        pdf,
        left,
        right,
        y,
        earnings,
        "EARNINGS",
        PAYSLIP_TEAL,
        highlight_last=True,
    )

    # ========================================================
    # DEDUCTIONS TABLE
    # ========================================================

    deductions = [
        (
            "PAYE",
            record.paye,
        ),
        (
            "Personal Relief",
            2400,
        ),
        (
            "NSSF",
            record.nssf,
        ),
        (
            "SHA",
            record.sha,
        ),
        (
            "Housing Levy",
            record.housing_levy,
        ),
        (
            "Loan Deduction",
            f"{record.loan_deductions or Decimal('0.00'):.2f} "
            f"(Balance Remaining: "
            f"{_get_employee_loan_remaining_balance(record.employee):.2f})",
        ),
        (
            "Other Deductions",
            record.other_deductions,
        ),
        (
            "Total Deductions",
            record.total_deductions,
        ),
    ]

    y = _draw_colourful_table(
        pdf,
        left,
        right,
        y,
        deductions,
        "DEDUCTIONS",
        PAYSLIP_NAVY,
        highlight_last=True,
    )

    # ========================================================
    # NET SALARY
    # ========================================================

    y = _draw_net_salary_box(
        pdf,
        left,
        right,
        y,
        record.net_salary,
    )

    # ========================================================
    # FOOTER
    # ========================================================

    pdf.setStrokeColor(PAYSLIP_BORDER)
    pdf.setLineWidth(0.5)

    pdf.line(
        left,
        y + 2 * mm,
        right,
        y + 2 * mm,
    )

    pdf.setFillColor(PAYSLIP_DARK)
    pdf.setFont(
        "Helvetica",
        7.5,
    )

    pdf.drawString(
        left,
        y - 3 * mm,
        "Generated by Luhan School ERP",
    )

    pdf.drawRightString(
        right,
        y - 3 * mm,
        f"Payslip: {payslip.payslip_number}",
    )

    pdf.showPage()
    pdf.save()

    return response

# ============================================================
# PAYSLIP DELETE
# ============================================================

@login_required
@role_permission_required("delete_payslip", "hr_payroll")
def payslip_delete(request, pk):

    payslip = get_object_or_404(
        Payslip,
        pk=pk,
    )

    if request.method == "POST":

        payslip_number = payslip.payslip_number

        payslip.delete()

        messages.success(
            request,
            f"Payslip {payslip_number} deleted successfully.",
        )

        return redirect(
            "hr_payroll:payslip_list",
        )

    return render(
        request,
        "hr_payroll/payslip_delete.html",
        {
            "payslip": payslip,
        },
    )


# ============================================================
# APPRAISALS
# ============================================================

@login_required
@role_permission_required("view_performanceappraisal", "hr_payroll")
def appraisal_list(request):

    appraisals = PerformanceAppraisal.objects.select_related(
        "employee",
    ).order_by(
        "-appraisal_date",
    )

    return render(
        request,
        "hr_payroll/appraisal_list.html",
        {"appraisals": appraisals},
    )


@login_required
@role_permission_required("add_performanceappraisal", "hr_payroll")
def appraisal_add(request):

    return form_page(
        request,
        PerformanceAppraisalForm,
        "Add Performance Appraisal",
        "hr_payroll:appraisal_list",
    )


@login_required
@role_permission_required("change_performanceappraisal", "hr_payroll")
def appraisal_edit(request, pk):

    obj = get_object_or_404(
        PerformanceAppraisal,
        pk=pk,
    )

    return form_page(
        request,
        PerformanceAppraisalForm,
        "Edit Performance Appraisal",
        "hr_payroll:appraisal_list",
        instance=obj,
    )


@login_required
@role_permission_required("change_performanceappraisal", "hr_payroll")
def appraisal_status(request, pk, status):

    appraisal = get_object_or_404(
        PerformanceAppraisal,
        pk=pk,
    )

    valid_statuses = {
        "DRAFT",
        "SUBMITTED",
        "REVIEWED",
        "COMPLETED",
    }

    if request.method == "POST" and status in valid_statuses:

        appraisal.status = status
        appraisal.save(update_fields=["status"])

        messages.success(
            request,
            f"Appraisal status changed to {status}.",
        )

    return redirect(
        "hr_payroll:appraisal_list",
    )


# ============================================================
# REPORTS
# ============================================================

@login_required
@role_permission_required("view_payrollrecord", "hr_payroll")
def hr_reports(request):

    context = {
        "total_employees":
            Employee.objects.count(),

        "active_employees":
            Employee.objects.filter(
                employment_status="ACTIVE",
                is_active=True,
            ).count(),

        "departments":
            Department.objects.filter(
                is_active=True,
            ).count(),

        "attendance_count":
            Attendance.objects.count(),

        "leave_count":
            LeaveApplication.objects.count(),

        "loan_count":
            StaffLoan.objects.count(),

        "payroll_count":
            PayrollRecord.objects.count(),

        "appraisal_count":
            PerformanceAppraisal.objects.count(),

        "payslip_count":
            Payslip.objects.count(),

        "document_count":
            EmployeeDocument.objects.count(),

        "active_loan_count":
            StaffLoan.objects.filter(
                status="ACTIVE",
            ).count(),
    }

    return render(
        request,
        "hr_payroll/reports.html",
        context,
    )


# ============================================================
# STAFF LOAN APPLICATION WORKFLOW
# ============================================================

class StaffLoanApplicationForm(forms.ModelForm):

    class Meta:
        model = LoanApplication
        fields = [
            "loan_name",
            "requested_amount",
            "requested_installment",
            "repayment_months",
            "purpose",
            "supporting_document",
        ]
        widgets = {
            "loan_name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. Emergency Loan, Development Loan",
            }),
            "requested_amount": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1",
                "step": "0.01",
                "placeholder": "0.00",
            }),
            "requested_installment": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0.01",
                "step": "0.01",
                "placeholder": "Preferred monthly deduction",
            }),
            "repayment_months": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1",
                "max": "120",
                "placeholder": "Number of months",
            }),
            "purpose": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Explain why you are requesting the loan...",
            }),
            "supporting_document": forms.ClearableFileInput(attrs={
                "class": "form-control",
            }),
        }

    def clean_requested_amount(self):
        amount = self.cleaned_data["requested_amount"]

        if amount <= Decimal("0.00"):
            raise forms.ValidationError(
                "Loan amount must be greater than zero."
            )

        return amount

    def clean_requested_installment(self):
        installment = self.cleaned_data.get("requested_installment")

        if installment is not None and installment <= Decimal("0.00"):
            raise forms.ValidationError(
                "Monthly installment must be greater than zero."
            )

        return installment

    def clean_repayment_months(self):
        months = self.cleaned_data.get("repayment_months")

        if months is not None and months < 1:
            raise forms.ValidationError(
                "Repayment period must be at least one month."
            )

        return months


class LoanApplicationApprovalForm(forms.Form):

    approved_amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        label="Approved Amount",
    )

    approved_installment = forms.DecimalField(
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        label="Monthly Installment",
    )

    repayment_months = forms.IntegerField(
        min_value=1,
        max_value=120,
        label="Repayment Period (Months)",
    )

    admin_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Approval notes...",
        }),
    )


class LoanApplicationRejectForm(forms.Form):

    admin_notes = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            "rows": 4,
            "placeholder": "Reason for rejecting this application...",
        }),
        label="Reason",
    )


def _staff_loan_access_allowed(request):
    support_staff = (
        getattr(
            getattr(request.user, "profile", None),
            "role",
            None,
        ) == "STAFF"
        and get_staff_teacher(request.user) is None
    )

    return (
        support_staff
        or user_has_role_permission(
            request.user,
            "view_staffloan",
        )
    )


def _add_months_to_date(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1

    day = min(
        value.day,
        calendar.monthrange(year, month)[1],
    )

    return date(year, month, day)


@login_required
def staff_loan_apply(request):

    if not _staff_loan_access_allowed(request):
        messages.error(
            request,
            "You do not have permission to access Loans.",
        )
        return redirect("accounts:staff_dashboard")

    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        messages.error(
            request,
            "Your staff account is not linked to an employee record.",
        )
        return redirect("accounts:staff_dashboard")

    active_count = StaffLoan.objects.filter(
        employee=employee,
        status="ACTIVE",
    ).count()

    pending_count = LoanApplication.objects.filter(
        employee=employee,
        status__in=[
            "SUBMITTED",
            "UNDER_REVIEW",
            "APPROVED",
        ],
    ).count()

    if request.method == "POST":

        if active_count > 0:
            messages.error(
                request,
                "You currently have an active loan. Please clear it before applying for another loan.",
            )
            return redirect("hr_payroll:staff_loan_list")

        form = StaffLoanApplicationForm(
            request.POST,
            request.FILES,
        )

        declaration = request.POST.get("declaration") == "on"

        if not declaration:
            form.add_error(
                None,
                "You must accept the declaration before submitting your application.",
            )

        if pending_count > 0:
            form.add_error(
                None,
                "You already have a loan application under review.",
            )

        if form.is_valid():

            application = form.save(commit=False)
            application.employee = employee
            application.status = "SUBMITTED"
            application.submitted_at = timezone.now()
            application.save()

            messages.success(
                request,
                f"Loan application {application.application_number} submitted successfully.",
            )

            return redirect(
                "hr_payroll:staff_loan_application_detail",
                pk=application.pk,
            )

    else:
        form = StaffLoanApplicationForm()

    return render(
        request,
        "hr_payroll/staff_loan_apply.html",
        {
            "employee": employee,
            "form": form,
            "active_count": active_count,
            "pending_count": pending_count,
        },
    )


@login_required
def staff_loan_application_detail(request, pk):

    if not _staff_loan_access_allowed(request):
        messages.error(
            request,
            "You do not have permission to access Loans.",
        )
        return redirect("accounts:staff_dashboard")

    employee = _get_logged_in_staff_employee(request)

    if employee is None:
        messages.error(
            request,
            "Your staff account is not linked to an employee record.",
        )
        return redirect("accounts:staff_dashboard")

    application = get_object_or_404(
        LoanApplication.objects.select_related(
            "employee",
            "reviewed_by",
            "staff_loan",
        ),
        pk=pk,
        employee=employee,
    )

    return render(
        request,
        "hr_payroll/staff_loan_application_detail.html",
        {
            "employee": employee,
            "application": application,
        },
    )


@login_required
@role_permission_required("view_staffloan", "hr_payroll")
def loan_applications(request):

    applications = (
        LoanApplication.objects
        .select_related(
            "employee",
            "reviewed_by",
            "staff_loan",
        )
        .order_by("-created_at")
    )

    status = request.GET.get("status", "").strip()

    if status:
        applications = applications.filter(status=status)

    search = request.GET.get("q", "").strip()

    if search:
        applications = applications.filter(
            Q(application_number__icontains=search)
            | Q(employee__first_name__icontains=search)
            | Q(employee__last_name__icontains=search)
            | Q(loan_name__icontains=search)
        )

    counts = {
        "submitted": LoanApplication.objects.filter(
            status="SUBMITTED"
        ).count(),
        "review": LoanApplication.objects.filter(
            status="UNDER_REVIEW"
        ).count(),
        "approved": LoanApplication.objects.filter(
            status="APPROVED"
        ).count(),
        "rejected": LoanApplication.objects.filter(
            status="REJECTED"
        ).count(),
        "disbursed": LoanApplication.objects.filter(
            status="DISBURSED"
        ).count(),
    }

    return render(
        request,
        "hr_payroll/loan_applications.html",
        {
            "applications": applications,
            "counts": counts,
            "selected_status": status,
            "search": search,
        },
    )


@login_required
@role_permission_required("view_staffloan", "hr_payroll")
def loan_application_detail(request, pk):

    application = get_object_or_404(
        LoanApplication.objects.select_related(
            "employee",
            "reviewed_by",
            "staff_loan",
        ),
        pk=pk,
    )

    approval_form = LoanApplicationApprovalForm(
        initial={
            "approved_amount": (
                application.approved_amount
                or application.requested_amount
            ),
            "approved_installment": (
                application.approved_installment
                or application.requested_installment
                or Decimal("0.00")
            ),
            "repayment_months": (
                application.repayment_months
                or 12
            ),
            "admin_notes": application.admin_notes or "",
        }
    )

    reject_form = LoanApplicationRejectForm(
        initial={
            "admin_notes": application.admin_notes or "",
        }
    )

    return render(
        request,
        "hr_payroll/loan_application_detail.html",
        {
            "application": application,
            "approval_form": approval_form,
            "reject_form": reject_form,
        },
    )


@login_required
@role_permission_required("change_staffloan", "hr_payroll")
def loan_application_approve(request, pk):

    if request.method != "POST":
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    application = get_object_or_404(
        LoanApplication,
        pk=pk,
    )

    if application.status not in (
        "SUBMITTED",
        "UNDER_REVIEW",
    ):
        messages.error(
            request,
            "This application cannot be approved in its current status.",
        )
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    form = LoanApplicationApprovalForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "Please correct the approval details.",
        )
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    approved_amount = form.cleaned_data["approved_amount"]
    approved_installment = form.cleaned_data[
        "approved_installment"
    ]
    repayment_months = form.cleaned_data["repayment_months"]

    if approved_amount > application.requested_amount:
        messages.error(
            request,
            "Approved amount cannot exceed the requested amount.",
        )
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    application.approved_amount = approved_amount
    application.approved_installment = approved_installment
    application.repayment_months = repayment_months
    application.admin_notes = form.cleaned_data["admin_notes"]
    application.status = "APPROVED"
    application.reviewed_by = request.user
    application.reviewed_at = timezone.now()
    application.approved_at = timezone.now()
    application.save()

    messages.success(
        request,
        f"{application.application_number} approved. It is now ready for disbursement.",
    )

    return redirect(
        "hr_payroll:loan_application_detail",
        pk=pk,
    )


@login_required
@role_permission_required("change_staffloan", "hr_payroll")
def loan_application_reject(request, pk):

    if request.method != "POST":
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    application = get_object_or_404(
        LoanApplication,
        pk=pk,
    )

    if application.status not in (
        "SUBMITTED",
        "UNDER_REVIEW",
    ):
        messages.error(
            request,
            "This application cannot be rejected in its current status.",
        )
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    form = LoanApplicationRejectForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "A rejection reason is required.",
        )
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    application.status = "REJECTED"
    application.admin_notes = form.cleaned_data["admin_notes"]
    application.reviewed_by = request.user
    application.reviewed_at = timezone.now()
    application.rejected_at = timezone.now()
    application.save()

    messages.success(
        request,
        f"{application.application_number} rejected.",
    )

    return redirect(
        "hr_payroll:loan_application_detail",
        pk=pk,
    )


@login_required
@role_permission_required("change_staffloan", "hr_payroll")
def loan_application_disburse(request, pk):

    if request.method != "POST":
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    application = get_object_or_404(
        LoanApplication.objects.select_related(
            "employee",
            "staff_loan",
        ),
        pk=pk,
    )

    if application.status != "APPROVED":
        messages.error(
            request,
            "Only approved applications can be disbursed.",
        )
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    if application.staff_loan_id:
        messages.error(
            request,
            "This application is already linked to a staff loan.",
        )
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    existing_active = StaffLoan.objects.filter(
        employee=application.employee,
        status="ACTIVE",
    ).exists()

    if existing_active:
        messages.error(
            request,
            "This employee already has an active loan.",
        )
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    approved_amount = (
        application.approved_amount
        or application.requested_amount
    )

    approved_installment = (
        application.approved_installment
        or application.requested_installment
    )

    if not approved_installment:
        messages.error(
            request,
            "An approved monthly installment is required before disbursement.",
        )
        return redirect(
            "hr_payroll:loan_application_detail",
            pk=pk,
        )

    start_date = timezone.localdate()

    end_date = None

    if application.repayment_months:
        end_date = _add_months_to_date(
            start_date,
            application.repayment_months,
        )

    with transaction.atomic():

        loan = StaffLoan.objects.create(
            employee=application.employee,
            loan_name=application.loan_name,
            principal_amount=approved_amount,
            monthly_installment=approved_installment,
            amount_paid=Decimal("0.00"),
            start_date=start_date,
            end_date=end_date,
            status="ACTIVE",
            notes=(
                f"Disbursed from loan application "
                f"{application.application_number}."
            ),
        )

        application.staff_loan = loan
        application.status = "DISBURSED"
        application.disbursed_at = timezone.now()
        application.save(
            update_fields=[
                "staff_loan",
                "status",
                "disbursed_at",
                "updated_at",
            ]
        )

    messages.success(
        request,
        f"{application.application_number} disbursed and added to payroll loans.",
    )

    return redirect(
        "hr_payroll:loan_application_detail",
        pk=pk,
    )
















