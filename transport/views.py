from django import forms
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.worksheet.datavalidation import DataValidation
from io import BytesIO
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.staff_access import role_permission_required

from fees.models import FeeRecord, AcademicYear, Term
from .forms import TransportFeeStructureForm, TransportFeeGenerateForm
from .models import TransportFeeCharge, TransportFeeStructure
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
)


# =========================================================
# MODEL CONFIGURATION
# =========================================================

MODEL_CONFIG = {

    "vehicle": {
        "model": Vehicle,
        "title": "Vehicles",
        "singular": "Vehicle",
        "permission": "vehicle",
        "list_url": "transport:vehicle_list",
        "add_url": "transport:vehicle_add",
        "edit_url": "transport:vehicle_edit",
        "delete_url": "transport:vehicle_delete",
        "fields": [
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
        ],
        "columns": [
            "registration_number",
            "vehicle_name",
            "vehicle_type",
            "capacity",
            "status",
            "insurance_expiry",
            "inspection_expiry",
        ],
        "search_fields": [
            "registration_number",
            "vehicle_name",
            "make",
            "model",
        ],
    },

        "driver": {
        "model": Driver,
        "title": "Drivers",
        "singular": "Driver",
        "permission": "driver",
        "list_url": "transport:driver_list",
        "add_url": "transport:driver_add",
        "edit_url": "transport:driver_edit",
        "delete_url": "transport:driver_delete",
        "fields": [
            "employee",
            "licence_number",
            "licence_expiry",
            "status",
            "address",
            "notes",
        ],
        "columns": [
            "employee",
            "licence_number",
            "licence_expiry",
            "status",
        ],
        "search_fields": [
            "employee__first_name",
            "employee__last_name",
            "employee__phone",
            "employee__phone_number",
            "employee__national_id",
            "employee__id_number",
            "licence_number",
        ],
    },
"route": {
        "model": Route,
        "title": "Routes",
        "singular": "Route",
        "permission": "route",
        "list_url": "transport:route_list",
        "add_url": "transport:route_add",
        "edit_url": "transport:route_edit",
        "delete_url": "transport:route_delete",
        "fields": [
            "name",
            "code",
            "description",
            "morning_departure",
            "afternoon_departure",
            "status",
        ],
        "columns": [
            "code",
            "name",
            "morning_departure",
            "afternoon_departure",
            "status",
        ],
        "search_fields": [
            "name",
            "code",
            "description",
        ],
    },

    "routestop": {
        "model": RouteStop,
        "title": "Route Stops",
        "singular": "Route Stop",
        "permission": "routestop",
        "list_url": "transport:routestop_list",
        "add_url": "transport:routestop_add",
        "edit_url": "transport:routestop_edit",
        "delete_url": "transport:routestop_delete",
        "fields": [
            "route",
            "name",
            "location",
            "stop_order",
            "pickup_time",
            "dropoff_time",
            "is_active",
        ],
        "columns": [
            "route",
            "stop_order",
            "name",
            "location",
            "pickup_time",
            "dropoff_time",
            "is_active",
        ],
        "search_fields": [
            "name",
            "location",
            "route__name",
            "route__code",
        ],
    },

    "studenttransportassignment": {
        "model": StudentTransportAssignment,
        "title": "Student Transport Assignments",
        "singular": "Student Transport Assignment",
        "permission": "studenttransportassignment",
        "list_url": "transport:student_assignment_list",
        "add_url": "transport:student_assignment_add",
        "edit_url": "transport:student_assignment_edit",
        "delete_url": "transport:student_assignment_delete",
        "fields": [
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
        ],
        "columns": [
            "student",
            "route",
            "pickup_stop",
            "dropoff_stop",
            "morning_transport",
            "afternoon_transport",
            "start_date",
            "end_date",
            "status",
        ],
        "search_fields": [
            "student__first_name",
            "student__last_name",
            "student__admission_no",
            "route__name",
            "route__code",
        ],
    },

    "transportassignment": {
        "model": TransportAssignment,
        "title": "Vehicle / Driver Route Assignments",
        "singular": "Transport Assignment",
        "permission": "transportassignment",
        "list_url": "transport:assignment_list",
        "add_url": "transport:assignment_add",
        "edit_url": "transport:assignment_edit",
        "delete_url": "transport:assignment_delete",
        "fields": [
            "route",
            "vehicle",
            "driver",
            "start_date",
            "end_date",
            "status",
            "notes",
        ],
        "columns": [
            "route",
            "vehicle",
            "driver",
            "start_date",
            "end_date",
            "status",
        ],
        "search_fields": [
            "route__name",
            "route__code",
            "vehicle__registration_number",
            "driver__first_name",
            "driver__last_name",
        ],
    },

    "transporttrip": {
        "model": TransportTrip,
        "title": "Transport Trips",
        "singular": "Transport Trip",
        "permission": "transporttrip",
        "list_url": "transport:trip_list",
        "add_url": "transport:trip_add",
        "edit_url": "transport:trip_edit",
        "delete_url": "transport:trip_delete",
        "fields": [
            "date",
            "route",
            "vehicle",
            "driver",
            "trip_type",
            "departure_time",
            "arrival_time",
            "status",
            "notes",
        ],
        "columns": [
            "date",
            "route",
            "vehicle",
            "driver",
            "trip_type",
            "departure_time",
            "arrival_time",
            "status",
        ],
        "search_fields": [
            "route__name",
            "route__code",
            "vehicle__registration_number",
            "driver__first_name",
            "driver__last_name",
        ],
    },

    "vehiclemaintenance": {
        "model": VehicleMaintenance,
        "title": "Vehicle Maintenance",
        "singular": "Vehicle Maintenance Record",
        "permission": "vehiclemaintenance",
        "list_url": "transport:maintenance_list",
        "add_url": "transport:maintenance_add",
        "edit_url": "transport:maintenance_edit",
        "delete_url": "transport:maintenance_delete",
        "fields": [
            "vehicle",
            "maintenance_type",
            "date",
            "description",
            "service_provider",
            "cost",
            "next_service_date",
            "notes",
        ],
        "columns": [
            "vehicle",
            "maintenance_type",
            "date",
            "service_provider",
            "cost",
            "next_service_date",
        ],
        "search_fields": [
            "vehicle__registration_number",
            "service_provider",
            "description",
        ],
    },

    "fuelrecord": {
        "model": FuelRecord,
        "title": "Fuel Records",
        "singular": "Fuel Record",
        "permission": "fuelrecord",
        "list_url": "transport:fuel_list",
        "add_url": "transport:fuel_add",
        "edit_url": "transport:fuel_edit",
        "delete_url": "transport:fuel_delete",
        "fields": [
            "vehicle",
            "date",
            "litres",
            "cost",
            "odometer_reading",
            "fuel_station",
            "notes",
        ],
        "columns": [
            "vehicle",
            "date",
            "litres",
            "cost",
            "odometer_reading",
            "fuel_station",
        ],
        "search_fields": [
            "vehicle__registration_number",
            "fuel_station",
        ],
    },
}


