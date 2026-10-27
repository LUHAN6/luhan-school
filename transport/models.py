from django.db import models
from django.utils import timezone

from students.models import Student


# =========================================================
# VEHICLES / SCHOOL BUSES
# =========================================================

class Vehicle(models.Model):

    VEHICLE_TYPES = [
        ("BUS", "School Bus"),
        ("VAN", "Van"),
        ("MINIBUS", "Minibus"),
        ("CAR", "School Car"),
        ("OTHER", "Other"),
    ]

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
        ("MAINTENANCE", "Under Maintenance"),
    ]

    registration_number = models.CharField(
        max_length=30,
        unique=True,
    )

    vehicle_name = models.CharField(
        max_length=100,
        blank=True,
    )

    vehicle_type = models.CharField(
        max_length=20,
        choices=VEHICLE_TYPES,
        default="BUS",
    )

    make = models.CharField(
        max_length=100,
        blank=True,
    )

    model = models.CharField(
        max_length=100,
        blank=True,
    )

    year = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    capacity = models.PositiveIntegerField(
        default=0,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE",
    )

    insurance_expiry = models.DateField(
        null=True,
        blank=True,
    )

    inspection_expiry = models.DateField(
        null=True,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["registration_number"]

    def __str__(self):
        if self.vehicle_name:
            return f"{self.registration_number} - {self.vehicle_name}"

        return self.registration_number


# =========================================================
# DRIVERS
# =========================================================

class Driver(models.Model):

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
    ]

    # The driver is an existing HR Payroll employee.
    # No employee identity information is duplicated in Transport.
    employee = models.OneToOneField(
        "hr_payroll.Employee",
        on_delete=models.PROTECT,
        related_name="transport_driver",
        null=True,
        blank=True,
    )

    # Transport-specific information.
    licence_number = models.CharField(
        max_length=50,
        unique=True,
    )

    licence_expiry = models.DateField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE",
    )

    address = models.CharField(
        max_length=255,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["employee"]

    def __str__(self):
        return str(self.employee)

    @property
    def first_name(self):
        return getattr(self.employee, "first_name", "")

    @property
    def last_name(self):
        return getattr(self.employee, "last_name", "")

    @property
    def phone(self):
        return (
            getattr(self.employee, "phone", None)
            or getattr(self.employee, "phone_number", None)
            or ""
        )

    @property
    def national_id(self):
        return (
            getattr(self.employee, "national_id", None)
            or getattr(self.employee, "id_number", None)
            or getattr(self.employee, "national_id_number", None)
            or ""
        )

class Route(models.Model):

    google_maps_url = models.URLField(blank=True)
    map_latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    map_longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    distance_km = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    estimated_minutes = models.PositiveIntegerField(null=True, blank=True)

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
    ]

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    code = models.CharField(
        max_length=30,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    morning_departure = models.TimeField(
        null=True,
        blank=True,
    )

    afternoon_departure = models.TimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE",
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
        return f"{self.code} - {self.name}"


# =========================================================
# ROUTE STOPS
# =========================================================

class RouteStop(models.Model):

    google_maps_url = models.URLField(blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name="stops",
    )

    name = models.CharField(
        max_length=150,
    )

    location = models.CharField(
        max_length=255,
        blank=True,
    )

    stop_order = models.PositiveIntegerField(
        default=1,
    )

    pickup_time = models.TimeField(
        null=True,
        blank=True,
    )

    dropoff_time = models.TimeField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        ordering = ["route", "stop_order"]

    def __str__(self):
        return f"{self.route.name} - {self.stop_order}. {self.name}"


# =========================================================
# STUDENT TRANSPORT ASSIGNMENT
# =========================================================

class StudentTransportAssignment(models.Model):

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="transport_assignments",
    )

    route = models.ForeignKey(
        Route,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_assignments",
    )

    pickup_stop = models.ForeignKey(
        RouteStop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pickup_students",
    )

    dropoff_stop = models.ForeignKey(
        RouteStop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dropoff_students",
    )

    morning_transport = models.BooleanField(
        default=True,
    )

    afternoon_transport = models.BooleanField(
        default=True,
    )

    start_date = models.DateField(
        default=timezone.now,
    )

    end_date = models.DateField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE",
    )

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["student__first_name", "student__last_name"]

    def __str__(self):
        return f"{self.student} - {self.route or 'No Route'}"


# =========================================================
# VEHICLE / DRIVER ROUTE ASSIGNMENT
# =========================================================

class TransportAssignment(models.Model):

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("INACTIVE", "Inactive"),
    ]

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name="transport_assignments",
    )

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="route_assignments",
    )

    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="route_assignments",
    )

    start_date = models.DateField(
        default=timezone.now,
    )

    end_date = models.DateField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE",
    )

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["route__name"]

    def __str__(self):
        return f"{self.route.name} - {self.vehicle.registration_number}"


