import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.urls import reverse

from messaging.bulk_models import Campaign, MessageLog, Contact
from messaging.bulk_views import _mask_destination
from messaging.bulk_services import (
    render_template,
    _send_sms,
    _send_email,
    send_campaign,
    prepare_and_send,
)
from hr_payroll.models import Employee
from messaging.bulk_sync import sync_erp_contacts, _contact_for


class BulkMessagingSafetyTests(SimpleTestCase):
    def setUp(self):
        self._live_gate_patch = patch.dict(
            os.environ, {"MESSAGING_LIVE_SEND_ENABLED": "true"}
        )
        self._live_gate_patch.start()
        self.addCleanup(self._live_gate_patch.stop)
        self.contact = SimpleNamespace(
            first_name="Amina",
            last_name="Otieno",
            full_name="Amina Otieno",
        )


    def test_send_campaign_is_noop_when_live_sending_disabled(self):
        campaign = SimpleNamespace(
            status=Campaign.Status.DRAFT,
            started_at=None,
            completed_at=None,
            save=Mock(),
            logs=Mock(),
        )

        with patch.dict(os.environ, {"MESSAGING_LIVE_SEND_ENABLED": "false"}):
            result = send_campaign(campaign)

        self.assertIs(result, campaign)
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)
        self.assertIsNone(campaign.started_at)
        self.assertIsNone(campaign.completed_at)
        campaign.save.assert_not_called()
        campaign.logs.filter.assert_not_called()

    def test_prepare_and_send_is_noop_when_live_sending_disabled(self):
        campaign = SimpleNamespace(
            status=Campaign.Status.DRAFT,
            save=Mock(),
            logs=Mock(),
        )

        with patch.dict(os.environ, {"MESSAGING_LIVE_SEND_ENABLED": "false"}):
            result = prepare_and_send(campaign)

        self.assertIs(result, campaign)
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)
        campaign.save.assert_not_called()
        campaign.logs.filter.assert_not_called()

    def test_personalization_replaces_known_placeholders(self):
        with patch.dict(os.environ, {"SCHOOL_NAME": "Luhan School"}):
            result = render_template(
                "Hello {{ first_name }} {{ last_name }} "
                "({{ full_name }}), welcome to {{ school_name }}. "
                "Unknown: {{ unknown_field }}",
                self.contact,
            )

        self.assertEqual(
            result,
            "Hello Amina Otieno (Amina Otieno), welcome to Luhan School. "
            "Unknown: {{ unknown_field }}",
        )

    def test_console_sms_is_simulation_not_success(self):
        with patch.dict(os.environ, {"MESSAGING_SMS_BACKEND": "console"}):
            result = _send_sms("+254700000000", "Test only")

        self.assertTrue(result["simulated"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["id"], "")
        self.assertIn("SIMULATION ONLY", result["error"])

    def test_console_email_is_simulation_not_success(self):
        with patch.dict(os.environ, {"MESSAGING_EMAIL_BACKEND": "console"}):
            result = _send_email(
                "test@example.invalid", "Test only", "Test only"
            )

        self.assertTrue(result["simulated"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["id"], "")
        self.assertIn("SIMULATION ONLY", result["error"])

    def test_simulated_sms_log_is_skipped_not_sent(self):
        log = SimpleNamespace(
            channel=MessageLog.Channel.SMS,
            destination="+254700000000",
            rendered_message="Test only",
            subject="",
            status=MessageLog.Status.PENDING,
            attempts=0,
            provider_message_id="",
            sent_at=None,
            error_message="",
            save=Mock(),
        )

        logs = Mock()

        def filtered_logs(**kwargs):
            status = kwargs.get("status")
            queryset = Mock()
            queryset.count.return_value = (
                1 if status == MessageLog.Status.SKIPPED else 0
            )
            queryset.exists.return_value = False
            if status == MessageLog.Status.PENDING:
                queryset.select_related.return_value.iterator.return_value = iter([log])
            else:
                queryset.select_related.return_value.iterator.return_value = iter([])
            return queryset

        logs.filter.side_effect = filtered_logs
        logs.count.return_value = 1

        campaign = SimpleNamespace(
            status=Campaign.Status.QUEUED,
            started_at=None,
            completed_at=None,
            sent_count=0,
            failed_count=0,
            skipped_count=0,
            total_recipients=1,
            logs=logs,
            save=Mock(),
        )

        with patch(
            "messaging.bulk_services._send_sms",
            return_value={
                "ok": False,
                "simulated": True,
                "id": "",
                "error": "SIMULATION ONLY: no SMS was sent.",
            },
        ):
            send_campaign(campaign)

        self.assertEqual(log.status, MessageLog.Status.SKIPPED)
        self.assertEqual(campaign.sent_count, 0)
        self.assertEqual(campaign.failed_count, 0)
        self.assertEqual(campaign.skipped_count, 1)
        self.assertEqual(campaign.status, Campaign.Status.SIMULATED)
        self.assertEqual(log.provider_message_id, "")
        self.assertIsNone(log.sent_at)
        log.save.assert_called_once()

    def test_progress_includes_skipped_but_not_as_sent(self):
        campaign = Campaign(
            name="Simulation test",
            channel=Campaign.Channel.SMS,
            message="Test",
            total_recipients=4,
            sent_count=1,
            failed_count=1,
            skipped_count=1,
        )
        self.assertEqual(campaign.progress_percent, 75)
        self.assertEqual(campaign.sent_count, 1)


class BulkMessagingRegressionTests(SimpleTestCase):
    def setUp(self):
        super().setUp()
        self._live_gate_patch = patch.dict(
            os.environ, {"MESSAGING_LIVE_SEND_ENABLED": "true"}
        )
        self._live_gate_patch.start()
        self.addCleanup(self._live_gate_patch.stop)

    def _make_campaign_and_log(self, contact):
        log = SimpleNamespace(
            channel=MessageLog.Channel.SMS,
            destination="+254700000000",
            rendered_message="Test only",
            subject="",
            status=MessageLog.Status.PENDING,
            attempts=0,
            provider_message_id="",
            sent_at=None,
            error_message="",
            contact=contact,
            contact_id=None,
            save=Mock(),
        )

        logs = Mock()

        def filtered_logs(**kwargs):
            status = kwargs.get("status")
            queryset = Mock()
            queryset.count.return_value = (
                1 if status == MessageLog.Status.SKIPPED else 0
            )
            queryset.exists.return_value = False

            if status == MessageLog.Status.PENDING:
                queryset.select_related.return_value.iterator.return_value = iter([log])
            else:
                queryset.select_related.return_value.iterator.return_value = iter([])

            return queryset

        logs.filter.side_effect = filtered_logs
        logs.count.return_value = 1

        campaign = SimpleNamespace(
            status=Campaign.Status.QUEUED,
            started_at=None,
            completed_at=None,
            sent_count=0,
            failed_count=0,
            skipped_count=0,
            total_recipients=1,
            logs=logs,
            save=Mock(),
        )
        return campaign, log

    def test_opted_out_contact_is_skipped_before_sms(self):
        from messaging.bulk_services import send_campaign

        contact = SimpleNamespace(
            is_active=True,
            opted_out=True,
            sms_consent=True,
            email_consent=False,
            phone="+254700000000",
            email="",
        )
        campaign, log = self._make_campaign_and_log(contact)

        with patch("messaging.bulk_services._send_sms") as send_sms:
            send_campaign(campaign)

        send_sms.assert_not_called()
        self.assertEqual(log.status, MessageLog.Status.SKIPPED)
        self.assertIn("opted out", log.error_message.lower())
        self.assertEqual(log.attempts, 0)

    def test_revoked_sms_consent_is_skipped_before_send(self):
        from messaging.bulk_services import send_campaign

        contact = SimpleNamespace(
            is_active=True,
            opted_out=False,
            sms_consent=False,
            email_consent=False,
            phone="+254700000000",
            email="",
        )
        campaign, log = self._make_campaign_and_log(contact)

        with patch("messaging.bulk_services._send_sms") as send_sms:
            send_campaign(campaign)

        send_sms.assert_not_called()
        self.assertEqual(log.status, MessageLog.Status.SKIPPED)
        self.assertIn("consent", log.error_message.lower())
        self.assertEqual(log.attempts, 0)

    def test_inactive_contact_is_skipped_before_send(self):
        from messaging.bulk_services import send_campaign

        contact = SimpleNamespace(
            is_active=False,
            opted_out=False,
            sms_consent=True,
            email_consent=False,
            phone="+254700000000",
            email="",
        )
        campaign, log = self._make_campaign_and_log(contact)

        with patch("messaging.bulk_services._send_sms") as send_sms:
            send_campaign(campaign)

        send_sms.assert_not_called()
        self.assertEqual(log.status, MessageLog.Status.SKIPPED)
        self.assertIn("inactive", log.error_message.lower())

    def test_live_sms_is_blocked_when_gate_is_off(self):
        from messaging.bulk_services import _send_sms

        with patch.dict(
            os.environ,
            {
                "MESSAGING_SMS_BACKEND": "africastalking",
                "MESSAGING_LIVE_SEND_ENABLED": "false",
            },
            clear=False,
        ):
            result = _send_sms("+254700000000", "Test only")

        self.assertFalse(result["ok"])
        self.assertTrue(result.get("blocked"))
        self.assertIn("LIVE SENDING DISABLED", result["error"])

    def test_live_email_is_blocked_when_gate_is_off(self):
        from messaging.bulk_services import _send_email

        with patch.dict(
            os.environ,
            {
                "MESSAGING_EMAIL_BACKEND": "django",
                "MESSAGING_LIVE_SEND_ENABLED": "false",
            },
            clear=False,
        ):
            with patch("messaging.bulk_services.send_mail") as mail:
                result = _send_email(
                    "test@example.invalid", "Test only", "Test only"
                )

        mail.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertTrue(result.get("blocked"))

    def test_existing_campaign_logs_are_not_deleted_during_preparation(self):
        from messaging.bulk_services import prepare_and_send

        logs = Mock()
        logs.exists.return_value = True
        logs.count.return_value = 1

        campaign = SimpleNamespace(
            status=Campaign.Status.DRAFT,
            total_recipients=0,
            logs=logs,
            save=Mock(),
        )

        with patch("messaging.bulk_services.create_logs") as create:
            with patch(
                "messaging.bulk_services.send_campaign",
                return_value=campaign,
            ):
                prepare_and_send(campaign)

        create.assert_not_called()
        logs.all.assert_not_called()
        self.assertEqual(campaign.total_recipients, 1)

class CampaignPreviewPrivacyTests(SimpleTestCase):
    def test_sms_destination_is_masked(self):
        self.assertEqual(
            _mask_destination("sms", "+254700123456"),
            "????3456",
        )

    def test_email_destination_masks_local_part(self):
        self.assertEqual(
            _mask_destination("email", "amina.otieno@example.com"),
            "am***@example.com",
        )

    def test_empty_destination_has_no_personal_data(self):
        self.assertEqual(_mask_destination("sms", ""), "?")
        self.assertEqual(_mask_destination("email", None), "?")



class CampaignWorkflowDatabaseTests(TestCase):
    """Database-backed workflow tests; delivery services are mocked."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="messaging-workflow-test",
            password="test-only-password",
            is_staff=True,
        )
        self.client.force_login(self.user)

    def make_campaign(self, **overrides):
        values = {
            "name": "Workflow safety test",
            "channel": Campaign.Channel.SMS,
            "message": "Test message only",
            "all_contacts": True,
            "status": Campaign.Status.DRAFT,
            "created_by": self.user,
        }
        values.update(overrides)
        return Campaign.objects.create(**values)


    def test_disabled_gate_blocks_send_retry_and_schedule_posts(self):
        with patch.dict(os.environ, {"MESSAGING_LIVE_SEND_ENABLED": "false"}):
            with patch("messaging.bulk_views.prepare_and_send") as dispatch:
                with patch("messaging.bulk_views.send_campaign") as retry:
                    for action in ("send", "retry_failed", "schedule"):
                        campaign = self.make_campaign()
                        if action == "retry_failed":
                            campaign.failed_count = 1
                            campaign.save(update_fields=["failed_count"])

                        before_status = campaign.status
                        before_scheduled_at = campaign.scheduled_at
                        response = self.client.post(
                            reverse(
                                "messaging:bulk_campaign_preview",
                                args=[campaign.pk],
                            ),
                            {"action": action},
                        )

                        self.assertEqual(response.status_code, 302)
                        campaign.refresh_from_db()
                        self.assertEqual(campaign.status, before_status)
                        self.assertEqual(campaign.scheduled_at, before_scheduled_at)

                    dispatch.assert_not_called()
                    retry.assert_not_called()

    def test_create_saves_draft_without_dispatching(self):
        with patch("messaging.bulk_views.prepare_and_send") as dispatch:
            response = self.client.post(
                reverse("messaging:bulk_campaign_add"),
                {
                    "name": "New draft test",
                    "channel": "sms",
                    "message": "Test message only",
                    "all_contacts": "on",
                    "subject": "",
                    "notes": "",
                },
            )

        self.assertEqual(response.status_code, 302)
        campaign = Campaign.objects.get(name="New draft test")
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)
        self.assertRedirects(
            response,
            reverse("messaging:bulk_campaign_preview", args=[campaign.pk]),
            fetch_redirect_response=False,
        )
        dispatch.assert_not_called()
        self.assertEqual(MessageLog.objects.filter(campaign=campaign).count(), 0)

    def test_preview_get_masks_destination_and_does_not_dispatch(self):
        campaign = self.make_campaign()
        Contact.objects.create(
            first_name="Amina",
            last_name="Otieno",
            phone="+254700123456",
            sms_consent=True,
            email_consent=False,
            is_active=True,
            opted_out=False,
        )

        with (
            patch("messaging.bulk_views.prepare_and_send") as dispatch,
            patch("messaging.bulk_views.send_campaign") as retry,
        ):
            response = self.client.get(
                reverse("messaging:bulk_campaign_preview", args=[campaign.pk])
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3456")
        self.assertNotContains(response, "+254700123456")
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)
        self.assertEqual(MessageLog.objects.filter(campaign=campaign).count(), 0)
        dispatch.assert_not_called()
        retry.assert_not_called()

    def test_legacy_send_route_cannot_dispatch(self):
        campaign = self.make_campaign()

        with patch("messaging.bulk_views.prepare_and_send") as dispatch:
            response = self.client.post(
                reverse("messaging:bulk_campaign_send", args=[campaign.pk])
            )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("messaging:bulk_campaign_preview", args=[campaign.pk]),
            fetch_redirect_response=False,
        )
        dispatch.assert_not_called()
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)
        self.assertEqual(MessageLog.objects.filter(campaign=campaign).count(), 0)

    def test_legacy_retry_route_cannot_retry_directly(self):
        campaign = self.make_campaign(failed_count=1)

        with patch("messaging.bulk_views.send_campaign") as retry:
            response = self.client.post(
                reverse("messaging:bulk_campaign_retry", args=[campaign.pk])
            )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("messaging:bulk_campaign_preview", args=[campaign.pk]),
            fetch_redirect_response=False,
        )
        retry.assert_not_called()
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)
        self.assertEqual(MessageLog.objects.filter(campaign=campaign).count(), 0)

class ContactCSVConsentRegressionTests(TestCase):
    """CSV imports must preserve consent unless a value is explicit."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="contact-csv-consent-test",
            password="test-only-password",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.url = reverse("messaging:bulk_contact_import")

    def import_csv(self, contents):
        upload = SimpleUploadedFile(
            "contacts.csv",
            contents.encode("utf-8"),
            content_type="text/csv",
        )
        return self.client.post(self.url, {"file": upload})

    def test_missing_consent_columns_preserve_existing_consent(self):
        contact = Contact.objects.create(
            first_name="Amina",
            last_name="Otieno",
            phone="+254700123456",
            email="amina.csv-test@example.invalid",
            sms_consent=True,
            email_consent=True,
        )

        response = self.import_csv(
            "first_name,last_name,phone,email\n"
            "Amina,Otieno,+254700123456,amina.csv-test@example.invalid\n"
        )

        self.assertEqual(response.status_code, 302)
        contact.refresh_from_db()
        self.assertTrue(contact.sms_consent)
        self.assertTrue(contact.email_consent)

    def test_new_contact_without_consent_columns_defaults_to_no_consent(self):
        response = self.import_csv(
            "first_name,last_name,phone,email\n"
            "Brian,Test,+254700987654,brian.csv-test@example.invalid\n"
        )

        self.assertEqual(response.status_code, 302)
        contact = Contact.objects.get(
            email="brian.csv-test@example.invalid"
        )
        self.assertFalse(contact.sms_consent)
        self.assertFalse(contact.email_consent)

    def test_explicit_consent_values_are_imported(self):
        response = self.import_csv(
            "first_name,last_name,phone,email,sms_consent,email_consent\n"
            "Carol,Test,+254700987655,carol.csv-test@example.invalid,yes,no\n"
        )

        self.assertEqual(response.status_code, 302)
        contact = Contact.objects.get(
            email="carol.csv-test@example.invalid"
        )
        self.assertTrue(contact.sms_consent)
        self.assertFalse(contact.email_consent)

    def test_blank_consent_values_preserve_existing_consent(self):
        contact = Contact.objects.create(
            first_name="David",
            phone="+254700987656",
            email="david.csv-test@example.invalid",
            sms_consent=True,
            email_consent=True,
        )

        response = self.import_csv(
            "first_name,phone,email,sms_consent,email_consent\n"
            "David,+254700987656,david.csv-test@example.invalid,,\n"
        )

        self.assertEqual(response.status_code, 302)
        contact.refresh_from_db()
        self.assertTrue(contact.sms_consent)
        self.assertTrue(contact.email_consent)



class StaffContactSyncRegressionTests(TestCase):
    def make_employee(self, number="REG-STAFF-001", **kwargs):
        values = {
            "employee_number": number,
            "first_name": "Amina",
            "last_name": "Otieno",
            "phone": "0712345678",
            "email": "amina@example.test",
            "employment_status": "ACTIVE",
            "is_active": True,
        }
        values.update(kwargs)
        return Employee.objects.create(**values)

    def staff_contact(self, number):
        return Contact.objects.get(
            source=Contact.Source.ERP,
            external_id=f"employee:{number}",
        )

    def test_repeated_sync_does_not_duplicate_staff_contacts(self):
        self.make_employee()
        first_result = sync_erp_contacts()
        second_result = sync_erp_contacts()

        self.assertEqual(
            Contact.objects.filter(
                source=Contact.Source.ERP,
                external_id="employee:REG-STAFF-001",
            ).count(),
            1,
        )
        self.assertEqual(first_result["staff_created"], 1)
        self.assertEqual(second_result["staff_created"], 0)
        self.assertEqual(second_result["staff_total"], 1)

    def test_sync_updates_details_without_overwriting_consent_or_opt_out(self):
        employee = self.make_employee()
        sync_erp_contacts()

        contact = self.staff_contact(employee.employee_number)
        contact.sms_consent = True
        contact.email_consent = True
        contact.opted_out = True
        contact.save(
            update_fields=[
                "sms_consent",
                "email_consent",
                "opted_out",
                "updated_at",
            ]
        )

        employee.first_name = "Amina-Marie"
        employee.phone = "0798765432"
        employee.email = "updated@example.test"
        employee.save()

        sync_erp_contacts()
        contact.refresh_from_db()

        self.assertEqual(contact.first_name, "Amina-Marie")
        self.assertEqual(contact.phone, "0798765432")
        self.assertEqual(contact.email, "updated@example.test")
        self.assertEqual(contact.audience, Contact.Audience.STAFF)
        self.assertTrue(contact.sms_consent)
        self.assertTrue(contact.email_consent)
        self.assertTrue(contact.opted_out)

    def test_inactive_employee_is_not_eligible_for_staff_campaign(self):
        employee = self.make_employee()
        sync_erp_contacts()

        employee.employment_status = "TERMINATED"
        employee.save()
        sync_erp_contacts()

        contact = self.staff_contact(employee.employee_number)
        self.assertFalse(contact.is_active)

        campaign = SimpleNamespace(
            audience=Campaign.Audience.STAFF,
            individual_contact_id=None,
            all_contacts=True,
        )
        self.assertFalse(
            __import__(
                "messaging.bulk_services",
                fromlist=["eligible_contacts"],
            ).eligible_contacts(campaign).filter(pk=contact.pk).exists()
        )

    def test_parent_matching_does_not_reuse_staff_contact(self):
        Contact.objects.create(
            external_id="employee:REG-STAFF-002",
            first_name="Brian",
            last_name="Otieno",
            phone="0700111222",
            audience=Contact.Audience.STAFF,
            source=Contact.Source.ERP,
            is_active=True,
        )

        parent_contact, created = _contact_for(
            name="Brian Otieno",
            phone="0700111222",
            email="brian.parent@example.test",
            external_id="student-parent:REG-PARENT-002",
        )

        self.assertTrue(created)
        self.assertNotEqual(
            parent_contact.external_id,
            "employee:REG-STAFF-002",
        )
        self.assertEqual(parent_contact.audience, Contact.Audience.UNCLASSIFIED)
        self.assertEqual(
            Contact.objects.filter(
                phone="0700111222",
                audience=Contact.Audience.STAFF,
            ).count(),
            1,
        )