# =========================================================
# FORM FACTORY
# =========================================================

@login_required
def transport_fee_dashboard(request):
    charges = TransportFeeCharge.objects.select_related(
        "student_assignment__student", "student_assignment__route",
        "student_assignment__pickup_stop", "fee_structure__academic_year",
        "fee_structure__term", "fee_record"
    )
    status = request.GET.get("status", "")
    route_id = request.GET.get("route", "")
    term_id = request.GET.get("term", "")
    year_id = request.GET.get("year", "")
    q = request.GET.get("q", "").strip()
    if status:
        charges = charges.filter(status=status)
    if route_id:
        charges = charges.filter(student_assignment__route_id=route_id)
    if term_id:
        charges = charges.filter(fee_structure__term_id=term_id)
    if year_id:
        charges = charges.filter(fee_structure__academic_year_id=year_id)
    if q:
        charges = charges.filter(
            Q(student_assignment__student__first_name__icontains=q) |
            Q(student_assignment__student__last_name__icontains=q) |
            Q(student_assignment__student__admission_number__icontains=q)
        )
    structures = TransportFeeStructure.objects.select_related("academic_year", "term", "route", "stop")
    total_charged = charges.aggregate(total=Sum("amount"))["total"] or 0
    total_paid = sum((c.paid_amount for c in charges), 0)
    total_outstanding = sum((c.outstanding_amount for c in charges), 0)
    return render(request, "transport/transport_fees.html", {
        "charges": charges[:100], "structures": structures[:12],
        "routes": Route.objects.filter(status="ACTIVE").order_by("name"),
        "terms": Term.objects.select_related("academic_year").order_by("-academic_year__year", "order"),
        "years": AcademicYear.objects.order_by("-year"),
        "total_charged": total_charged, "total_paid": total_paid,
        "total_outstanding": total_outstanding,
        "active_structure_count": structures.filter(is_active=True).count(),
        "selected_status": status, "selected_route": route_id,
        "selected_term": term_id, "selected_year": year_id, "q": q,
    })


@login_required
def transport_fee_structure_add(request):
    form = TransportFeeStructureForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("transport:transport_fee_dashboard")
    return render(request, "transport/transport_fee_structure_form.html", {"form": form, "title": "Add Transport Fee Structure"})


@login_required
def transport_fee_structure_edit(request, pk):
    obj = get_object_or_404(TransportFeeStructure, pk=pk)
    form = TransportFeeStructureForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("transport:transport_fee_dashboard")
    return render(request, "transport/transport_fee_structure_form.html", {"form": form, "title": "Edit Transport Fee Structure"})


@login_required
def transport_fee_structure_delete(request, pk):
    obj = get_object_or_404(TransportFeeStructure, pk=pk)
    if request.method == "POST":
        obj.delete()
        return redirect("transport:transport_fee_dashboard")
    return render(request, "transport/transport_fee_confirm_delete.html", {"object": obj})


@login_required
def transport_fee_generate(request):
    form = TransportFeeGenerateForm(request.POST or None)
    if request.method != "POST":
        return render(request, "transport/transport_fee_generate.html", {"form": form})
    if not form.is_valid():
        return render(request, "transport/transport_fee_generate.html", {"form": form})
    academic_year = form.cleaned_data["academic_year"]
    term = form.cleaned_data["term"]
    route = form.cleaned_data["route"]
    structures = TransportFeeStructure.objects.filter(academic_year=academic_year, term=term, is_active=True)
    if route:
        structures = structures.filter(route=route)
    assignments = StudentTransportAssignment.objects.filter(status="ACTIVE").select_related("student", "route", "pickup_stop")
    for assignment in assignments:
        if not assignment.route_id:
            continue
        matches = structures.filter(route_id=assignment.route_id)
        structure = matches.filter(stop_id=assignment.pickup_stop_id).first() if assignment.pickup_stop_id else None
        structure = structure or matches.filter(stop__isnull=True).first()
        if not structure:
            continue
        if TransportFeeCharge.objects.filter(student_assignment=assignment, fee_structure=structure).exists():
            continue
        fee_record, _ = FeeRecord.objects.get_or_create(
            student=assignment.student, academic_year=academic_year, term=term,
            defaults={"amount_charged": 0, "opening_balance": 0,
                      "old_academic_year": str(academic_year.year),
                      "old_term": str(term.order)}
        )
        fee_record.amount_charged = (fee_record.amount_charged or 0) + structure.amount
        fee_record.save(update_fields=["amount_charged"])
        TransportFeeCharge.objects.create(
            student_assignment=assignment, fee_structure=structure,
            fee_record=fee_record, amount=structure.amount
        )
    return redirect("transport:transport_fee_dashboard")

