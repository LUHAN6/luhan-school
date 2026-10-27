from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


# ============================================================
# DEPARTMENT
# ============================================================

class Department(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    code = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    head = models.ForeignKey(
        "Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="headed_departments",
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# ============================================================
# JOB POSITION
# ============================================================

class JobPosition(models.Model):

    title = models.CharField(
        max_length=150,
        unique=True,
    )

    code = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True,
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="positions",
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title


# ============================================================
# EMPLOYEE
# ============================================================

class Employee(models.Model):

    GENDER_CHOICES = [
        ("MALE", "Male"),
        ("FEMALE", "Female"),
        ("OTHER", "Other"),
    ]

    EMPLOYMENT_TYPE_CHOICES = [
        ("PERMANENT", "Permanent"),
        ("CONTRACT", "Contract"),
        ("PART_TIME", "Part Time"),
        ("CASUAL", "Casual"),
        ("INTERN", "Intern"),
        ("PROBATION", "Probation"),
    ]

    EMPLOYMENT_STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("ON_LEAVE", "On Leave"),
        ("SUSPENDED", "Suspended"),
        ("TERMINATED", "Terminated"),
        ("RESIGNED", "Resigned"),
        ("RETIRED", "Retired"),
    ]

    # --------------------------------------------------------
    # PERSONAL DETAILS
    # --------------------------------------------------------

    employee_number = models.CharField(
        max_length=50,
        unique=True,
    )

    first_name = models.CharField(
        max_length=100,
    )

    middle_name = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    last_name = models.CharField(
        max_length=100,
    )

    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
        blank=True,
        null=True,
    )

    date_of_birth = models.DateField(
        blank=True,
        null=True,
    )

    national_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    kra_pin = models.CharField(
        max_length=30,
        blank=True,
        null=True,
    )

    nssf_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    sha_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
    )

    phone = models.CharField(
        max_length=30,
        blank=True,
        null=True,
    )

    email = models.EmailField(
        blank=True,
        null=True,
    )

    address = models.TextField(
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # EMPLOYMENT DETAILS
    # --------------------------------------------------------

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )

    position = models.ForeignKey(
        JobPosition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )

    employment_type = models.CharField(
        max_length=30,
        choices=EMPLOYMENT_TYPE_CHOICES,
        default="PERMANENT",
    )

    employment_status = models.CharField(
        max_length=30,
        choices=EMPLOYMENT_STATUS_CHOICES,
        default="ACTIVE",
    )

    date_joined = models.DateField(
        default=timezone.localdate,
    )

    contract_start_date = models.DateField(
        blank=True,
        null=True,
    )

    contract_end_date = models.DateField(
        blank=True,
        null=True,
    )

    date_left = models.DateField(
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # PAYROLL DETAILS
    # --------------------------------------------------------

    basic_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    bank_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    bank_account_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    bank_branch = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    payment_method = models.CharField(
        max_length=30,
        choices=[
            ("BANK", "Bank"),
            ("MPESA", "M-Pesa"),
            ("CASH", "Cash"),
        ],
        default="BANK",
    )

    # --------------------------------------------------------
    # EMERGENCY CONTACT
    # --------------------------------------------------------

    emergency_contact_name = models.CharField(
        max_length=150,
        blank=True,
        null=True,
    )

    emergency_contact_phone = models.CharField(
        max_length=30,
        blank=True,
        null=True,
    )

    emergency_contact_relationship = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )

    # --------------------------------------------------------
    # SYSTEM
    # --------------------------------------------------------

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "first_name",
            "last_name",
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):

        names = [
            self.first_name,
            self.middle_name,
            self.last_name,
        ]

        return " ".join(
            name.strip()
            for name in names
            if name
        )

    def clean(self):

        if (
            self.contract_start_date
            and self.contract_end_date
            and self.contract_end_date < self.contract_start_date
        ):
            raise ValidationError(
                "Contract end date cannot be before contract start date."
            )


# ============================================================
# EMPLOYEE DOCUMENT
# ============================================================

