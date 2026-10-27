from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True


class Vehicle(TimeStampedModel):
    STATUS = [("AVAILABLE","Available"),("ASSIGNED","Assigned"),("MAINTENANCE","Under maintenance"),("OUT_OF_SERVICE","Out of service")]
    registration_number = models.CharField(max_length=24, unique=True)
    make_model = models.CharField(max_length=100, blank=True)
    year_of_manufacture = models.PositiveSmallIntegerField(null=True, blank=True)
    seating_capacity = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    odometer_km = models.PositiveIntegerField(default=0)
    fuel_type = models.CharField(max_length=30, blank=True)
    insurance_expiry = models.DateField(null=True, blank=True)
    inspection_expiry = models.DateField(null=True, blank=True)
    road_licence_expiry = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="AVAILABLE")
    notes = models.TextField(blank=True)
    def __str__(self): return f"{self.registration_number} ({self.seating_capacity} seats)"
    @property
    def documents_expired(self):
        today = timezone.localdate()
        return any(d and d < today for d in [self.insurance_expiry, self.inspection_expiry, self.road_licence_expiry])


class TransportStaff(TimeStampedModel):
    ROLE = [("DRIVER","Driver"),("ATTENDANT","Attendant"),("OTHER","Other")]
    employee = models.ForeignKey(
        "hr_payroll.Employee",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transport_staff_records",
    )
    full_name = models.CharField(max_length=160)
    role = models.CharField(max_length=12, choices=ROLE)
    phone = models.CharField(max_length=30, blank=True)
    emergency_contact = models.CharField(max_length=160, blank=True)
    licence_number = models.CharField(max_length=80, blank=True)
    licence_class = models.CharField(max_length=40, blank=True)
    licence_expiry = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    def __str__(self): return f"{self.full_name} â€” {self.get_role_display()}"


class TransportRoute(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=24, unique=True)
    area = models.CharField(max_length=160, blank=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    def __str__(self): return f"{self.code} â€” {self.name}"


class RouteStop(TimeStampedModel):
    route = models.ForeignKey(TransportRoute, on_delete=models.CASCADE, related_name="stops")
    name = models.CharField(max_length=160)
    address_or_landmark = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    sequence = models.PositiveSmallIntegerField(default=1)
    morning_pickup_time = models.TimeField(null=True, blank=True)
    afternoon_dropoff_time = models.TimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    class Meta:
        ordering = ["route", "sequence"]
        unique_together = [("route", "sequence")]
    def __str__(self): return f"{self.route.code} / {self.sequence}. {self.name}"


class LearnerTransport(TimeStampedModel):
    DIRECTION = [("BOTH","Morning and afternoon"),("AM","Morning only"),("PM","Afternoon only")]
    STATUS = [("PENDING","Pending approval"),("ACTIVE","Active"),("SUSPENDED","Suspended"),("ENDED","Ended")]
    learner_admission_no = models.CharField(max_length=50, db_index=True)
    learner_name = models.CharField(max_length=180)
    class_name = models.CharField(max_length=50, blank=True)
    parent_name = models.CharField(max_length=160, blank=True)
    parent_phone = models.CharField(max_length=30, blank=True)
    emergency_phone = models.CharField(max_length=30, blank=True)
    route = models.ForeignKey(TransportRoute, on_delete=models.PROTECT, related_name="assignments")
    stop = models.ForeignKey(RouteStop, on_delete=models.PROTECT, related_name="assignments")
    # New separate journeys. The legacy route/stop fields remain populated
    # so existing reports and older assignments continue to work.
    pickup_stop = models.ForeignKey(
        RouteStop, on_delete=models.PROTECT, null=True, blank=True,
        related_name="learner_pickup_assignments",
    )
    dropoff_stop = models.ForeignKey(
        RouteStop, on_delete=models.PROTECT, null=True, blank=True,
        related_name="learner_dropoff_assignments",
    )
    pickup_time = models.TimeField(null=True, blank=True)
    dropoff_time = models.TimeField(null=True, blank=True)
    direction = models.CharField(max_length=8, choices=DIRECTION, default="BOTH")
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    authorised_collectors = models.TextField(blank=True, help_text="Names and verification notes; restrict access to authorised staff.")
    special_instructions = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="PENDING")
    def __str__(self): return f"{self.learner_name} ({self.learner_admission_no})"
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.stop_id and self.route_id and self.stop.route_id != self.route_id:
            raise ValidationError({"stop": "The selected stop must belong to the selected route."})