# =========================================================
# DAILY TRANSPORT TRIPS
# =========================================================

class TransportTrip(models.Model):

    TRIP_TYPES = [
        ("MORNING", "Morning Pickup"),
        ("AFTERNOON", "Afternoon Drop-off"),
        ("SPECIAL", "Special Trip"),
    ]

    STATUS_CHOICES = [
        ("SCHEDULED", "Scheduled"),
        ("IN_PROGRESS", "In Progress"),
        ("COMPLETED", "Completed"),
        ("CANCELLED", "Cancelled"),
    ]

    date = models.DateField(
        default=timezone.now,
    )

    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name="trips",
    )

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trips",
    )

    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trips",
    )

    trip_type = models.CharField(
        max_length=20,
        choices=TRIP_TYPES,
        default="MORNING",
    )

    departure_time = models.TimeField(
        null=True,
        blank=True,
    )

    arrival_time = models.TimeField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="SCHEDULED",
    )

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-date", "departure_time"]

    def __str__(self):
        return f"{self.date} - {self.route.name} - {self.get_trip_type_display()}"


# =========================================================
# VEHICLE MAINTENANCE
# =========================================================
class TransportFeeStructure(models.Model):
    academic_year = models.ForeignKey("fees.AcademicYear", on_delete=models.PROTECT, related_name="transport_fee_structures")
    term = models.ForeignKey("fees.Term", on_delete=models.PROTECT, related_name="transport_fee_structures")
    class_name = models.CharField(max_length=30, blank=True, default="")
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="transport_fee_structures")
    from_stop = models.ForeignKey(RouteStop, on_delete=models.PROTECT, related_name="transport_fee_from_structures", null=True, blank=True)
    to_stop = models.ForeignKey(RouteStop, on_delete=models.PROTECT, related_name="transport_fee_to_structures", null=True, blank=True)
    stop = models.ForeignKey(RouteStop, on_delete=models.PROTECT, related_name="transport_fee_structures", null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    billing_label = models.CharField(max_length=100, default="Transport Fee")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-academic_year__year", "term__order", "route__name", "stop__stop_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "term", "route", "stop"],
                name="unique_transport_fee_structure",
            )
        ]

    def __str__(self):
        stop = f" / {self.stop.name}" if self.stop_id else ""
        return f"{self.route.name}{stop} - {self.amount}"


class TransportFeeCharge(models.Model):
    STATUS_CHOICES = [
        ("UNPAID", "Unpaid"),
        ("PARTIAL", "Partially Paid"),
        ("PAID", "Paid"),
        ("CANCELLED", "Cancelled"),
    ]
    student_assignment = models.ForeignKey(StudentTransportAssignment, on_delete=models.PROTECT, related_name="transport_fee_charges")
    fee_structure = models.ForeignKey(TransportFeeStructure, on_delete=models.PROTECT, related_name="charges")
    fee_record = models.ForeignKey("fees.FeeRecord", on_delete=models.PROTECT, related_name="transport_fee_charges")
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="UNPAID")
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-generated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student_assignment", "fee_structure"],
                name="unique_transport_fee_charge",
            )
        ]

    @property
    def paid_amount(self):
        from django.db.models import Sum
        return self.fee_record.payments.aggregate(total=Sum("amount"))["total"] or 0

    @property
    def outstanding_amount(self):
        return max(0, self.amount - self.paid_amount)

    def refresh_status(self):
        paid = self.paid_amount
        self.status = "PAID" if paid >= self.amount and self.amount > 0 else ("PARTIAL" if paid > 0 else "UNPAID")
        self.save(update_fields=["status", "updated_at"])


class VehicleMaintenance(models.Model):

    MAINTENANCE_TYPES = [
        ("SERVICE", "Routine Service"),
        ("REPAIR", "Repair"),
        ("INSPECTION", "Inspection"),
        ("TYRES", "Tyres"),
        ("OTHER", "Other"),
    ]

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="maintenance_records",
    )

    maintenance_type = models.CharField(
        max_length=20,
        choices=MAINTENANCE_TYPES,
        default="SERVICE",
    )

    date = models.DateField(
        default=timezone.now,
    )

    description = models.TextField()

    service_provider = models.CharField(
        max_length=150,
        blank=True,
    )

    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    next_service_date = models.DateField(
        null=True,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.vehicle.registration_number} - {self.date}"


# =========================================================
# FUEL RECORDS
# =========================================================

class FuelRecord(models.Model):

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.CASCADE,
        related_name="fuel_records",
    )

    date = models.DateField(
        default=timezone.now,
    )

    litres = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    odometer_reading = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    fuel_station = models.CharField(
        max_length=150,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.vehicle.registration_number} - {self.date}"