class EmployeeDocument(models.Model):

    DOCUMENT_TYPE_CHOICES = [
        ("ID", "National ID"),
        ("KRA_PIN", "KRA PIN"),
        ("NSSF", "NSSF Document"),
        ("SHA", "SHA Document"),
        ("CONTRACT", "Employment Contract"),
        ("CERTIFICATE", "Certificate"),
        ("ACADEMIC", "Academic Document"),
        ("OTHER", "Other"),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    document_type = models.CharField(
        max_length=30,
        choices=DOCUMENT_TYPE_CHOICES,
    )

    title = models.CharField(
        max_length=150,
    )

    file = models.FileField(
        upload_to="hr/employee_documents/",
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.employee.full_name} - {self.title}"


# ============================================================
# ATTENDANCE
# ============================================================

class Attendance(models.Model):

    STATUS_CHOICES = [
        ("PRESENT", "Present"),
        ("ABSENT", "Absent"),
        ("LATE", "Late"),
        ("LEAVE", "On Leave"),
        ("OFF", "Off Day"),
        ("HALF_DAY", "Half Day"),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )

    date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PRESENT",
    )

    check_in = models.TimeField(
        blank=True,
        null=True,
    )

    check_out = models.TimeField(
        blank=True,
        null=True,
    )

    remarks = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-date", "employee__first_name"]

        constraints = [
            models.UniqueConstraint(
                fields=["employee", "date"],
                name="unique_employee_attendance_per_day",
            )
        ]

    def __str__(self):
        return f"{self.employee.full_name} - {self.date}"


# ============================================================
# LEAVE TYPE
# ============================================================

class LeaveType(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    days_allowed = models.PositiveIntegerField(
        default=0,
    )

    is_paid = models.BooleanField(
        default=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return self.name


# ============================================================
# LEAVE APPLICATION
# ============================================================

class LeaveApplication(models.Model):

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("CANCELLED", "Cancelled"),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="leave_applications",
    )

    leave_type = models.ForeignKey(
        LeaveType,
        on_delete=models.PROTECT,
        related_name="applications",
    )

    start_date = models.DateField()

    end_date = models.DateField()

    days = models.PositiveIntegerField(
        default=1,
    )

    reason = models.TextField(
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="PENDING",
    )

    approved_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_leave_applications",
    )

    approved_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def clean(self):

        if self.end_date < self.start_date:
            raise ValidationError(
                "Leave end date cannot be before start date."
            )

        if self.days < 1:
            raise ValidationError(
                "Leave must be at least one day."
            )

    def __str__(self):
        return (
            f"{self.employee.full_name} - "
            f"{self.leave_type.name}"
        )


# ============================================================
# ALLOWANCE TYPE
# ============================================================

