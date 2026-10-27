from django.urls import path

from . import views


app_name = "transport"


urlpatterns = [
    path("route-maps/<int:pk>/edit/", views.route_map_edit, name="route_map_edit"),
    path("route-maps/", views.route_maps, name="route_maps"),

    # =====================================================
    # DASHBOARD
    # =====================================================

    path(
        "",
        views.transport_dashboard,
        name="dashboard",
    ),

    # =====================================================
    # VEHICLES
    # =====================================================

    path(
        "vehicles/",
        views.vehicle_list,
        name="vehicle_list",
    ),

    path(
        "vehicles/add/",
        views.vehicle_add,
        name="vehicle_add",
    ),

    path(
        "vehicles/<int:pk>/edit/",
        views.vehicle_edit,
        name="vehicle_edit",
    ),

    path(
        "vehicles/<int:pk>/delete/",
        views.vehicle_delete,
        name="vehicle_delete",
    ),

    # =====================================================
    # DRIVERS
    # =====================================================

    path(
        "drivers/",
        views.driver_list,
        name="driver_list",
    ),

    path(
        "drivers/add/",
        views.driver_add,
        name="driver_add",
    ),

    path(
        "drivers/<int:pk>/edit/",
        views.driver_edit,
        name="driver_edit",
    ),

    path(
        "drivers/<int:pk>/delete/",
        views.driver_delete,
        name="driver_delete",
    ),

    # =====================================================
    # ROUTES
    # =====================================================

    path(
        "routes/",
        views.route_list,
        name="route_list",
    ),

    path(
        "routes/add/",
        views.route_add,
        name="route_add",
    ),

    path(
        "routes/csv/template/",
        views.route_csv_template,
        name="route_csv_template",
    ),
    path(
        "routes/excel/template/",
        views.route_excel_template,
        name="route_excel_template",
    ),
    path(
        "routes/excel/import/",
        views.route_excel_import,
        name="route_excel_import",
    ),
    path(
        "routes/csv/export/",
        views.route_csv_export,
        name="route_csv_export",
    ),
    path(
        "routes/export/excel/",
        views.route_excel_export,
        name="route_excel_export",
    ),
    path(
        "routes/export/excel/",
        views.route_excel_export,
        name="route_excel_export",
    ),
    path(
        "routes/csv/import/",
        views.route_csv_import,
        name="route_csv_import",
    ),

    path(
        "routes/<int:pk>/edit/",
        views.route_edit,
        name="route_edit",
    ),

    path(
        "routes/<int:pk>/delete/",
        views.route_delete,
        name="route_delete",
    ),

    # =====================================================
    # ROUTE STOPS
    # =====================================================

    path(
        "route-stops/",
        views.routestop_list,
        name="routestop_list",
    ),

    path(
        "route-stops/add/",
        views.routestop_add,
        name="routestop_add",
    ),

    path(
        "route-stops/<int:pk>/edit/",
        views.routestop_edit,
        name="routestop_edit",
    ),

    path(
        "route-stops/<int:pk>/delete/",
        views.routestop_delete,
        name="routestop_delete",
    ),

    # =====================================================
    # STUDENT TRANSPORT ASSIGNMENTS
    # =====================================================

    path(
        "student-assignments/",
        views.student_assignment_list,
        name="student_assignment_list",
    ),

    path(
        "student-assignments/add/",
        views.student_assignment_add,
        name="student_assignment_add",
    ),

    path(
        "student-assignments/<int:pk>/edit/",
        views.student_assignment_edit,
        name="student_assignment_edit",
    ),

    path(
        "student-assignments/<int:pk>/delete/",
        views.student_assignment_delete,
        name="student_assignment_delete",
    ),

    # =====================================================
    # VEHICLE / DRIVER ASSIGNMENTS
    # =====================================================

    path(
        "assignments/",
        views.assignment_list,
        name="assignment_list",
    ),

    path(
        "assignments/add/",
        views.assignment_add,
        name="assignment_add",
    ),

    path(
        "assignments/<int:pk>/edit/",
        views.assignment_edit,
        name="assignment_edit",
    ),

    path(
        "assignments/<int:pk>/delete/",
        views.assignment_delete,
        name="assignment_delete",
    ),

    # =====================================================
    # TRIPS
    # =====================================================

    path(
        "trips/",
        views.trip_list,
        name="trip_list",
    ),

    path(
        "trips/add/",
        views.trip_add,
        name="trip_add",
    ),

    path(
        "trips/<int:pk>/edit/",
        views.trip_edit,
        name="trip_edit",
    ),

    path(
        "trips/<int:pk>/delete/",
        views.trip_delete,
        name="trip_delete",
    ),

    # =====================================================
    # MAINTENANCE
    # =====================================================

    path(
        "maintenance/",
        views.maintenance_list,
        name="maintenance_list",
    ),

    path(
        "maintenance/add/",
        views.maintenance_add,
        name="maintenance_add",
    ),

    path(
        "maintenance/<int:pk>/edit/",
        views.maintenance_edit,
        name="maintenance_edit",
    ),

    path(
        "maintenance/<int:pk>/delete/",
        views.maintenance_delete,
        name="maintenance_delete",
    ),

    # =====================================================
    # FUEL
    # =====================================================

    path(
        "fuel/",
        views.fuel_list,
        name="fuel_list",
    ),

    path(
        "fuel/add/",
        views.fuel_add,
        name="fuel_add",
    ),

    path(
        "fuel/<int:pk>/edit/",
        views.fuel_edit,
        name="fuel_edit",
    ),

    path(
        "fuel/<int:pk>/delete/",
        views.fuel_delete,
        name="fuel_delete",
    ),
    path("fees/", views.unified_transport_fee_dashboard, name="transport_fee_dashboard"),
    path("fees/structures/add/", views.unified_transport_fee_add, name="transport_fee_structure_add"),
    path("fees/structures/<int:pk>/edit/", views.unified_transport_fee_edit, name="transport_fee_structure_edit"),
    path("fees/structures/<int:pk>/delete/", views.unified_transport_fee_delete, name="transport_fee_structure_delete"),
    path("fees/generate/", views.transport_fee_generate, name="transport_fee_generate"),
]
