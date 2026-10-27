from django.urls import path
from . import views
from . import automatic_payment_sections
from . import automatic_method_router
from . import paybill_payment_views
from . import paybill_c2b_views
from . import paybill_c2b_admin

from . import bank_payment_views
from . import alternate_payment
from . import alternate_c2b
from . import online_payment_upgrade
from . import alternate_payment_settings_view
from . import alternate_payment_auto
from . import paybill_payment_views


app_name = "fees"


urlpatterns = [
    path("fee-structure/unified/export/pdf/", views.unified_fee_structure_pdf, name="unified_fee_structure_pdf"),
    path("fee-structure/unified/export/excel/", views.unified_fee_structure_excel, name="unified_fee_structure_excel"),
    path("fee-structure/unified/", views.unified_fee_structure, name="unified_fee_structure"),

    # ========================================================
    # AUTOMATIC PAYMENT SETTINGS
    # ========================================================

    path(
        "automatic-payment-settings/",
        automatic_payment_sections.automatic_payment_settings_home,
        name="automatic_payment_settings",
    ),

    path(
        "automatic-payment-settings/mpesa-online/",
        automatic_payment_sections.mpesa_online_settings,
        name="mpesa_online_settings",
    ),

    path(
        "automatic-payment-settings/mpesa-till/",
        automatic_payment_sections.mpesa_till_settings,
        name="mpesa_till_settings",
    ),

    path(
        "automatic-payment-settings/paybill/",
        automatic_payment_sections.mpesa_paybill_settings,
        name="mpesa_paybill_settings",
    ),

    path(
        "automatic-payment-settings/bank/",
        automatic_payment_sections.bank_settings,
        name="bank_settings",
    ),



    # ========================================================
    # AUTOMATIC PAYMENT ACTIVATION
    # ========================================================


    path(
        "paybill/c2b/validation/",
        paybill_c2b_views.c2b_validation,
        name="paybill_c2b_validation",
    ),
    path(
        "paybill/c2b/confirmation/",
        paybill_c2b_views.c2b_confirmation,
        name="paybill_c2b_confirmation",
    ),
    path(
        "paybill/c2b/register/",
        paybill_c2b_views.c2b_register_urls,
        name="paybill_c2b_register",
    ),
    path(
        "paybill/c2b/transactions/",
        paybill_c2b_views.c2b_transactions,
        name="paybill_c2b_transactions",
    ),

    path("alternate/automatic/bank/pay/", automatic_method_router.automatic_bank_route, name="automatic_bank_payment"),
    path("alternate/automatic/till/route/", automatic_method_router.automatic_till_route, name="automatic_till_route"),
    path("alternate/automatic/online/pay/", automatic_method_router.automatic_online_route, name="automatic_online_payment"),

    path(
        "online/mpesa/callback/",
        views.mpesa_callback,
        name="mpesa_callback"
    ),
    path("online/pay/", views.online_payment_page, name="online_payment"),
    path(
        "online/status/<int:payment_id>/",
        online_payment_upgrade.upgraded_online_payment_status,
        name="online_payment_status",
    ),
    path(
        "online/receipt/<int:payment_id>/",
        online_payment_upgrade.online_payment_receipt,
        name="online_payment_receipt",
    ),
    path(
        "online/receipt/<int:payment_id>/pdf/",
        online_payment_upgrade.online_payment_receipt_pdf,
        name="online_payment_receipt_pdf",
    ),

    path(
        "payments/",
        views.fee_payments_page,
        name="fee_payments_page"
    ),

    path(
        "fee-structure/",
        views.fee_structure_settings,
        name="fee_structure_settings"
    ),
    path(
        "configured-fee-items/",
        views.configured_fee_items,
        name="configured_fee_items"
    ),
    path(
        "fee-structure/<int:id>/edit/",
        views.edit_fee_structure,
        name="edit_fee_structure"
    ),


    path(
        "",
        views.fees_dashboard,
        name="dashboard"
    ),

    path(
        "receipts/",
        views.receipt_list,
        name="receipt_list"
    ),

    path(
        "payment-list/",
        views.payment_list,
        name="payment_list"
    ),

    path(
        "receipt/<int:payment_id>/",
        views.print_receipt,
        name="print_receipt"
    ),

    path(
        "invoice/<int:student_id>/",
        views.print_invoice,
        name="print_invoice"
    ),

    path(
        "statement/<int:student_id>/",
        views.print_statement,
        name="print_statement"
    ),

    path("online/status/<int:payment_id>/query/", online_payment_upgrade.online_payment_stk_query, name="online_payment_stk_query"),
    path(
        "alternate/automatic/",
        alternate_payment_auto.alternate_payment_auto,
        name="alternate_payment_auto",
    ),
    path(
        "alternate/automatic/method/",
        alternate_payment_auto.alternate_payment_auto_method,
        name="alternate_payment_auto_method",
    ),
    path(
        "alternate/gateway/",
        alternate_payment.alternate_payment_gateway,
        name="alternate_payment_gateway",
    ),

    path("alternate/", alternate_payment.alternate_payment, name="alternate_payment"),
    path(
        "alternate/payment-settings/",
        alternate_payment_settings_view.alternate_payment_settings,
        name="alternate_payment_settings"
    ),
    path(
        "alternate/automatic/till/pay/",
        alternate_c2b.alternate_till_payment,
        name="alternate_till_payment",
    ),
    path(
        "alternate/automatic/till/status/<int:intent_id>/",
        alternate_c2b.alternate_till_payment_status,
        name="alternate_till_payment_status",
    ),
    path("alternate/c2b/validation/", alternate_c2b.alternate_c2b_validation, name="alternate_c2b_validation"),
    path("alternate/c2b/confirmation/", alternate_c2b.alternate_c2b_confirmation, name="alternate_c2b_confirmation"),
    path("alternate/status/<int:payment_id>/", alternate_payment.alternate_payment_status, name="alternate_payment_status"),

    path("alternate/", alternate_payment.alternate_payment, name="alternate_payment"),
    path(
        "alternate/payment-settings/",
        alternate_payment_settings_view.alternate_payment_settings,
        name="alternate_payment_settings"
    ),
    path("alternate/instructions/<int:payment_id>/", alternate_payment.alternate_payment_instructions, name="alternate_payment_instructions"),
    path("alternate/status/<int:payment_id>/", alternate_payment.alternate_payment_status, name="alternate_payment_status"),
    path(
        "alternate/track/",
        alternate_payment.alternate_payment_track_request,
        name="alternate_payment_track",
    ),
    path("alternate/manage/", alternate_payment.alternate_payment_management, name="alternate_payment_management"),
    path("alternate/confirm/<int:payment_id>/", alternate_payment.alternate_payment_confirm, name="alternate_payment_confirm"),
    path("alternate/reject/<int:payment_id>/", alternate_payment.alternate_payment_reject, name="alternate_payment_reject"),

    path(
        "bank/pay/",
        bank_payment_views.bank_payment_page,
        name="bank_payment",
    ),
    path(
        "bank/verify/",
        bank_payment_views.bank_self_service_verify,
        name="bank_self_service_verify",
    ),
    path(
        "bank/test-connection/",
        bank_payment_views.bank_connection_test,
        name="bank_connection_test",
    ),
    path(
        "bank/transactions/",
        bank_payment_views.bank_transactions,
        name="bank_transactions",
    ),
    path(
        "bank/transactions/<int:transaction_id>/verify/",
        bank_payment_views.bank_transaction_verify,
        name="bank_transaction_verify",
    ),
    path(
        "bank/transactions/<int:transaction_id>/assign/",
        bank_payment_views.bank_transaction_assign,
        name="bank_transaction_assign",
    ),
    path(
        "bank/sync/",
        bank_payment_views.bank_sync_now,
        name="bank_sync_now",
    ),
    path(
        "bank/webhook/",
        bank_payment_views.bank_webhook,
        name="bank_webhook",
    ),
    path("alternate/automatic/paybill/pay/", paybill_payment_views.paybill_payment_page, name="automatic_paybill_payment"),

path(
    "paybill/admin/test/",
    paybill_c2b_admin.test_paybill_credentials,
    name="paybill_admin_test",
),
path(
    "paybill/admin/register/",
    paybill_c2b_admin.register_paybill_c2b,
    name="paybill_admin_register",
),
path(
    "paybill/admin/activate/",
    paybill_c2b_admin.activate_paybill,
    name="paybill_admin_activate",
),
]