def transport_form(_model, _fields):
    """
    Dynamic ModelForm factory for Transport.

    Driver identity comes from the HR Payroll Employee record.
    Transport only collects driver-specific transport information.
    """

    class TransportModelForm(forms.ModelForm):

        class Meta:
            model = _model
            fields = _fields

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            for name, field in self.fields.items():

                css = "transport-input"

                if isinstance(field.widget, forms.Textarea):
                    css = "transport-input transport-textarea"

                elif isinstance(
                    field.widget,
                    (
                        forms.Select,
                        forms.SelectMultiple,
                    ),
                ):
                    css = "transport-input transport-select"

                field.widget.attrs["class"] = css

                # Route departure times: browser time picker plus manual entry.
                if _model.__name__ == "Route" and name in (
                    "morning_departure",
                    "afternoon_departure",
                ):
                    field.widget = forms.TimeInput(
                        format="%H:%M",
                        attrs={
                            "type": "time",
                            "step": "60",
                            "class": css,
                        },
                    )

                # Route status is a dropdown using the model's Active/Inactive choices.
                if _model.__name__ == "Route" and name == "status":
                    field.widget = forms.Select(
                        attrs={"class": "transport-input transport-select"}
                    )

                if field.label:
                    field.label = field.label.replace(
                        "_",
                        " ",
                    ).title()

            # -----------------------------------------------------
            # DRIVER EMPLOYEE SELECTOR
            # -----------------------------------------------------
            if "employee" in self.fields:

                self.fields["employee"].label = "HR Employee"

                self.fields["employee"].help_text = (
                    "Select an existing employee from HR Payroll. "
                    "Employee name, phone and identification details "
                    "are taken from the HR record."
                )

                employee_field = self.fields["employee"]

                try:
                    employees = employee_field.queryset

                    choices = [("", "---------")]

                    for employee in employees:

                        first_name = getattr(
                            employee,
                            "first_name",
                            "",
                        ) or ""

                        last_name = getattr(
                            employee,
                            "last_name",
                            "",
                        ) or ""

                        employee_number = (
                            getattr(
                                employee,
                                "employee_number",
                                None,
                            )
                            or getattr(
                                employee,
                                "staff_number",
                                None,
                            )
                            or ""
                        )

                        full_name = (
                            f"{first_name} {last_name}"
                        ).strip()

                        if employee_number:
                            label = (
                                f"{full_name} "
                                f"â€” {employee_number}"
                            )
                        else:
                            label = full_name

                        choices.append(
                            (
                                employee.pk,
                                label,
                            )
                        )

                    employee_field.choices = choices

                except Exception:
                    pass

    return TransportModelForm

def transport_dashboard(request):

    total_vehicles = Vehicle.objects.count()
    total_drivers = Driver.objects.count()
    total_routes = Route.objects.count()
    total_stops = RouteStop.objects.count()
    total_student_assignments = StudentTransportAssignment.objects.count()
    total_assignments = TransportAssignment.objects.count()
    total_trips = TransportTrip.objects.count()
    total_maintenance = VehicleMaintenance.objects.count()
    total_fuel_records = FuelRecord.objects.count()

    active_vehicles = Vehicle.objects.filter(
        status="ACTIVE"
    ).count()

    inactive_vehicles = Vehicle.objects.filter(
        status="INACTIVE"
    ).count()

    maintenance_vehicles = Vehicle.objects.filter(
        status="MAINTENANCE"
    ).count()

    vehicles = Vehicle.objects.all().order_by("-id")[:8]

    drivers = Driver.objects.all().order_by("-id")[:8]

    routes = Route.objects.all().order_by("-id")[:8]

    trips = (
        TransportTrip.objects
        .select_related("route", "vehicle", "driver")
        .order_by("-date", "-id")[:8]
    )

    fuel_records = (
        FuelRecord.objects
        .select_related("vehicle")
        .order_by("-date", "-id")[:8]
    )

    maintenance_records = (
        VehicleMaintenance.objects
        .select_related("vehicle")
        .order_by("-date", "-id")[:8]
    )

    context = {
        "total_vehicles": total_vehicles,
        "total_drivers": total_drivers,
        "total_routes": total_routes,
        "total_stops": total_stops,
        "total_student_assignments": total_student_assignments,
        "total_assignments": total_assignments,
        "total_trips": total_trips,
        "total_maintenance": total_maintenance,
        "total_fuel_records": total_fuel_records,

        "active_vehicles": active_vehicles,
        "inactive_vehicles": inactive_vehicles,
        "maintenance_vehicles": maintenance_vehicles,

        "vehicles": vehicles,
        "drivers": drivers,
        "routes": routes,
        "trips": trips,
        "fuel_records": fuel_records,
        "maintenance_records": maintenance_records,
    }

    return render(
        request,
        "transport/transport_dashboard.html",
        context,
    )


# =========================================================
# GENERIC LIST
# =========================================================

