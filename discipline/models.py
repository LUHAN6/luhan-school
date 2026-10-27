from django.conf import settings
from .storage import PrivateDisciplineEvidenceStorage
from django.db import models
from django.utils import timezone
import uuid

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

class DisciplineCategory(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    severity = models.CharField(max_length=20, choices=[("low","Low"),("moderate","Moderate"),("high","High"),("critical","Critical")], default="moderate")
    is_active = models.BooleanField(default=True)
    class Meta:
        ordering = ["name"]
        verbose_name_plural = "discipline categories"
    def __str__(self): return self.name

class DisciplinePolicy(TimeStampedModel):
    title = models.CharField(max_length=180)
    version = models.CharField(max_length=30, default="1.0")
    content = models.TextField()
    effective_from = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="discipline_policies_created")
    class Meta: ordering = ["-effective_from", "title"]
    def __str__(self): return f"{self.title} (v{self.version})"

class DisciplineCase(TimeStampedModel):
    STATUS_CHOICES = [
        ("draft","Draft"),("submitted","Submitted"),("under_review","Under Review"),
        ("investigation","Under Investigation"),("awaiting_meeting","Awaiting Meeting"),
        ("awaiting_decision","Awaiting Decision"),("awaiting_ack","Awaiting Acknowledgment"),
        ("action_in_progress","Action in Progress"),("appeal","Under Review / Appeal"),
        ("closed","Closed"),("reopened","Reopened"),
    ]
    case_number = models.CharField(max_length=24, unique=True, blank=True)
    student = models.ForeignKey("students.Student", null=True, blank=True, on_delete=models.SET_NULL, related_name="discipline_cases")
    student_name = models.CharField(max_length=180, help_text="Temporary standalone field; link to the ERP student model during integration.")
    student_admission_no = models.CharField(max_length=60, blank=True)
    class_name = models.CharField(max_length=100, blank=True)
    parent_name = models.CharField(max_length=180, blank=True)
    parent_email = models.EmailField(blank=True)
    parent_phone = models.CharField(max_length=40, blank=True)
    category = models.ForeignKey(DisciplineCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="cases")
    incident_date = models.DateField(default=timezone.localdate)
    incident_time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=180, blank=True)
    description = models.TextField()
    immediate_action = models.TextField(blank=True)
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="discipline_reports")
    assigned_officer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="discipline_assigned_cases")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="submitted")
    urgent = models.BooleanField(default=False)
    student_response = models.TextField(blank=True)
    parent_response = models.TextField(blank=True)
    findings = models.TextField(blank=True)
    decision_reason = models.TextField(blank=True)
    decision_maker = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="discipline_decisions")
    decision_date = models.DateField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closure_note = models.TextField(blank=True)
    class Meta: ordering = ["-created_at"]
    def save(self, *args, **kwargs):
        if self.student_id:
            student = self.student
            self.student_name = student.get_full_name()
            self.student_admission_no = student.admission_no or ""
            self.class_name = " ".join(part for part in [student.class_name, student.stream] if part)
            self.parent_name = student.parent_name or self.parent_name
            self.parent_phone = student.parent_phone or self.parent_phone
        if not self.case_number:
            self.case_number = "DISC-" + timezone.now().strftime("%Y%m") + "-" + uuid.uuid4().hex[:6].upper()
        super().save(*args, **kwargs)
    def __str__(self): return self.case_number

class DisciplineInvolvedParty(TimeStampedModel):
    ROLE_CHOICES = [("student","Student"),("witness","Witness"),("staff","Staff"),("other","Other")]
    case = models.ForeignKey(DisciplineCase, on_delete=models.CASCADE, related_name="parties")
    name = models.CharField(max_length=180)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    notes = models.TextField(blank=True)
    confidential = models.BooleanField(default=False)
    def __str__(self): return f"{self.name} — {self.get_role_display()}"

class DisciplineIncidentReport(TimeStampedModel):
    case = models.ForeignKey(DisciplineCase, on_delete=models.CASCADE, related_name="reports")
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    factual_account = models.TextField()
    immediate_safety_concern = models.BooleanField(default=False)
    attachments = models.FileField(upload_to="discipline/evidence/%Y/%m/", blank=True, storage=PrivateDisciplineEvidenceStorage())
    def __str__(self): return f"Report for {self.case.case_number}"

