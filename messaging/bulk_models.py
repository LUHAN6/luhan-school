import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone

class ContactGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

class Contact(models.Model):
    class Audience(models.TextChoices):
        PARENT = "parent", "Parent / Guardian"
        STUDENT = "student", "Student"
        STAFF = "staff", "Staff"
        UNCLASSIFIED = "unclassified", "Unclassified"

    class Source(models.TextChoices):
        MANUAL = "manual", "Manual"
        CSV = "csv", "CSV Import"
        ERP = "erp", "ERP Sync"

    external_id = models.CharField(max_length=100, blank=True, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=32, blank=True, db_index=True)
    email = models.EmailField(blank=True, db_index=True)
    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.UNCLASSIFIED,
        db_index=True,
    )
    groups = models.ManyToManyField(ContactGroup, blank=True, related_name="contacts")
    sms_consent = models.BooleanField(default=False)
    email_consent = models.BooleanField(default=False)
    opted_out = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["first_name", "last_name"]
        indexes = [models.Index(fields=["is_active", "opted_out"])]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

class MessageTemplate(models.Model):
    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"

    name = models.CharField(max_length=120, unique=True)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    subject = models.CharField(max_length=200, blank=True, help_text="Email subject; optional for SMS.")
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_channel_display()})"

class Campaign(models.Model):
    class Audience(models.TextChoices):
        GROUPS = "groups", "Contact Groups (existing workflow)"
        PARENTS = "parents", "Parents"
        STUDENTS = "students", "Students"
        STAFF = "staff", "Staff"
        EVERYONE = "everyone", "All (Parents, Students and Staff)"
        INDIVIDUAL = "individual", "Individual Person"

    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"
        BOTH = "both", "SMS + Email"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        SIMULATED = "simulated", "Simulated (not sent)"
        CANCELLED = "cancelled", "Cancelled"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=160)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    subject = models.CharField(max_length=200, blank=True)
    message = models.TextField()
    audience = models.CharField(
        max_length=20,
        choices=Audience.choices,
        default=Audience.GROUPS,
        db_index=True,
    )
    individual_contact = models.ForeignKey(
        Contact,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="individual_campaigns",
    )
    groups = models.ManyToManyField(ContactGroup, blank=True, related_name="campaigns")
    all_contacts = models.BooleanField(default=False, help_text="Target every eligible active contact in the legacy group workflow.")
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_recipients = models.PositiveIntegerField(default=0)
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    @property
    def progress_percent(self):
        if not self.total_recipients:
            return 0
        processed = self.sent_count + self.failed_count + self.skipped_count
        return min(100, round(processed * 100 / self.total_recipients))

class MessageLog(models.Model):
    class Channel(models.TextChoices):
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="logs")
    contact = models.ForeignKey(Contact, null=True, blank=True, on_delete=models.SET_NULL, related_name="message_logs")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    destination = models.CharField(max_length=254)
    subject = models.CharField(max_length=200, blank=True)
    rendered_message = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    provider_message_id = models.CharField(max_length=200, blank=True)
    error_message = models.TextField(blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["campaign", "status"]), models.Index(fields=["channel", "status"])]

    def __str__(self):
        return f"{self.channel} to {self.destination}: {self.status}"