class AllowanceType(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    is_taxable = models.BooleanField(
        default=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return self.name


# ============================================================
# EMPLOYEE ALLOWANCE
# ============================================================

class EmployeeAllowance(models.Model):

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="allowances",
    )

    allowance_type = models.ForeignKey(
        AllowanceType,
        on_delete=models.PROTECT,
        related_name="employee_allowances",
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    effective_from = models.DateField(
        default=timezone.localdate,
    )

    effective_to = models.DateField(
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["employee__first_name"]

    def __str__(self):
        return (
            f"{self.employee.full_name} - "
            f"{self.allowance_type.name}"
        )


# ============================================================
# DEDUCTION TYPE
# ============================================================

class DeductionType(models.Model):

    CALCULATION_CHOICES = [
        ("FIXED", "Fixed Amount"),
        ("PERCENTAGE", "Percentage"),
    ]

    BASE_CHOICES = [
        ("BASIC", "Basic Salary"),
        ("GROSS", "Gross Salary"),
        ("TAXABLE", "Taxable Income"),
    ]

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    is_statutory = models.BooleanField(
        default=False,
    )

    is_compulsory = models.BooleanField(
        default=False,
    )

    calculation_method = models.CharField(
        max_length=20,
        choices=CALCULATION_CHOICES,
        default="FIXED",
    )

    calculation_base = models.CharField(
        max_length=20,
        choices=BASE_CHOICES,
        default="BASIC",
    )

    percentage = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
    )

    fixed_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    minimum_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    maximum_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    effective_from = models.DateField(
        default=timezone.localdate,
    )

    effective_to = models.DateField(
        blank=True,
        null=True,
    )

    is_percentage = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return self.name


# ============================================================
# PAYE TAX BANDS
# ============================================================

class PAYETaxBand(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    lower_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    upper_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        blank=True,
        null=True,
    )

    rate = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
    )

    effective_from = models.DateField(
        default=timezone.localdate,
    )

    effective_to = models.DateField(
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["lower_limit"]

    def __str__(self):
        return f"{self.name} - {self.rate}%"


# ============================================================
# PAYE RELIEF
# ============================================================

class PAYERelief(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    monthly_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    effective_from = models.DateField(
        default=timezone.localdate,
    )

    effective_to = models.DateField(
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# ============================================================
# NSSF RULES
# ============================================================

class NSSFRule(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    lower_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    upper_limit = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        blank=True,
        null=True,
    )

    employee_percentage = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
    )

    employee_cap = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    effective_from = models.DateField(
        default=timezone.localdate,
    )

    effective_to = models.DateField(
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["lower_limit"]

    def __str__(self):
        return self.name


# ============================================================
# EMPLOYEE DEDUCTION
# ============================================================

class EmployeeDeduction(models.Model):

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="deductions",
    )

    deduction_type = models.ForeignKey(
        DeductionType,
        on_delete=models.PROTECT,
        related_name="employee_deductions",
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    effective_from = models.DateField(
        default=timezone.localdate,
    )

    effective_to = models.DateField(
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["employee__first_name"]

    def __str__(self):
        return (
            f"{self.employee.full_name} - "
            f"{self.deduction_type.name}"
        )


# ============================================================
# STAFF LOAN
# ============================================================

class StaffLoan(models.Model):

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="loans",
    )

    loan_name = models.CharField(
        max_length=150,
    )

    principal_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    monthly_installment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    start_date = models.DateField()

    end_date = models.DateField(
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE",
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    @property
    def balance(self):
        return max(
            Decimal("0.00"),
            self.principal_amount - self.amount_paid,
        )

    def __str__(self):
        return (
            f"{self.employee.full_name} - "
            f"{self.loan_name}"
        )


# ============================================================
# PAYROLL PERIOD
# ============================================================

class LoanApplication(models.Model):

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted"),
        ("UNDER_REVIEW", "Under Review"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("CANCELLED", "Cancelled"),
        ("DISBURSED", "Disbursed"),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="loan_applications",
    )

    application_number = models.CharField(
        max_length=40,
        unique=True,
        blank=True,
    )

    loan_name = models.CharField(
        max_length=150,
    )

    requested_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    approved_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
    )

    requested_installment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
    )

    approved_installment = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
    )

    repayment_months = models.PositiveIntegerField(
        blank=True,
        null=True,
    )

    purpose = models.TextField()

    supporting_document = models.FileField(
        upload_to="hr/loan_applications/",
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
    )

    staff_notes = models.TextField(
        blank=True,
        null=True,
    )

    admin_notes = models.TextField(
        blank=True,
        null=True,
    )

    reviewed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_loan_applications",
    )

    reviewed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    approved_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    rejected_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    submitted_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    disbursed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    staff_loan = models.OneToOneField(
        "StaffLoan",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="application",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.application_number:
            year = timezone.localdate().year

            last = (
                LoanApplication.objects
                .filter(
                    application_number__startswith=f"LA-{year}-"
                )
                .order_by("-id")
                .first()
            )

            sequence = 1

            if last and last.application_number:
                try:
                    sequence = (
                        int(last.application_number.rsplit("-", 1)[-1])
                        + 1
                    )
                except (ValueError, TypeError):
                    sequence = 1

            self.application_number = (
                f"LA-{year}-{sequence:05d}"
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.application_number} - "
            f"{self.employee.full_name}"
        )

class PayrollPeriod(models.Model):

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PROCESSING", "Processing"),
        ("APPROVED", "Approved"),
        ("PAID", "Paid"),
        ("CLOSED", "Closed"),
    ]

    name = models.CharField(
        max_length=100,
    )

    year = models.PositiveIntegerField()

    month = models.PositiveIntegerField()

    start_date = models.DateField()

    end_date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
    )

    processed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-year", "-month"]

        constraints = [
            models.UniqueConstraint(
                fields=["year", "month"],
                name="unique_payroll_period",
            )
        ]

    def clean(self):

        if not 1 <= self.month <= 12:
            raise ValidationError(
                "Month must be between 1 and 12."
            )

        if (
            self.start_date
            and self.end_date
            and self.end_date < self.start_date
        ):
            raise ValidationError(
                "Payroll end date cannot be before start date."
            )

    def __str__(self):
        return self.name


