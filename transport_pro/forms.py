from django import forms
from hr_payroll.models import Employee
from .models import (
    Vehicle, TransportStaff, TransportRoute, RouteStop, LearnerTransport,
    TransportTrip, VehicleInspection, BoardingEvent, MaintenanceRecord, TransportIncident,
    TransportCharge, TransportPayment
)

class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")
            if isinstance(field.widget, forms.DateInput):
                field.widget.attrs.setdefault("type", "date")
            if isinstance(field.widget, forms.DateTimeInput):
                field.widget.attrs.setdefault("type", "datetime-local")

class VehicleForm(StyledModelForm):
    class Meta:
        model = Vehicle
        fields = "__all__"

def is_eligible_transport_employee(employee):
    """Fail closed: only active, clearly identified support staff qualify."""
    if not employee.is_active or employee.employment_status != "ACTIVE":
        return False

    position = (employee.position.title if employee.position_id else "").strip().casefold()
    department = (employee.department.name if employee.department_id else "").strip().casefold()

    excluded_positions = {
        "teacher", "senior teacher", "head of department", "head teacher",
        "deputy head teacher", "principal", "deputy principal",
    }
    if position in excluded_positions or department == "academic":
        return False

    support_positions = {
        "driver", "attendant", "caterer", "librarian", "maintenance officer",
        "security officer", "ict officer", "accountant", "accounts clerk",
        "hr officer",
    }
    support_departments = {
        "transport", "catering", "library", "maintenance", "security",
        "ict", "finance", "human resources",
    }
    return position in support_positions or department in support_departments


class TransportStaffForm(StyledModelForm):
    employee_number = forms.CharField(
        label="Employee Number",
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "placeholder": "Enter HR employee number first",
        }),
    )

    class Meta:
        model = TransportStaff
        fields = (
            "employee_number", "full_name", "role", "phone",
            "emergency_contact", "licence_number", "licence_class",
            "licence_expiry", "active", "notes",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.employee_id:
            self.fields["employee_number"].initial = self.instance.employee.employee_number

    def clean_employee_number(self):
        number = (self.cleaned_data.get("employee_number") or "").strip()
        if not number:
            if self.instance and self.instance.pk and self.instance.employee_id:
                return self.instance.employee.employee_number
            if self.instance and self.instance.pk:
                return ""
            raise forms.ValidationError("Enter an HR employee number first.")

        try:
            employee = Employee.objects.select_related("department", "position").get(
                employee_number__iexact=number
            )
        except Employee.DoesNotExist:
            raise forms.ValidationError("No HR employee was found with that employee number.")

        if not is_eligible_transport_employee(employee):
            raise forms.ValidationError(
                "This employee is inactive, teaching/leadership staff, or not clearly "
                "classified as support staff. Correct the HR employee record first."
            )

        duplicate = TransportStaff.objects.filter(employee=employee)
        if self.instance and self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError(
                "This employee is already registered as transport staff."
            )
        self._matched_employee = employee
        return employee.employee_number

    def clean(self):
        cleaned = super().clean()
        number = cleaned.get("employee_number")
        if number:
            employee = getattr(self, "_matched_employee", None)
            if employee is None and self.instance and self.instance.employee_id:
                employee = self.instance.employee
            if employee:
                # HR remains the source of truth for these identity fields.
                cleaned["full_name"] = " ".join(filter(None, [
                    employee.first_name, employee.middle_name, employee.last_name
                ]))
                cleaned["phone"] = employee.phone or ""
                cleaned["emergency_contact"] = " ".join(filter(None, [
                    employee.emergency_contact_name,
                    employee.emergency_contact_phone,
                ]))
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        number = self.cleaned_data.get("employee_number")
        employee = getattr(self, "_matched_employee", None)
        if employee is None and number:
            employee = Employee.objects.get(employee_number__iexact=number)
        if employee:
            obj.employee = employee
        if commit:
            obj.save()
            self.save_m2m()
        return obj

class TransportRouteForm(StyledModelForm):
    class Meta:
        model = TransportRoute
        fields = "__all__"

class RouteStopForm(StyledModelForm):
    morning_pickup_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={"type": "time", "step": "60"},
        ),
    )
    afternoon_dropoff_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(
            format="%H:%M",
            attrs={"type": "time", "step": "60"},
        ),
    )

    class Meta:
        model = RouteStop
        fields = "__all__"

class LearnerTransportForm(StyledModelForm):
    class Meta:
        model = LearnerTransport
        exclude = ("created_at", "updated_at")

class TransportTripForm(StyledModelForm):
    class Meta:
        model = TransportTrip
        exclude = ("created_at", "updated_at", "authorised_by", "actual_departure", "actual_arrival", "start_odometer_km", "end_odometer_km", "fuel_litres", "status")

class VehicleInspectionForm(StyledModelForm):
    class Meta:
        model = VehicleInspection
        exclude = ("created_at", "updated_at", "inspected_by", "inspected_at")

class BoardingEventForm(StyledModelForm):
    class Meta:
        model = BoardingEvent
        exclude = ("created_at", "updated_at", "recorded_by")

class MaintenanceRecordForm(StyledModelForm):
    class Meta:
        model = MaintenanceRecord
        exclude = ("created_at", "updated_at")

class TransportIncidentForm(StyledModelForm):
    class Meta:
        model = TransportIncident
        exclude = ("created_at", "updated_at", "reported_by")

class TransportChargeForm(StyledModelForm):
    class Meta:
        model = TransportCharge
        exclude = ("created_at", "updated_at")

class TransportPaymentForm(StyledModelForm):
    class Meta:
        model = TransportPayment
        exclude = ("created_at", "updated_at", "verified_by", "verified")

