from django.db import models
from django.contrib.auth.models import User, Permission
from students.models import Student


# ============================================================
# DEPARTMENT
# ============================================================

class Department(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    description = models.TextField(
        blank=True,
        default=""
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# ============================================================
# ROLE
# ============================================================

class Role(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    description = models.TextField(
        blank=True,
        default=""
    )

    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="erp_roles"
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


# ============================================================
# USER PROFILE
# ============================================================

class UserProfile(models.Model):

    ROLE_CHOICES = [
        ("ADMIN", "Admin"),
        ("STAFF", "Staff"),
        ("STUDENT", "Student"),
        ("PARENT", "Parent"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    # --------------------------------------------------------
    # ACCOUNT ROLE
    # --------------------------------------------------------

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="STAFF"
    )

    # --------------------------------------------------------
    # ERP CUSTOM ROLE
    # --------------------------------------------------------

    custom_role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_members"
    )

    # --------------------------------------------------------
    # STUDENT ACCOUNT LINK
    # --------------------------------------------------------

    student = models.OneToOneField(
        Student,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_account"
    )

    # --------------------------------------------------------
    # HR EMPLOYEE LINK
    # --------------------------------------------------------

    employee = models.OneToOneField(
        "hr_payroll.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profile",
    )

    # --------------------------------------------------------
    # STAFF INFORMATION
    # --------------------------------------------------------

    phone = models.CharField(
        max_length=20,
        blank=True,
        default=""
    )

    employee_number = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True
    )

    job_title = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_members"
    )

    # --------------------------------------------------------
    # TIMEZONE / LOCAL DATE & TIME
    # --------------------------------------------------------

    timezone = models.CharField(
        max_length=64,
        default="Africa/Nairobi",
        blank=True,
        help_text="User's preferred IANA timezone, e.g. Africa/Nairobi or Europe/London.",
    )

    # --------------------------------------------------------
    # ACCOUNT STATUS
    # --------------------------------------------------------

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    # --------------------------------------------------------
    # DISPLAY NAME
    # --------------------------------------------------------

    def __str__(self):

        if self.custom_role:
            return (
                f"{self.user.username} - "
                f"{self.custom_role.name}"
            )

        return (
            f"{self.user.username} - "
            f"{self.role}"
        )

# ============================================================
# SCHOOL BRANDING
# ============================================================

class SchoolBranding(models.Model):

    school_name = models.CharField(
        max_length=200,
        default="Luhan School"
    )

    motto = models.CharField(
        max_length=300,
        blank=True,
        default=""
    )

    logo = models.ImageField(
        upload_to="school_branding/",
        blank=True,
        null=True
    )

    phone = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )

    alternative_phone = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )

    email = models.EmailField(
        blank=True,
        default=""
    )

    website = models.CharField(
        max_length=200,
        blank=True,
        default=""
    )

    physical_address = models.CharField(
        max_length=300,
        blank=True,
        default=""
    )

    postal_address = models.CharField(
        max_length=300,
        blank=True,
        default=""
    )

    school_code = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )

    additional_information = models.TextField(
        blank=True,
        default=""
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = "School Branding"
        verbose_name_plural = "School Branding"
        permissions = [
            ("access_staff_academic_portal", "Academics (full access to the staff academic portal)"),
        ]

    def __str__(self):
        return self.school_name