import csv
import io
from django import forms
from django.core.exceptions import ValidationError
from .bulk_models import Contact, ContactGroup, Campaign, MessageTemplate

class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        fields = ["first_name", "last_name", "phone", "email", "audience", "groups", "sms_consent", "email_consent", "opted_out", "is_active", "external_id", "notes"]
        widgets = {"groups": forms.CheckboxSelectMultiple(), "notes": forms.Textarea(attrs={"rows": 2})}

class ContactGroupForm(forms.ModelForm):
    class Meta:
        model = ContactGroup
        fields = ["name", "description"]

class TemplateForm(forms.ModelForm):
    class Meta:
        model = MessageTemplate
        fields = ["name", "channel", "subject", "body", "is_active"]
        widgets = {"body": forms.Textarea(attrs={"rows": 5})}

class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["name", "channel", "subject", "message", "audience", "individual_contact", "groups", "all_contacts", "scheduled_at", "notes"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 6, "placeholder": "Use {{ first_name }}, {{ full_name }}, and {{ school_name }} for personalization."}),
            "audience": forms.Select(),
            "individual_contact": forms.Select(),
            "groups": forms.CheckboxSelectMultiple(),
            "scheduled_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        initial = kwargs.get("initial") or {}
        requested_audience = initial.get("audience")
        super().__init__(*args, **kwargs)
        self.fields["scheduled_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["scheduled_at"].required = False
        self.fields["individual_contact"].queryset = Contact.objects.filter(
            is_active=True, opted_out=False
        ).order_by("first_name", "last_name")
        self.fields["individual_contact"].required = False
        self.fields["groups"].required = False
        # Older submissions omit audience; clean() defaults them to GROUPS.
        self.fields["audience"].required = False
        self.fields["audience"].initial = requested_audience or Campaign.Audience.GROUPS

    def clean(self):
        data = super().clean()
        audience = data.get("audience") or Campaign.Audience.GROUPS

        if audience == Campaign.Audience.GROUPS:
            if not data.get("all_contacts") and not data.get("groups"):
                raise ValidationError(
                    "For Contact Groups, choose at least one group or select all contacts."
                )
        elif audience == Campaign.Audience.INDIVIDUAL:
            contact = data.get("individual_contact")
            if not contact:
                self.add_error(
                    "individual_contact",
                    "Choose the one contact who should receive this campaign.",
                )
            elif not contact.is_active or contact.opted_out:
                self.add_error(
                    "individual_contact",
                    "This contact is inactive or has opted out.",
                )
        else:
            # Audience-specific campaigns use their classification, not legacy groups.
            data["all_contacts"] = False

        channel = data.get("channel")
        if channel in (Campaign.Channel.EMAIL, Campaign.Channel.BOTH) and not data.get("subject"):
            self.add_error("subject", "An email subject is required for email campaigns.")
        if data.get("scheduled_at"):
            from django.utils import timezone
            if data["scheduled_at"] <= timezone.now():
                self.add_error("scheduled_at", "Choose a future date and time.")
        return data

class CSVImportForm(forms.Form):
    file = forms.FileField(help_text="CSV columns: first_name, last_name, phone, email, groups, sms_consent, email_consent. Separate group names with semicolons.")

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        if uploaded.size > 5 * 1024 * 1024:
            raise ValidationError("File must be 5 MB or smaller.")
        if not uploaded.name.lower().endswith(".csv"):
            raise ValidationError("Upload a .csv file.")
        try:
            uploaded.read().decode("utf-8-sig")
            uploaded.seek(0)
        except UnicodeDecodeError:
            raise ValidationError("Save the CSV as UTF-8 and upload again.")
        return uploaded
