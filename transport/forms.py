from django import forms
from fees.models import AcademicYear, Term

from .models import (
    Vehicle,
    Driver,
    Route,
    RouteStop,
    StudentTransportAssignment,
    TransportAssignment,
    TransportTrip,
    VehicleMaintenance,
    FuelRecord,
    TransportFeeStructure,
)

class BootstrapModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (
                f"{existing} form-control".strip()
            )

            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-check-input"


class VehicleForm(BootstrapModelForm):
    class Meta:
        model = Vehicle
        fields = [
            "registration_number",
            "vehicle_name",
            "vehicle_type",
            "make",
            "model",
            "year",
            "capacity",
            "status",
            "insurance_expiry",
            "inspection_expiry",
            "notes",
        ]
        widgets = {
            "insurance_expiry": forms.DateInput(attrs={"type": "date"}),
            "inspection_expiry": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class DriverForm(BootstrapModelForm):
    class Meta:
        model = Driver
        fields = ["employee", "licence_number", "licence_expiry", "status", "address", "notes"]
        widgets = {
            "licence_expiry": forms.DateInput(attrs={"type": "date"}),
        }

class RouteForm(BootstrapModelForm):
    class Meta:
        model = Route
        fields = [
            "name",
            "code",
            "description",
            "morning_departure",
            "afternoon_departure",
            "status",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "morning_departure": forms.TimeInput(
                attrs={"type": "time"}
            ),
            "afternoon_departure": forms.TimeInput(
                attrs={"type": "time"}
            ),
        }


class RouteStopForm(BootstrapModelForm):
    class Meta:
        model = RouteStop
        fields = [
            "route",
            "name",
            "location",
            "stop_order",
            "pickup_time",
            "dropoff_time",
            "is_active",
        ]
        widgets = {
            "pickup_time": forms.TimeInput(attrs={"type": "time"}),
            "dropoff_time": forms.TimeInput(attrs={"type": "time"}),
        }


class StudentTransportAssignmentForm(BootstrapModelForm):
    class Meta:
        model = StudentTransportAssignment
        fields = [
            "student",
            "route",
            "pickup_stop",
            "dropoff_stop",
            "morning_transport",
            "afternoon_transport",
            "start_date",
            "end_date",
            "status",
            "notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["pickup_stop"].queryset = RouteStop.objects.filter(
            is_active=True
        ).select_related("route")

        self.fields["dropoff_stop"].queryset = RouteStop.objects.filter(
            is_active=True
        ).select_related("route")


class TransportAssignmentForm(BootstrapModelForm):
    class Meta:
        model = TransportAssignment
        fields = [
            "route",
            "vehicle",
            "driver",
            "start_date",
            "end_date",
            "status",
            "notes",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class TransportTripForm(BootstrapModelForm):
    class Meta:
        model = TransportTrip
        fields = [
            "date",
            "route",
            "vehicle",
            "driver",
            "trip_type",
            "departure_time",
            "arrival_time",
            "status",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "departure_time": forms.TimeInput(attrs={"type": "time"}),
            "arrival_time": forms.TimeInput(attrs={"type": "time"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class VehicleMaintenanceForm(BootstrapModelForm):
    class Meta:
        model = VehicleMaintenance
        fields = [
            "vehicle",
            "maintenance_type",
            "date",
            "description",
            "service_provider",
            "cost",
            "next_service_date",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "next_service_date": forms.DateInput(
                attrs={"type": "date"}
            ),
            "description": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }


class FuelRecordForm(BootstrapModelForm):
    class Meta:
        model = FuelRecord
        fields = [
            "vehicle",
            "date",
            "litres",
            "cost",
            "odometer_reading",
            "fuel_station",
            "notes",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

class TransportFeeStructureForm(forms.ModelForm):
    class Meta:
        model=TransportFeeStructure
        fields=["academic_year","term","class_name","route","from_stop","to_stop","amount","billing_label","is_active"]
        widgets={"class_name":forms.TextInput(attrs={"placeholder":"e.g. Grade 5"}),"amount":forms.NumberInput(attrs={"step":"0.01","min":"0"})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields["from_stop"].queryset=RouteStop.objects.filter(is_active=True).select_related("route").order_by("route__name","stop_order")
        self.fields["to_stop"].queryset=RouteStop.objects.filter(is_active=True).select_related("route").order_by("route__name","stop_order")
    def clean(self):
        c=super().clean();route=c.get("route");a=c.get("from_stop");b=c.get("to_stop")
        if route and a and a.route_id!=route.id:raise forms.ValidationError("From/Pickup stop must belong to the selected route.")
        if route and b and b.route_id!=route.id:raise forms.ValidationError("To/Drop-off stop must belong to the selected route.")
        if a and b and a.id==b.id:raise forms.ValidationError("From and To stops must be different.")
        return c

class TransportFeeGenerateForm(forms.Form):
    academic_year = forms.ModelChoiceField(queryset=AcademicYear.objects.all(), empty_label="Select academic year")
    term = forms.ModelChoiceField(queryset=Term.objects.all(), empty_label="Select term")
    route = forms.ModelChoiceField(queryset=Route.objects.all(), required=False, empty_label="All active routes")



