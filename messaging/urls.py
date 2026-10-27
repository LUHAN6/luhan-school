from django.urls import path
from .audience_views import audience_dashboard

from . import views
from . import bulk_views


app_name = "messaging"


urlpatterns = [

    # =========================================================
    # PORTAL MESSAGES
    # =========================================================

    path(
        "portal/",
        views.portal_messages,
        name="portal_messages",
    ),

    path(
        "portal/sent/",
        views.portal_sent_messages,
        name="portal_sent_messages",
    ),


    # =========================================================
    # MESSAGING DASHBOARD
    # =========================================================

    path(
        "",
        views.messaging_dashboard,
        name="dashboard",
    ),


    # =========================================================
    # COMPOSE MESSAGE
    # =========================================================

    path(
        "compose/",
        views.message_compose,
        name="compose",
    ),

    path(
        "compose/recipient-lookup/",
        views.compose_recipient_lookup,
        name="compose_recipient_lookup",
    ),


    # =========================================================
    # ADMIN MESSAGE APPROVALS
    # =========================================================

    path(
        "approvals/",
        views.pending_approvals,
        name="pending_approvals",
    ),

    path(
        "approvals/<int:message_id>/approve/",
        views.approve_message,
        name="approve_message",
    ),

    path(
        "approvals/<int:message_id>/reject/",
        views.reject_message,
        name="reject_message",
    ),


    # =========================================================
    # RECEIVED MESSAGE
    # =========================================================

    path(
        "message/<int:message_id>/",
        views.message_detail,
        name="message_detail",
    ),


    # =========================================================
    # REPLY TO MESSAGE
    # =========================================================

    path(
        "message/<int:message_id>/reply/",
        views.message_reply,
        name="message_reply",
    ),


    # =========================================================
    # SENT MESSAGE
    # =========================================================

    path(
        "sent/<int:message_id>/",
        views.sent_message_detail,
        name="sent_message_detail",
    ),


    # =========================================================
    # BULK SMS AND EMAIL CAMPAIGNS
    # =========================================================
    path("bulk/", bulk_views.dashboard, name="bulk_dashboard"),
    path("bulk/contacts/", bulk_views.contact_list, name="bulk_contacts"),
    path("bulk/contacts/sync/", bulk_views.contact_sync, name="bulk_contact_sync"),
    path("bulk/contacts/add/", bulk_views.contact_create, name="bulk_contact_add"),
    path("bulk/contacts/<int:pk>/edit/", bulk_views.contact_edit, name="bulk_contact_edit"),
    path("bulk/contacts/<int:pk>/delete/", bulk_views.contact_delete, name="bulk_contact_delete"),
    path("bulk/contacts/import/", bulk_views.contact_import, name="bulk_contact_import"),
    path("bulk/contacts/export/", bulk_views.contact_export, name="bulk_contact_export"),
    path("bulk/groups/", bulk_views.group_list, name="bulk_groups"),
    path("bulk/groups/add/", bulk_views.group_create, name="bulk_group_add"),
    path("bulk/campaigns/", bulk_views.campaign_list, name="bulk_campaigns"),
    path("bulk/campaigns/add/", bulk_views.campaign_create, name="bulk_campaign_add"),
    path("bulk/campaigns/<int:pk>/preview/", bulk_views.campaign_preview, name="bulk_campaign_preview"),
    path("bulk/campaigns/<int:pk>/", bulk_views.campaign_detail, name="bulk_campaign_detail"),
    path("bulk/campaigns/<int:pk>/send/", bulk_views.campaign_send, name="bulk_campaign_send"),
    path("bulk/campaigns/<int:pk>/retry/", bulk_views.campaign_retry, name="bulk_campaign_retry"),
    path("bulk/campaigns/<int:pk>/cancel/", bulk_views.campaign_cancel, name="bulk_campaign_cancel"),
    path("bulk/templates/", bulk_views.template_list, name="bulk_templates"),
    path("bulk/templates/add/", bulk_views.template_create, name="bulk_template_add"),
    path("bulk/logs/", bulk_views.logs_list, name="bulk_logs"),]

# Five-section messaging audience dashboard
urlpatterns += [path("audiences/", audience_dashboard, name="audiences")]

