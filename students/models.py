import random

from django.db import models


class Student(models.Model):

    GENDER_CHOICES = [
        ("Male", "Male"),
        ("Female", "Female"),
    ]

    admission_no = models.CharField(
        max_length=20,
        unique=True,
        blank=True
    )

    first_name = models.CharField(
        max_length=100
    )

    middle_name = models.CharField(
        max_length=100,
        blank=True
    )

    last_name = models.CharField(
        max_length=100
    )

    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES
    )

    date_of_birth = models.DateField()

    class_name = models.CharField(
        max_length=30
    )

    stream = models.CharField(
        max_length=20
    )

    parent_name = models.CharField(
        max_length=150
    )

    parent_phone = models.CharField(
        max_length=20
    )

    photo = models.ImageField(
        upload_to="students/",
        blank=True,
        null=True
    )

    # Active students remain visible in normal student lists.
    # Deactivation keeps the learner and all linked records safely
    # in the database without permanently deleting them.
    is_active = models.BooleanField(
        default=True
    )

    date_admitted = models.DateField(
        auto_now_add=True
    )

    # ========================================================
    # FULL NAME
    # ========================================================

    def get_full_name(self):

        return " ".join(
            part
            for part in [
                self.first_name,
                self.middle_name,
                self.last_name
            ]
            if part
        )

    # ========================================================
    # SAVE
    # ========================================================

    def save(self, *args, **kwargs):

        if not self.admission_no:
            from number_formats.services import (
                generate_student_admission_number
            )

            self.admission_no = (
                generate_student_admission_number()
            )

        super().save(*args, **kwargs)

    # ========================================================
    # DISPLAY
    # ========================================================

    def __str__(self):

        return (
            f"{self.admission_no} - "
            f"{self.get_full_name()}"
        )

# ============================================================
# ONLINE ADMISSION APPLICATIONS
# ============================================================

    transport_required = models.BooleanField(
        default=False,
        help_text="Whether this learner requires school transport.",
    )
class OnlineApplication(models.Model):

    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Admitted", "Admitted"),
        ("Rejected", "Rejected"),
    ]

    GENDER_CHOICES = [
        ("Male", "Male"),
        ("Female", "Female"),
    ]

    application_no = models.CharField(
        max_length=30,
        unique=True,
        blank=True
    )

    status_reference = models.CharField(
        max_length=30,
        unique=True,
        blank=True
    )

    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)

    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES
    )

    date_of_birth = models.DateField()

    requested_class = models.CharField(max_length=30)
    requested_stream = models.CharField(
        max_length=20,
        blank=True
    )

    transport_required = models.BooleanField(
        default=False,
        help_text="Whether transport is required.",
    )
    transport_route = models.ForeignKey(
        "transport.Route", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="online_transport_applications",
    )
    transport_from_stop = models.ForeignKey(
        "transport.RouteStop", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="online_transport_from_applications",
    )
    transport_to_stop = models.ForeignKey(
        "transport.RouteStop", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="online_transport_to_applications",
    )

    parent_name = models.CharField(max_length=150)
    parent_phone = models.CharField(max_length=20)
    parent_email = models.EmailField(blank=True)

    previous_school = models.CharField(
        max_length=200,
        blank=True
    )

    address = models.TextField(blank=True)

    application_date = models.DateTimeField(
        auto_now_add=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Pending"
    )

    admitted_student = models.ForeignKey(
        "Student",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="online_application"
    )

    processed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    rejection_reason = models.TextField(
        blank=True
    )

    def save(self, *args, **kwargs):

        if not self.application_no:

            last_application = (
                OnlineApplication.objects
                .order_by("-id")
                .first()
            )

            if last_application and last_application.application_no:

                try:
                    last_number = int(
                        last_application.application_no
                        .replace("APP", "")
                    )
                    new_number = last_number + 1

                except ValueError:
                    new_number = (
                        last_application.id + 1
                    )

            else:
                new_number = 1

            self.application_no = (
                f"APP{new_number:04d}"
            )

        if not self.status_reference:
            while True:
                reference = f"ADM-{random.randint(100000, 999999)}"

                if not OnlineApplication.objects.filter(
                    status_reference=reference
                ).exists():
                    self.status_reference = reference
                    break

        super().save(*args, **kwargs)

    def get_full_name(self):

        return " ".join(
            part
            for part in [
                self.first_name,
                self.middle_name,
                self.last_name
            ]
            if part
        )

    def __str__(self):

        return (
            f"{self.application_no} - "
            f"{self.get_full_name()}"
        )


# ============================================================
# STUDENT PROMOTION HISTORY
# ============================================================

class StudentPromotionHistory(models.Model):

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="promotion_history"
    )

    academic_year = models.ForeignKey(
        "fees.AcademicYear",
        on_delete=models.PROTECT,
        related_name="student_promotions"
    )

    previous_class = models.CharField(
        max_length=100
    )

    previous_stream = models.CharField(
        max_length=100,
        blank=True
    )

    promoted_class = models.CharField(
        max_length=100
    )

    promoted_stream = models.CharField(
        max_length=100,
        blank=True
    )

    promoted_at = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        ordering = ["-promoted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "academic_year"],
                name="unique_student_promotion_year"
            )
        ]

    def __str__(self):
        return (
            f"{self.student.admission_no} - "
            f"{self.previous_class} to "
            f"{self.promoted_class} - "
            f"{self.academic_year.year}"
        )