class TransportTrip(TimeStampedModel):
    DIRECTION = [("AM","Morning to school"),("PM","Afternoon return")]
    STATUS = [("PLANNED","Planned"),("AUTHORISED","Authorised"),("IN_PROGRESS","In progress"),("COMPLETED","Completed"),("CANCELLED","Cancelled"),("INCIDENT","Incident review")]
    route = models.ForeignKey(TransportRoute, on_delete=models.PROTECT, related_name="trips")
    service_date = models.DateField(default=timezone.localdate, db_index=True)
    direction = models.CharField(max_length=2, choices=DIRECTION)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="trips")
    driver = models.ForeignKey(TransportStaff, on_delete=models.PROTECT, related_name="driven_trips")
    attendant = models.ForeignKey(TransportStaff, on_delete=models.PROTECT, related_name="attended_trips", null=True, blank=True)
    planned_departure = models.DateTimeField(null=True, blank=True)
    actual_departure = models.DateTimeField(null=True, blank=True)
    actual_arrival = models.DateTimeField(null=True, blank=True)
    start_odometer_km = models.PositiveIntegerField(null=True, blank=True)
    end_odometer_km = models.PositiveIntegerField(null=True, blank=True)
    fuel_litres = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS, default="PLANNED")
    authorised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="authorised_transport_trips")
    closing_notes = models.TextField(blank=True)
    class Meta:
        ordering = ["-service_date", "planned_departure"]
    def __str__(self): return f"{self.route.code} {self.get_direction_display()} {self.service_date}"
    @property
    def distance_km(self):
        if self.start_odometer_km is not None and self.end_odometer_km is not None:
            return max(0, self.end_odometer_km - self.start_odometer_km)
        return None
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.pk and self.vehicle_id and self.vehicle.seating_capacity < self.boarding_events.filter(status="BOARDED").count():
            raise ValidationError("Recorded boarded learners exceed vehicle seating capacity.")
        if self.driver_id and self.driver.role != "DRIVER":
            raise ValidationError({"driver": "The assigned staff member must have the Driver role."})
        if self.attendant_id and self.attendant.role != "ATTENDANT":
            raise ValidationError({"attendant": "The assigned staff member must have the Attendant role."})


class VehicleInspection(TimeStampedModel):
    RESULT = [("PASS", "Pass"), ("MINOR", "Minor defect"), ("FAIL", "Fail - do not dispatch")]
    trip = models.OneToOneField(TransportTrip, on_delete=models.CASCADE, related_name="inspection")
    inspected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    result = models.CharField(max_length=8, choices=RESULT)
    brakes_ok = models.BooleanField(default=False)
    tyres_ok = models.BooleanField(default=False)
    lights_ok = models.BooleanField(default=False)
    seatbelts_ok = models.BooleanField(default=False)
    doors_ok = models.BooleanField(default=False)
    first_aid_ok = models.BooleanField(default=False)
    extinguisher_ok = models.BooleanField(default=False)
    defects = models.TextField(blank=True)
    inspected_at = models.DateTimeField(default=timezone.now)
    @property
    def dispatch_allowed(self):
        return self.result == "PASS" and all([self.brakes_ok, self.tyres_ok, self.lights_ok, self.seatbelts_ok, self.doors_ok, self.first_aid_ok, self.extinguisher_ok])