def _transport_list(request, key):

    config = MODEL_CONFIG[key]
    model = config["model"]

    queryset = model.objects.all()

    search = request.GET.get("q", "").strip()

    if search:
        query = Q()

        for field in config["search_fields"]:
            query |= Q(**{f"{field}__icontains": search})

        queryset = queryset.filter(query)

    queryset = queryset.order_by("-id")

    rows = []

    for obj in queryset:

        values = []

        for field_name in config["columns"]:

            field = model._meta.get_field(field_name)

            if hasattr(obj, f"get_{field_name}_display"):
                value = getattr(
                    obj,
                    f"get_{field_name}_display"
                )()

            else:
                value = getattr(
                    obj,
                    field_name,
                    "",
                )

            if value is None:
                value = ""

            values.append(value)

        rows.append({
            "object": obj,
            "values": values,
        })

    context = {
        "title": config["title"],
        "singular": config["singular"],
        "columns": config["columns"],
        "rows": rows,
        "search": search,
        "config": config,
        "add_permission": f"add_{config['permission']}",
        "change_permission": f"change_{config['permission']}",
        "delete_permission": f"delete_{config['permission']}",
    }

    return render(
        request,
        "transport/model_list.html",
        context,
    )


# =========================================================
# GENERIC ADD
# =========================================================

def _transport_add(request, key):

    config = MODEL_CONFIG[key]

    FormClass = transport_form(
        config["model"],
        config["fields"],
    )

    if request.method == "POST":

        form = FormClass(request.POST)

        if form.is_valid():

            obj = form.save()

            messages.success(
                request,
                f"{config['singular']} created successfully.",
            )

            return redirect(config["list_url"])

    else:
        form = FormClass()

    return render(
        request,
        "transport/model_form.html",
        {
            "form": form,
            "title": f"Add {config['singular']}",
            "singular": config["singular"],
            "config": config,
        },
    )


# =========================================================
# GENERIC EDIT
# =========================================================

def _transport_edit(request, key, pk):

    config = MODEL_CONFIG[key]

    obj = get_object_or_404(
        config["model"],
        pk=pk,
    )

    FormClass = transport_form(
        config["model"],
        config["fields"],
    )

    if request.method == "POST":

        form = FormClass(
            request.POST,
            instance=obj,
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                f"{config['singular']} updated successfully.",
            )

            return redirect(config["list_url"])

    else:
        form = FormClass(instance=obj)

    return render(
        request,
        "transport/model_form.html",
        {
            "form": form,
            "title": f"Edit {config['singular']}",
            "singular": config["singular"],
            "config": config,
            "object": obj,
        },
    )


# =========================================================
# GENERIC DELETE
# =========================================================

def _transport_delete(request, key, pk):

    config = MODEL_CONFIG[key]

    obj = get_object_or_404(
        config["model"],
        pk=pk,
    )

    if request.method == "POST":

        obj.delete()

        messages.success(
            request,
            f"{config['singular']} deleted successfully.",
        )

        return redirect(config["list_url"])

    return render(
        request,
        "transport/model_confirm_delete.html",
        {
            "object": obj,
            "title": f"Delete {config['singular']}",
            "singular": config["singular"],
            "config": config,
        },
    )


# =========================================================
# VEHICLES
# =========================================================

@login_required
@role_permission_required("view_vehicle", "transport")
def vehicle_list(request):
    return _transport_list(request, "vehicle")


@login_required
@role_permission_required("add_vehicle", "transport")
def vehicle_add(request):
    return _transport_add(request, "vehicle")


@login_required
@role_permission_required("change_vehicle", "transport")
def vehicle_edit(request, pk):
    return _transport_edit(request, "vehicle", pk)


@login_required
@role_permission_required("delete_vehicle", "transport")
def vehicle_delete(request, pk):
    return _transport_delete(request, "vehicle", pk)


# =========================================================
# DRIVERS
# =========================================================

@login_required
@role_permission_required("view_driver", "transport")
def driver_list(request):
    return _transport_list(request, "driver")


@login_required
@role_permission_required("add_driver", "transport")
def driver_add(request):
    return _transport_add(request, "driver")


@login_required
@role_permission_required("change_driver", "transport")
def driver_edit(request, pk):
    return _transport_edit(request, "driver", pk)


@login_required
@role_permission_required("delete_driver", "transport")
def driver_delete(request, pk):
    return _transport_delete(request, "driver", pk)


# =========================================================
# ROUTES
# =========================================================



# =========================================================
# ROUTE CSV DOWNLOAD / EXPORT / IMPORT
# =========================================================

import csv
import io
from datetime import datetime

from django.db import IntegrityError, transaction
from django.http import HttpResponse


ROUTE_CSV_FIELDS = [
    "name",
    "code",
    "description",
    "morning_departure",
    "afternoon_departure",
    "status",
]


def _route_csv_response(filename):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    return response


@login_required
@role_permission_required("view_route", "transport")
def route_csv_template(request):
    response = _route_csv_response("transport_routes_template.csv")
    writer = csv.writer(response)
    writer.writerow(ROUTE_CSV_FIELDS)
    return response


@login_required
@role_permission_required("view_route", "transport")
def route_csv_export(request):
    """Export existing routes in the exact CSV import-template format."""
    response = _route_csv_response("transport_routes_export.csv")
    writer = csv.writer(response, lineterminator="\r\n")
    writer.writerow(ROUTE_CSV_FIELDS)

    routes = Route.objects.order_by("name").iterator()

    for route in routes:
        writer.writerow([
            route.name or "",
            route.code or "",
            route.description or "",
            route.morning_departure.strftime("%H:%M") if route.morning_departure else "",
            route.afternoon_departure.strftime("%H:%M") if route.afternoon_departure else "",
            route.status or "ACTIVE",
        ])

    return response