# ============================================================
# PAYROLL RECORD
# ============================================================

class PayrollRecord(models.Model):

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="payroll_records",
    )

    payroll_period = models.ForeignKey(
        PayrollPeriod,
        on_delete=models.CASCADE,
        related_name="payroll_records",
    )

    basic_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    total_allowances = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    gross_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    total_deductions = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    taxable_income = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    paye = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    nssf = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    sha = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    housing_levy = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    loan_deductions = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    other_deductions = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    net_salary = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = [
            "employee__first_name",
            "employee__last_name",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "employee",
                    "payroll_period",
                ],
                name="unique_employee_payroll_period",
            )
        ]

    def __str__(self):
        return (
            f"{self.employee.full_name} - "
            f"{self.payroll_period.name}"
        )


# ============================================================
# PAYSLIP
# ============================================================

class Payslip(models.Model):

    payroll_record = models.OneToOneField(
        PayrollRecord,
        on_delete=models.CASCADE,
        related_name="payslip",
    )

    payslip_number = models.CharField(
        max_length=100,
        unique=True,
    )

    generated_at = models.DateTimeField(
        auto_now_add=True,
    )

    is_sent = models.BooleanField(
        default=False,
    )

    sent_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return self.payslip_number


# ============================================================
# PERFORMANCE APPRAISAL
# ============================================================

class PerformanceAppraisal(models.Model):

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SUBMITTED", "Submitted"),
        ("REVIEWED", "Reviewed"),
        ("COMPLETED", "Completed"),
    ]

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="appraisals",
    )

    appraisal_date = models.DateField(
        default=timezone.localdate,
    )

    period = models.CharField(
        max_length=100,
    )

    rating = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    strengths = models.TextField(
        blank=True,
        null=True,
    )

    areas_for_improvement = models.TextField(
        blank=True,
        null=True,
    )

    comments = models.TextField(
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="DRAFT",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-appraisal_date"]

    def __str__(self):
        return (
            f"{self.employee.full_name} - "
            f"{self.period}"
        )


# ============================================================
# EMPLOYEE EXIT
# ============================================================

class EmployeeExit(models.Model):

    EXIT_TYPE_CHOICES = [
        ("RESIGNATION", "Resignation"),
        ("TERMINATION", "Termination"),
        ("RETIREMENT", "Retirement"),
        ("CONTRACT_END", "Contract End"),
        ("OTHER", "Other"),
    ]

    employee = models.OneToOneField(
        Employee,
        on_delete=models.CASCADE,
        related_name="exit_record",
    )

    exit_type = models.CharField(
        max_length=30,
        choices=EXIT_TYPE_CHOICES,
    )

    exit_date = models.DateField()

    reason = models.TextField(
        blank=True,
        null=True,
    )

    clearance_completed = models.BooleanField(
        default=False,
    )

    final_payment_completed = models.BooleanField(
        default=False,
    )

    notes = models.TextField(
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return (
            f"{self.employee.full_name} - "
            f"{self.exit_type}"
        )