class BoardingEvent(TimeStampedModel):
    STATUS = [("BOARDED","Boarded"),("ABSENT","Absent at stop"),("NOT_EXPECTED","Not expected"),("DROPPED_OFF","Dropped off"),("HANDED_OVER","Handed over to authorised collector"),("EXCEPTION","Exception / not confirmed")]
    trip = models.ForeignKey(TransportTrip, on_delete=models.CASCADE, related_name="boarding_events")
    learner = models.ForeignKey(LearnerTransport, on_delete=models.PROTECT, related_name="boarding_events")
    stop = models.ForeignKey(RouteStop, on_delete=models.PROTECT)
    status = models.CharField(max_length=16, choices=STATUS)
    event_time = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    handover_to = models.CharField(max_length=160, blank=True)
    verification_note = models.CharField(max_length=255, blank=True)
    class Meta:
        ordering = ["event_time"]
        constraints = [models.UniqueConstraint(fields=["trip", "learner", "status"], name="unique_trip_learner_event_status")]
    def clean(self):
        from django.core.exceptions import ValidationError
        if self.learner_id and self.trip_id and self.learner.route_id != self.trip.route_id:
            raise ValidationError("Learner is not assigned to this trip's route.")
        if self.stop_id and self.trip_id and self.stop.route_id != self.trip.route_id:
            raise ValidationError("Stop is not part of this trip's route.")


class MaintenanceRecord(TimeStampedModel):
    STATUS = [("OPEN","Open"),("IN_PROGRESS","In progress"),("COMPLETED","Completed")]
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="maintenance_records")
    reported_date = models.DateField(default=timezone.localdate)
    due_odometer_km = models.PositiveIntegerField(null=True, blank=True)
    category = models.CharField(max_length=80)
    description = models.TextField()
    service_provider = models.CharField(max_length=160, blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=15, choices=STATUS, default="OPEN")
    completed_date = models.DateField(null=True, blank=True)


class TransportIncident(TimeStampedModel):
    SEVERITY = [("LOW","Low"),("MEDIUM","Medium"),("HIGH","High"),("CRITICAL","Critical")]
    STATUS = [("OPEN","Open"),("INVESTIGATING","Investigating"),("RESOLVED","Resolved")]
    trip = models.ForeignKey(TransportTrip, on_delete=models.PROTECT, related_name="incidents", null=True, blank=True)
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, null=True, blank=True)
    learner_admission_no = models.CharField(max_length=50, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    severity = models.CharField(max_length=10, choices=SEVERITY, default="LOW")
    description = models.TextField()
    action_taken = models.TextField(blank=True)
    parent_notified = models.BooleanField(default=False)
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=15, choices=STATUS, default="OPEN")


class TransportCharge(TimeStampedModel):
    STATUS = [("DUE","Due"),("PARTIAL","Partially paid"),("PAID","Paid"),("WAIVED","Waived")]
    learner = models.ForeignKey(LearnerTransport, on_delete=models.PROTECT, related_name="charges")
    period_label = models.CharField(max_length=80, help_text="e.g. Term 1 2027 or October 2026")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="DUE")
    external_fee_reference = models.CharField(max_length=100, blank=True, help_text="Optional reference to the ERP fee ledger.")
    notes = models.TextField(blank=True)


class TransportPayment(TimeStampedModel):
    charge = models.ForeignKey(TransportCharge, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    payment_date = models.DateTimeField(default=timezone.now)
    method = models.CharField(max_length=30, default="MPESA")
    transaction_reference = models.CharField(max_length=100, unique=True)
    verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)


class TransportNotificationLog(TimeStampedModel):
    CHANNEL = [("IN_APP","In-app"),("SMS","SMS"),("WHATSAPP","WhatsApp"),("EMAIL","Email")]
    STATUS = [("QUEUED","Queued"),("SENT","Sent"),("FAILED","Failed")]
    recipient = models.CharField(max_length=160)
    channel = models.CharField(max_length=10, choices=CHANNEL)
    message = models.TextField()
    status = models.CharField(max_length=8, choices=STATUS, default="QUEUED")
    provider_reference = models.CharField(max_length=160, blank=True)
    error_detail = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)


class TransportAuditEvent(TimeStampedModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=64, blank=True)
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    class Meta:
        ordering = ["-created_at"]