@login_required
@role_permission_required("view_route", "transport")
def route_excel_export(request):
    """Export existing transport routes to an Excel workbook."""
    from datetime import time as dt_time

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Routes"

    headers = list(ROUTE_CSV_FIELDS)
    sheet.append(headers)

    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(
            fill_type="solid",
            fgColor="1F4E78",
        )
        cell.alignment = Alignment(horizontal="center")

    for route in Route.objects.order_by("name").iterator():
        sheet.append([
            route.name or "",
            route.code or "",
            route.description or "",
            route.morning_departure,
            route.afternoon_departure,
            (route.status or "ACTIVE").upper(),
        ])

    for row_number in range(2, sheet.max_row + 1):
        for column in ("D", "E"):
            sheet[f"{column}{row_number}"].number_format = "hh:mm"

    widths = {
        "A": 28,
        "B": 18,
        "C": 42,
        "D": 22,
        "E": 23,
        "F": 18,
    }
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        'attachment; filename="transport_routes_export.xlsx"'
    )
    return response


@login_required
@role_permission_required("add_route", "transport")
def route_csv_import(request):
    errors = []
    imported_count = None

    if request.method == "POST":
        upload = request.FILES.get("csv_file")

        if not upload:
            errors.append("Choose a CSV file to upload.")
        elif upload.size > 5 * 1024 * 1024:
            errors.append("The CSV file must be 5 MB or smaller.")
        else:
            try:
                decoded = upload.read().decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(decoded))

                if not reader.fieldnames:
                    errors.append("The CSV file is empty or has no header row.")
                else:
                    reader.fieldnames = [
                        (name or "").strip().lower()
                        for name in reader.fieldnames
                    ]
                    missing = [
                        field for field in ROUTE_CSV_FIELDS
                        if field not in reader.fieldnames
                    ]

                    if missing:
                        errors.append(
                            "Missing required CSV columns: " + ", ".join(missing)
                        )
                    elif len(reader.fieldnames) != len(set(reader.fieldnames)):
                        errors.append("The CSV contains duplicate column names.")
                    else:
                        rows = []
                        seen_names = set()
                        seen_codes = set()
                        existing_names = set(
                            Route.objects.values_list("name", flat=True)
                        )
                        existing_codes = set(
                            Route.objects.values_list("code", flat=True)
                        )

                        for line_number, raw in enumerate(reader, start=2):
                            if not raw or not any(
                                str(value or "").strip()
                                for value in raw.values()
                            ):
                                continue

                            row = {
                                key: (value or "").strip()
                                for key, value in raw.items()
                                if key is not None
                            }

                            name = row.get("name", "")
                            code = row.get("code", "")
                            description = row.get("description", "")
                            status = row.get("status", "").upper() or "ACTIVE"
                            morning_text = row.get("morning_departure", "")
                            afternoon_text = row.get("afternoon_departure", "")

                            row_errors = []

                            if not name:
                                row_errors.append("name is required")
                            elif len(name) > 100:
                                row_errors.append("name exceeds 100 characters")

                            if not code:
                                row_errors.append("code is required")
                            elif len(code) > 30:
                                row_errors.append("code exceeds 30 characters")

                            if name in existing_names or name in seen_names:
                                row_errors.append(f"duplicate route name: {name}")
                            if code in existing_codes or code in seen_codes:
                                row_errors.append(f"duplicate route code: {code}")

                            if status not in ("ACTIVE", "INACTIVE"):
                                row_errors.append(
                                    "status must be ACTIVE or INACTIVE"
                                )

                            parsed_times = []
                            for label, value in (
                                ("morning_departure", morning_text),
                                ("afternoon_departure", afternoon_text),
                            ):
                                if not value:
                                    parsed_times.append(None)
                                else:
                                    try:
                                        parsed_times.append(
                                            datetime.strptime(value, "%H:%M").time()
                                        )
                                    except ValueError:
                                        row_errors.append(
                                            f"{label} must use HH:MM format, e.g. 07:30"
                                        )
                                        parsed_times.append(None)

                            if row_errors:
                                errors.append(
                                    f"Row {line_number}: " + "; ".join(row_errors)
                                )
                            else:
                                seen_names.add(name)
                                seen_codes.add(code)
                                rows.append(Route(
                                    name=name,
                                    code=code,
                                    description=description,
                                    morning_departure=parsed_times[0],
                                    afternoon_departure=parsed_times[1],
                                    status=status,
                                ))

                            if line_number > 5001:
                                errors.append(
                                    "The file exceeds the 5,000 data-row limit."
                                )
                                break

                        if not errors and not rows:
                            errors.append("The CSV contains no route rows to import.")

                        if not errors:
                            try:
                                with transaction.atomic():
                                    Route.objects.bulk_create(rows)
                                imported_count = len(rows)
                            except IntegrityError:
                                errors.append(
                                    "Import was cancelled because a route name or "
                                    "code conflicts with an existing record. "
                                    "No routes were imported; check the CSV and retry."
                                )

            except UnicodeDecodeError:
                errors.append("Could not read the file as UTF-8 CSV.")
            except csv.Error as exc:
                errors.append(f"Invalid CSV file: {exc}")

        if imported_count is not None:
            messages.success(
                request,
                f"Successfully imported {imported_count} route(s)."
            )
            return redirect("transport:route_list")

    return render(request, "transport/route_csv_import.html", {
        "errors": errors,
        "csv_fields": ROUTE_CSV_FIELDS,
    })


@login_required
@role_permission_required("view_route", "transport")
def route_list(request):
    return _transport_list(request, "route")


@login_required
@role_permission_required("add_route", "transport")
def route_add(request):
    return _transport_add(request, "route")


@login_required
@role_permission_required("change_route", "transport")
def route_edit(request, pk):
    return _transport_edit(request, "route", pk)


@login_required
@role_permission_required("delete_route", "transport")
def route_delete(request, pk):
    return _transport_delete(request, "route", pk)