class DisciplineStatement(TimeStampedModel):
    case = models.ForeignKey(DisciplineCase, on_delete=models.CASCADE, related_name="statements")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    author_name = models.CharField(max_length=180, blank=True)
    statement_type = models.CharField(max_length=30, choices=[("student","Student response"),("witness","Witness statement"),("staff","Staff statement"),("parent","Parent response")])
    body = models.TextField()
    confidential = models.BooleanField(default=False)
    def __str__(self): return f"{self.get_statement_type_display()} — {self.case.case_number}"

class DisciplineMeeting(TimeStampedModel):
    case = models.ForeignKey(DisciplineCase, on_delete=models.CASCADE, related_name="meetings")
    title = models.CharField(max_length=180, default="Disciplinary meeting")
    scheduled_at = models.DateTimeField()
    venue = models.CharField(max_length=180, blank=True)
    attendees = models.TextField(blank=True)
    outcome = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    def __str__(self): return f"{self.title} — {self.case.case_number}"

class DisciplineDecision(TimeStampedModel):
    case = models.ForeignKey(DisciplineCase, on_delete=models.CASCADE, related_name="decisions")
    outcome = models.CharField(max_length=40, choices=[("no_action","No further action"),("warning","Warning"),("counselling","Counselling"),("improvement_plan","Behaviour improvement plan"),("restorative","Restorative action"),("other","Other authorized action")])
    reasons = models.TextField()
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    approved_at = models.DateTimeField(default=timezone.now)
    communicated_to_parent = models.BooleanField(default=False)
    communicated_to_student = models.BooleanField(default=False)
    def __str__(self): return f"{self.case.case_number}: {self.get_outcome_display()}"

class DisciplineAction(TimeStampedModel):
    STATUS_CHOICES = [("pending","Pending"),("in_progress","In progress"),("completed","Completed"),("cancelled","Cancelled")]
    case = models.ForeignKey(DisciplineCase, on_delete=models.CASCADE, related_name="actions")
    title = models.CharField(max_length=180)
    details = models.TextField(blank=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    completion_note = models.TextField(blank=True)
    def __str__(self): return f"{self.title} — {self.case.case_number}"

class DisciplineImprovementPlan(TimeStampedModel):
    case = models.ForeignKey(DisciplineCase, on_delete=models.CASCADE, related_name="improvement_plans")
    title = models.CharField(max_length=180, default="Behaviour improvement plan")
    goals = models.TextField()
    support_measures = models.TextField(blank=True)
    start_date = models.DateField(default=timezone.localdate)
    review_date = models.DateField(null=True, blank=True)
    progress_notes = models.TextField(blank=True)
    completed = models.BooleanField(default=False)
    def __str__(self): return f"{self.title} — {self.case.case_number}"

class DisciplineCommunication(TimeStampedModel):
    CHANNEL_CHOICES = [("portal","Portal"),("email","Email"),("sms","SMS"),("letter","Letter"),("meeting","Meeting")]
    case = models.ForeignKey(DisciplineCase, on_delete=models.CASCADE, related_name="communications")
    recipient_name = models.CharField(max_length=180)
    recipient_role = models.CharField(max_length=20, choices=[("parent","Parent/Guardian"),("student","Student"),("staff","Staff")])
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default="portal")
    subject = models.CharField(max_length=180)
    message = models.TextField()
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    def __str__(self): return f"{self.subject} — {self.case.case_number}"

class DisciplineAppeal(TimeStampedModel):
    case = models.ForeignKey(DisciplineCase, on_delete=models.CASCADE, related_name="appeals")
    requested_by_name = models.CharField(max_length=180)
    requester_role = models.CharField(max_length=20, choices=[("parent","Parent/Guardian"),("student","Student"),("staff","Staff")])
    grounds = models.TextField()
    status = models.CharField(max_length=20, choices=[("submitted","Submitted"),("reviewing","Reviewing"),("upheld","Decision upheld"),("varied","Decision varied"),("reversed","Decision reversed")], default="submitted")
    review_outcome = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="discipline_appeals_reviewed")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    def __str__(self): return f"Appeal — {self.case.case_number}"

class DisciplineAuditLog(models.Model):
    case = models.ForeignKey(DisciplineCase, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta: ordering = ["-created_at"]
    def __str__(self): return f"{self.action} ({self.created_at:%Y-%m-%d %H:%M})"
