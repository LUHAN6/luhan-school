from django import forms
from students.models import Student
from .models import (DisciplineCase, DisciplineIncidentReport, DisciplineStatement,
    DisciplineMeeting, DisciplineDecision, DisciplineAction, DisciplineImprovementPlan,
    DisciplineAppeal, DisciplineCategory)

class StyledForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs.setdefault("rows", 4)

class CaseReportForm(StyledForm):
    attachments = forms.FileField(
        required=False,
        label="Evidence attachment",
        help_text="Optional. PDF, JPG, PNG, DOC or DOCX; maximum 10 MB.",
    )
    class Meta:
        model = DisciplineCase
        fields = ["student","student_name","category","incident_date","incident_time","location","description","immediate_action","urgent"]
        widgets = {"description": forms.Textarea(attrs={"rows":5}), "immediate_action": forms.Textarea(attrs={"rows":3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = Student.objects.filter(is_active=True).order_by("first_name", "last_name")
        self.fields["student"].required = False
        self.fields["student_name"].required = False
        self.fields["student_name"].label = "Student name (if not in ERP)"
        self.fields["student_name"].help_text = "Used only when the learner is not available in the student register."
        self.fields["student"].help_text = "Select an existing ERP student to link this case. Leave blank only for incidents not involving a registered student."

    def clean_attachments(self):
        uploaded = self.cleaned_data.get("attachments")
        if not uploaded:
            return uploaded
        if uploaded.size > 10 * 1024 * 1024:
            raise forms.ValidationError("Evidence files must be 10 MB or smaller.")
        allowed = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"}
        suffix = __import__("os").path.splitext(uploaded.name)[1].lower()
        if suffix not in allowed:
            raise forms.ValidationError("Allowed evidence formats: PDF, JPG, PNG, DOC and DOCX.")
        return uploaded

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("student") and not (cleaned.get("student_name") or "").strip():
            self.add_error("student_name", "Select an ERP student or enter the student's name.")
        return cleaned

class IncidentReportForm(StyledForm):
    class Meta:
        model = DisciplineIncidentReport
        fields = ["factual_account","immediate_safety_concern","attachments"]

class StatementForm(StyledForm):
    class Meta:
        model = DisciplineStatement
        fields = ["author_name","statement_type","body","confidential"]

class MeetingForm(StyledForm):
    class Meta:
        model = DisciplineMeeting
        fields = ["title","scheduled_at","venue","attendees"]

class DecisionForm(StyledForm):
    class Meta:
        model = DisciplineDecision
        fields = ["outcome","reasons","communicated_to_parent","communicated_to_student"]

class ActionForm(StyledForm):
    class Meta:
        model = DisciplineAction
        fields = ["title","details","assigned_to","due_date","status"]

class ImprovementPlanForm(StyledForm):
    class Meta:
        model = DisciplineImprovementPlan
        fields = ["title","goals","support_measures","start_date","review_date","progress_notes","completed"]

class AppealForm(StyledForm):
    class Meta:
        model = DisciplineAppeal
        # Requester identity and role are assigned by the view from the
        # authenticated account and verified ERP parent-child relationship.
        fields = ["grounds"]


class AppealReviewForm(StyledForm):
    class Meta:
        model = DisciplineAppeal
        fields = ["status", "review_outcome"]
        widgets = {"review_outcome": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [
            ("reviewing", "Reviewing"),
            ("upheld", "Decision upheld"),
            ("varied", "Decision varied"),
            ("reversed", "Decision reversed"),
        ]
        self.fields["review_outcome"].required = False

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        outcome = (cleaned.get("review_outcome") or "").strip()
        if status in {"upheld", "varied", "reversed"} and not outcome:
            self.add_error("review_outcome", "Record the reason for the appeal outcome.")
        return cleaned