# =========================================================
# ROUTE STOPS
# =========================================================

@login_required
@role_permission_required("view_routestop", "transport")
def routestop_list(request):
    return _transport_list(request, "routestop")


@login_required
@role_permission_required("add_routestop", "transport")
def routestop_add(request):
    return _transport_add(request, "routestop")


@login_required
@role_permission_required("change_routestop", "transport")
def routestop_edit(request, pk):
    return _transport_edit(request, "routestop", pk)


@login_required
@role_permission_required("delete_routestop", "transport")
def routestop_delete(request, pk):
    return _transport_delete(request, "routestop", pk)


# =========================================================
# STUDENT TRANSPORT ASSIGNMENTS
# =========================================================

@login_required
@role_permission_required(
    "view_studenttransportassignment",
    "transport",
)
def student_assignment_list(request):
    return _transport_list(
        request,
        "studenttransportassignment",
    )


@login_required
@role_permission_required(
    "add_studenttransportassignment",
    "transport",
)
def student_assignment_add(request):
    return _transport_add(
        request,
        "studenttransportassignment",
    )


@login_required
@role_permission_required(
    "change_studenttransportassignment",
    "transport",
)
def student_assignment_edit(request, pk):
    return _transport_edit(
        request,
        "studenttransportassignment",
        pk,
    )


@login_required
@role_permission_required(
    "delete_studenttransportassignment",
    "transport",
)
def student_assignment_delete(request, pk):
    return _transport_delete(
        request,
        "studenttransportassignment",
        pk,
    )


# =========================================================
# VEHICLE / DRIVER ROUTE ASSIGNMENTS
# =========================================================

@login_required
@role_permission_required(
    "view_transportassignment",
    "transport",
)
def assignment_list(request):
    return _transport_list(
        request,
        "transportassignment",
    )


@login_required
@role_permission_required(
    "add_transportassignment",
    "transport",
)
def assignment_add(request):
    return _transport_add(
        request,
        "transportassignment",
    )


@login_required
@role_permission_required(
    "change_transportassignment",
    "transport",
)
def assignment_edit(request, pk):
    return _transport_edit(
        request,
        "transportassignment",
        pk,
    )


@login_required
@role_permission_required(
    "delete_transportassignment",
    "transport",
)
def assignment_delete(request, pk):
    return _transport_delete(
        request,
        "transportassignment",
        pk,
    )


# =========================================================
# TRANSPORT TRIPS
# =========================================================

@login_required
@role_permission_required(
    "view_transporttrip",
    "transport",
)
def trip_list(request):
    return _transport_list(
        request,
        "transporttrip",
    )


@login_required
@role_permission_required(
    "add_transporttrip",
    "transport",
)
def trip_add(request):
    return _transport_add(
        request,
        "transporttrip",
    )


@login_required
@role_permission_required(
    "change_transporttrip",
    "transport",
)
def trip_edit(request, pk):
    return _transport_edit(
        request,
        "transporttrip",
        pk,
    )


@login_required
@role_permission_required(
    "delete_transporttrip",
    "transport",
)
def trip_delete(request, pk):
    return _transport_delete(
        request,
        "transporttrip",
        pk,
    )


# =========================================================
# VEHICLE MAINTENANCE
# =========================================================

@login_required
@role_permission_required(
    "view_vehiclemaintenance",
    "transport",
)
def maintenance_list(request):
    return _transport_list(
        request,
        "vehiclemaintenance",
    )


@login_required
@role_permission_required(
    "add_vehiclemaintenance",
    "transport",
)
def maintenance_add(request):
    return _transport_add(
        request,
        "vehiclemaintenance",
    )


@login_required
@role_permission_required(
    "change_vehiclemaintenance",
    "transport",
)
def maintenance_edit(request, pk):
    return _transport_edit(
        request,
        "vehiclemaintenance",
        pk,
    )


@login_required
@role_permission_required(
    "delete_vehiclemaintenance",
    "transport",
)
def maintenance_delete(request, pk):
    return _transport_delete(
        request,
        "vehiclemaintenance",
        pk,
    )


# =========================================================
# FUEL RECORDS
# =========================================================

@login_required
@role_permission_required(
    "view_fuelrecord",
    "transport",
)
def fuel_list(request):
    return _transport_list(
        request,
        "fuelrecord",
    )


@login_required
@role_permission_required(
    "add_fuelrecord",
    "transport",
)
def fuel_add(request):
    return _transport_add(
        request,
        "fuelrecord",
    )


@login_required
@role_permission_required(
    "change_fuelrecord",
    "transport",
)
def fuel_edit(request, pk):
    return _transport_edit(
        request,
        "fuelrecord",
        pk,
    )


@login_required
@role_permission_required(
    "delete_fuelrecord",
    "transport",
)
def fuel_delete(request, pk):
    return _transport_delete(
        request,
        "fuelrecord",
        pk,
    )








@login_required
def unified_transport_fee_dashboard(request):
    from fees.models import AcademicYear,Term
    from .models import TransportFeeStructure
    q=TransportFeeStructure.objects.select_related("academic_year","term","route","from_stop","to_stop").order_by("-academic_year__year","term__order","class_name","route__name","from_stop__stop_order")
    if request.GET.get("year"):q=q.filter(academic_year_id=request.GET["year"])
    if request.GET.get("term"):q=q.filter(term_id=request.GET["term"])
    return render(request,"transport/transport_fees.html",{"structures":q,"years":AcademicYear.objects.order_by("-year"),"terms":Term.objects.order_by("order"),"selected_year":request.GET.get("year",""),"selected_term":request.GET.get("term","")})
