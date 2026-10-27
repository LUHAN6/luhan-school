from django.contrib import admin
from .models import (
    Vehicle, TransportStaff, TransportRoute, RouteStop, LearnerTransport,
    TransportTrip, VehicleInspection, BoardingEvent, MaintenanceRecord,
    TransportIncident, TransportCharge, TransportPayment, TransportNotificationLog,
    TransportAuditEvent
)

@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("registration_number","make_model","seating_capacity","status","insurance_expiry","inspection_expiry")
    list_filter = ("status","fuel_type")
    search_fields = ("registration_number","make_model")

@admin.register(TransportTrip)
class TransportTripAdmin(admin.ModelAdmin):
    list_display = ("service_date","route","direction","vehicle","driver","status")
    list_filter = ("service_date","direction","status")
    search_fields = ("route__name","vehicle__registration_number","driver__full_name")

for model in [TransportStaff, TransportRoute, RouteStop, LearnerTransport, VehicleInspection, BoardingEvent,
              MaintenanceRecord, TransportIncident, TransportCharge, TransportPayment,
              TransportNotificationLog, TransportAuditEvent]:
    admin.site.register(model)
