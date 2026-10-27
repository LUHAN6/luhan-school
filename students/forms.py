from django import forms
from .models import Student, OnlineApplication
from timetable.models import TimetableClass
from academic.models import Stream
from transport.models import Route, RouteStop


def active_class_choices():
    rows = (
        TimetableClass.objects
        .filter(active=True)
        .exclude(name="")
        .values_list("name", flat=True)
        .distinct()
        .order_by("name")
    )
    return [(name, name) for name in rows]


def active_stream_choices():
    rows = (
        Stream.objects
        .filter(is_active=True)
        .exclude(name="")
        .values_list("name", flat=True)
        .distinct()
        .order_by("name")
    )
    return [(name, name) for name in rows]


class StudentForm(forms.ModelForm):

    class_name = forms.ChoiceField(
        choices=(),
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_class_name",
            }
        ),
        label="Class",
    )

    stream = forms.ChoiceField(
        choices=(),
        widget=forms.Select(
            attrs={
                "class": "form-select",
                "id": "id_stream",
            }
        ),
        label="Stream",
    )

    class Meta:
        model = Student
        fields = [
            "first_name",
            "middle_name",
            "last_name",
            "gender",
            "date_of_birth",
            "class_name",
            "stream",
            "parent_name",
            "parent_phone",
            "photo",
        "transport_required",
        ]
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "middle_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "gender": forms.Select(
                attrs={"class": "form-select"}
            ),
            "date_of_birth": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
            "parent_name": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "parent_phone": forms.TextInput(
                attrs={"class": "form-control"}
            ),
            "photo": forms.ClearableFileInput(
                attrs={"class": "form-control"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        class_choices = active_class_choices()
        stream_choices = active_stream_choices()

        current_class = self.instance.class_name if self.instance.pk else ""
        current_stream = self.instance.stream if self.instance.pk else ""

        class_values = {value for value, label in class_choices}
        stream_values = {value for value, label in stream_choices}

        if current_class and current_class not in class_values:
            class_choices.insert(
                0,
                (current_class, f"{current_class} (Inactive)")
            )

        if current_stream and current_stream not in stream_values:
            stream_choices.insert(
                0,
                (current_stream, f"{current_stream} (Inactive)")
            )

        self.fields["class_name"].choices = [
            ("", "Select Class")
        ] + class_choices

        self.fields["stream"].choices = [
            ("", "Select Stream")
        ] + stream_choices

    def clean(self):
        cleaned = super().clean()
        class_name = cleaned.get("class_name")
        stream = cleaned.get("stream")

        if class_name:
            if not TimetableClass.objects.filter(
                name=class_name,
                active=True,
            ).exists():
                raise forms.ValidationError(
                    "Please select a Class from the active school configuration."
                )

        if stream:
            if not Stream.objects.filter(
                name=stream,
                is_active=True,
            ).exists():
                raise forms.ValidationError(
                    "Please select a Stream from the active school configuration."
                )

        return cleaned


class OnlineApplicationForm(forms.ModelForm):
    requested_class=forms.ChoiceField(choices=(),widget=forms.Select(attrs={"class":"form-select","id":"id_requested_class"}),label="Requested Class")
    requested_stream=forms.ChoiceField(choices=(),widget=forms.Select(attrs={"class":"form-select","id":"id_requested_stream"}),label="Requested Stream",required=False)
    transport_required=forms.BooleanField(required=False,label="School Transport Required?",widget=forms.CheckboxInput(attrs={"class":"form-check-input","id":"id_transport_required"}))
    transport_route=forms.ModelChoiceField(queryset=Route.objects.none(),required=False,label="Route",widget=forms.Select(attrs={"class":"form-select","id":"id_transport_route"}))
    transport_from_stop=forms.ModelChoiceField(queryset=RouteStop.objects.none(),required=False,label="From / Pickup",widget=forms.Select(attrs={"class":"form-select","id":"id_transport_from_stop"}))
    transport_to_stop=forms.ModelChoiceField(queryset=RouteStop.objects.none(),required=False,label="To / Drop-off",widget=forms.Select(attrs={"class":"form-select","id":"id_transport_to_stop"}))
    class Meta:
        model=OnlineApplication
        fields=["first_name","middle_name","last_name","gender","date_of_birth","requested_class","requested_stream","parent_name","parent_phone","parent_email","previous_school","address","transport_required","transport_route","transport_from_stop","transport_to_stop"]
        widgets={"date_of_birth":forms.DateInput(attrs={"type":"date"}),"address":forms.Textarea(attrs={"rows":3})}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields["requested_class"].choices=[("","Select Class")]+active_class_choices()
        self.fields["requested_stream"].choices=[("","Select Stream")]+active_stream_choices()
        self.fields["transport_route"].queryset=Route.objects.all().order_by("name")
        self.fields["transport_from_stop"].queryset=RouteStop.objects.filter(is_active=True).select_related("route").order_by("route__name","stop_order")
        self.fields["transport_to_stop"].queryset=RouteStop.objects.filter(is_active=True).select_related("route").order_by("route__name","stop_order")
    def clean(self):
        c=super().clean();cn=c.get("requested_class");st=c.get("requested_stream")
        if cn and not TimetableClass.objects.filter(name=cn,active=True).exists(): raise forms.ValidationError("Please select a Class from the active school configuration.")
        if st and not Stream.objects.filter(name=st,is_active=True).exists(): raise forms.ValidationError("Please select a Stream from the active school configuration.")
        if c.get("transport_required"):
            route=c.get("transport_route");a=c.get("transport_from_stop");b=c.get("transport_to_stop")
            if not route or not a or not b: raise forms.ValidationError("Transport is required. Select Route, From/Pickup and To/Drop-off.")
            if a.route_id!=route.id or b.route_id!=route.id: raise forms.ValidationError("Selected stops must belong to the selected route.")
            if a.id==b.id: raise forms.ValidationError("From and To stops must be different.")
        else:c["transport_route"]=c["transport_from_stop"]=c["transport_to_stop"]=None
        return c