@login_required
def unified_transport_fee_add(request):
    from .forms import TransportFeeStructureForm
    form=TransportFeeStructureForm(request.POST or None)
    if request.method=="POST" and form.is_valid():form.save();return redirect("transport:transport_fee_dashboard")
    return render(request,"transport/transport_fee_structure_form.html",{"form":form,"title":"Add Transport Fee Structure"})
@login_required
def unified_transport_fee_edit(request,pk):
    from .forms import TransportFeeStructureForm
    from .models import TransportFeeStructure
    obj=get_object_or_404(TransportFeeStructure,pk=pk);form=TransportFeeStructureForm(request.POST or None,instance=obj)
    if request.method=="POST" and form.is_valid():form.save();return redirect("transport:transport_fee_dashboard")
    return render(request,"transport/transport_fee_structure_form.html",{"form":form,"title":"Edit Transport Fee Structure"})
@login_required
def unified_transport_fee_delete(request,pk):
    from .models import TransportFeeStructure
    obj=get_object_or_404(TransportFeeStructure,pk=pk)
    if request.method=="POST":obj.delete();return redirect("transport:transport_fee_dashboard")
    return render(request,"transport/transport_fee_confirm_delete.html",{"object":obj})
@login_required
def route_maps(request):
    from .models import Route
    return render(request,"transport/route_maps.html",{"routes":Route.objects.prefetch_related("stops").order_by("name")})
@login_required
def route_map_edit(request,pk):
    from .models import Route
    route=get_object_or_404(Route,pk=pk)
    if request.method=="POST":
        route.google_maps_url=(request.POST.get("google_maps_url") or "").strip();route.map_latitude=request.POST.get("map_latitude") or None;route.map_longitude=request.POST.get("map_longitude") or None;route.distance_km=request.POST.get("distance_km") or None;route.estimated_minutes=request.POST.get("estimated_minutes") or None;route.save(update_fields=["google_maps_url","map_latitude","map_longitude","distance_km","estimated_minutes"])
        for stop in route.stops.all():
            k=str(stop.pk);stop.google_maps_url=(request.POST.get("stop_url_"+k) or "").strip();stop.latitude=request.POST.get("stop_lat_"+k) or None;stop.longitude=request.POST.get("stop_lng_"+k) or None;stop.save(update_fields=["google_maps_url","latitude","longitude"])
        return redirect("transport:route_maps")
    return render(request,"transport/route_map_edit.html",{"route":route,"stops":route.stops.order_by("stop_order")})


# =============================================================
# ROUTE EXCEL TEMPLATE
# Provides Excel time cells and an Active/Inactive dropdown.
# =============================================================

@login_required
@role_permission_required("view_route", "transport")
def route_excel_template(request):
    from django.http import HttpResponse

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Routes"

    headers = [
        "name",
        "code",
        "description",
        "morning_departure",
        "afternoon_departure",
        "status",
    ]
    sheet.append(headers)

    # Styled header row.
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(
            fill_type="solid",
            fgColor="1F4E78",
        )
        cell.alignment = Alignment(horizontal="center")

    # Add blank rows for data entry.
    for _ in range(500):
        sheet.append(["", "", "", None, None, "ACTIVE"])

    # Time columns use actual Excel time formatting.
    for row_number in range(2, 502):
        for column in ("D", "E"):
            cell = sheet[f"{column}{row_number}"]
            cell.number_format = "hh:mm"

    # Excel dropdown for route status.
    status_validation = DataValidation(
        type="list",
        formula1='"ACTIVE,INACTIVE"',
        allow_blank=False,
    )
    status_validation.error = "Choose ACTIVE or INACTIVE from the dropdown."
    status_validation.errorTitle = "Invalid route status"
    status_validation.prompt = "Select ACTIVE or INACTIVE."
    status_validation.promptTitle = "Route status"
    status_validation.showErrorMessage = True
    status_validation.showInputMessage = True
    sheet.add_data_validation(status_validation)
    status_validation.add("F2:F501")

    # Dropdown of times in 15-minute intervals, covering the full day.
    from openpyxl.workbook.defined_name import DefinedName

    time_sheet = workbook.create_sheet("Time Choices")
    for minute_index in range(96):
        hour, minute = divmod(minute_index * 15, 60)
        time_sheet.cell(
            row=minute_index + 1,
            column=1,
            value=f"{hour:02d}:{minute:02d}",
        )
    time_sheet.sheet_state = "hidden"

    time_name = DefinedName(
        "RouteTimeChoices",
        attr_text="'Time Choices'!$A$1:$A$96",
    )
    try:
        workbook.defined_names.add(time_name)
    except AttributeError:
        workbook.defined_names["RouteTimeChoices"] = time_name

    for column in ("D", "E"):
        time_validation = DataValidation(
            type="list",
            formula1="=RouteTimeChoices",
            allow_blank=True,
        )
        time_validation.error = "Choose a time from the dropdown."
        time_validation.errorTitle = "Invalid departure time"
        time_validation.prompt = "Select a time in 15-minute intervals."
        time_validation.promptTitle = "Departure time"
        time_validation.showErrorMessage = True
        time_validation.showInputMessage = True
        sheet.add_data_validation(time_validation)
        time_validation.add(f"{column}2:{column}501")

    # Useful worksheet layout.
    widths = {
        "A": 28,
        "B": 18,
        "C": 42,
        "D": 22,
        "E": 23,
        "F": 18,
    }
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = "A1:F501"

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        'attachment; filename="route_import_template.xlsx"'
    )
    return response


# =============================================================
# ROUTE EXCEL IMPORT
# Accepts the workbook generated by route_excel_template.
# =============================================================

@login_required
@role_permission_required("add_route", "transport")
def route_excel_import(request):
    import io
    from datetime import datetime as dt_datetime, time as dt_time
    from zipfile import BadZipFile
    from openpyxl import load_workbook
    from openpyxl.utils.datetime import from_excel

    errors = []
    imported_count = None

    def parse_excel_time(value):
        if value is None or str(value).strip() == "":
            return None
        if isinstance(value, dt_datetime):
            return value.time().replace(second=0, microsecond=0)
        if isinstance(value, dt_time):
            return value.replace(second=0, microsecond=0)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            converted = from_excel(value)
            if isinstance(converted, dt_datetime):
                converted = converted.time()
            if isinstance(converted, dt_time):
                return converted.replace(second=0, microsecond=0)
            raise ValueError("Invalid Excel time value")

        text = str(value).strip()
        for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
            try:
                return dt_datetime.strptime(text, fmt).time()
            except ValueError:
                pass
        raise ValueError("Use a valid time, such as 07:30")

    if request.method == "POST":
        upload = request.FILES.get("excel_file")

        if not upload:
            errors.append("Choose an Excel (.xlsx) workbook to upload.")
        elif upload.size > 5 * 1024 * 1024:
            errors.append("The Excel file must be 5 MB or smaller.")
        elif not upload.name.lower().endswith(".xlsx"):
            errors.append("Upload an .xlsx workbook. CSV files use the CSV import option.")
        else:
            workbook = None
            try:
                workbook = load_workbook(
                    upload,
                    read_only=True,
                    data_only=True,
                )
                sheet = workbook.active
                first_row = next(
                    sheet.iter_rows(min_row=1, max_row=1, values_only=True),
                    None,
                )

                if not first_row:
                    errors.append("The Excel workbook is empty.")
                else:
                    headers = [
                        str(value or "").strip().lower()
                        for value in first_row
                    ]
                    required = list(ROUTE_CSV_FIELDS)
                    missing = [field for field in required if field not in headers]

                    if missing:
                        errors.append(
                            "Missing required Excel columns: " + ", ".join(missing)
                        )
                    elif len(headers) != len(set(headers)):
                        errors.append("The Excel workbook contains duplicate column names.")
                    else:
                        rows = []
                        seen_names = set()
                        seen_codes = set()
                        existing_names = set(
                            Route.objects.values_list("name", flat=True)
                        )
                        existing_codes = set(
                            Route.objects.values_list("code", flat=True)
                        )

                        for row_number, values in enumerate(
                            sheet.iter_rows(min_row=2, values_only=True),
                            start=2,
                        ):
                            if row_number > 5001:
                                errors.append(
                                    "The workbook exceeds the 5,000 data-row limit."
                                )
                                break

                            raw = dict(zip(headers, values))
                            if not any(
                                value is not None and str(value).strip()
                                for value in raw.values()
                            ):
                                continue

                            def cell_text(key):
                                value = raw.get(key)
                                return "" if value is None else str(value).strip()

                            name = cell_text("name")
                            code = cell_text("code")
                            description = cell_text("description")
                            status = cell_text("status").upper() or "ACTIVE"
                            row_errors = []

                            if not name:
                                row_errors.append("name is required")
                            elif len(name) > 100:
                                row_errors.append("name exceeds 100 characters")

                            if not code:
                                row_errors.append("code is required")
                            elif len(code) > 30:
                                row_errors.append("code exceeds 30 characters")

                            if name in existing_names or name in seen_names:
                                row_errors.append(f"duplicate route name: {name}")
                            if code in existing_codes or code in seen_codes:
                                row_errors.append(f"duplicate route code: {code}")

                            if status not in ("ACTIVE", "INACTIVE"):
                                row_errors.append(
                                    "status must be ACTIVE or INACTIVE"
                                )

                            parsed_times = []
                            for label in (
                                "morning_departure",
                                "afternoon_departure",
                            ):
                                try:
                                    parsed_times.append(
                                        parse_excel_time(raw.get(label))
                                    )
                                except (ValueError, TypeError, OverflowError):
                                    row_errors.append(
                                        f"{label} must be a valid time, e.g. 07:30"
                                    )
                                    parsed_times.append(None)

                            if row_errors:
                                errors.append(
                                    f"Row {row_number}: " + "; ".join(row_errors)
                                )
                            else:
                                seen_names.add(name)
                                seen_codes.add(code)
                                rows.append(Route(
                                    name=name,
                                    code=code,
                                    description=description,
                                    morning_departure=parsed_times[0],
                                    afternoon_departure=parsed_times[1],
                                    status=status,
                                ))

                        if not errors and not rows:
                            errors.append(
                                "The Excel workbook contains no route rows to import."
                            )

                        if not errors:
                            try:
                                with transaction.atomic():
                                    Route.objects.bulk_create(rows)
                                imported_count = len(rows)
                            except IntegrityError:
                                errors.append(
                                    "Import was cancelled because a route name or "
                                    "code conflicts with an existing record. "
                                    "No routes were imported; check the workbook and retry."
                                )

            except (BadZipFile, OSError, ValueError, KeyError) as exc:
                errors.append(
                    "Could not read this Excel workbook. Download a fresh template "
                    "and try again."
                )
            except Exception:
                errors.append(
                    "The workbook could not be processed. Check that it is a valid "
                    "Excel .xlsx file and try again."
                )
            finally:
                if workbook is not None:
                    workbook.close()

        if imported_count is not None:
            messages.success(
                request,
                f"Successfully imported {imported_count} route(s) from Excel.",
            )
            return redirect("transport:route_list")

    return render(request, "transport/route_csv_import.html", {
        "errors": errors,
        "csv_fields": ROUTE_CSV_FIELDS,
    })

