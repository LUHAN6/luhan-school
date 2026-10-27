from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from .models import DisciplineCase, DisciplineCategory, DisciplineMeeting, DisciplineStatement, DisciplineAppeal
from students.models import Student
from parents.models import Parent
from django.utils import timezone

class DisciplineSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="discipline-staff", password="test-password-123")
        self.case = DisciplineCase.objects.create(student_name="Test Student", description="Test incident", reporter=self.user)
    def test_case_reference_generated(self):
        self.assertTrue(self.case.case_number.startswith("DISC-"))
    def test_login_required_dashboard(self):
        response = self.client.get(reverse("discipline:dashboard"))
        self.assertEqual(response.status_code, 302)
    def test_reporter_can_view_own_case(self):
        self.client.login(username="discipline-staff", password="test-password-123")
        response = self.client.get(reverse("discipline:case_detail", args=[self.case.pk]))
        self.assertEqual(response.status_code, 200)
    def test_parent_can_only_view_cases_for_linked_children(self):
        parent_user = get_user_model().objects.create_user(username="discipline-parent", password="test-password-123")
        student = Student.objects.create(
            first_name="Linked", last_name="Learner", gender="Female",
            date_of_birth="2014-01-01", class_name="Grade 7", stream="A",
            parent_name="Parent", parent_phone="0700000000",
        )
        Parent.objects.create(user=parent_user, full_name="Parent", phone="0700000000").children.add(student)
        linked_case = DisciplineCase.objects.create(student=student, student_name="Linked Learner", description="Linked case")
        self.client.login(username="discipline-parent", password="test-password-123")
        response = self.client.get(reverse("discipline:case_detail", args=[linked_case.pk]))
        self.assertEqual(response.status_code, 200)

    def test_case_status_change_rejects_get(self):
        manager = get_user_model().objects.create_user(username="discipline-manager", password="test-password-123", is_staff=True)
        self.client.login(username="discipline-manager", password="test-password-123")
        response = self.client.get(reverse("discipline:case_status", args=[self.case.pk, "closed"]))
        self.assertEqual(response.status_code, 405)

    def test_unrelated_user_cannot_view_case(self):
        get_user_model().objects.create_user(username="unrelated-user", password="test-password-123")
        self.client.login(username="unrelated-user", password="test-password-123")
        response = self.client.get(reverse("discipline:case_detail", args=[self.case.pk]))
        self.assertEqual(response.status_code, 403)

    def test_response_role_cannot_be_spoofed_by_post_data(self):
        self.client.login(username="discipline-staff", password="test-password-123")
        response = self.client.post(
            reverse("discipline:submit_response", args=[self.case.pk]),
            {"response": "My factual response", "response_role": "parent"},
        )
        self.assertEqual(response.status_code, 302)
        statement = self.case.statements.get()
        self.assertEqual(statement.statement_type, "staff")
        self.assertEqual(statement.body, "My factual response")

    def test_appeal_identity_and_role_are_server_controlled(self):
        self.client.login(username="discipline-staff", password="test-password-123")
        response = self.client.post(
            reverse("discipline:submit_appeal", args=[self.case.pk]),
            {
                "grounds": "I request a review.",
                "requested_by_name": "Forged Parent",
                "requester_role": "parent",
            },
        )
        self.assertEqual(response.status_code, 302)
        appeal = self.case.appeals.get()
        self.assertEqual(appeal.requester_role, "staff")
        self.assertEqual(appeal.requested_by_name, "discipline-staff")
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, "appeal")

    def test_case_status_closing_and_reopening_manage_closed_timestamp(self):
        manager = get_user_model().objects.create_user(
            username="discipline-status-manager",
            password="test-password-123",
            is_staff=True,
        )
        self.client.login(username="discipline-status-manager", password="test-password-123")
        close_response = self.client.post(
            reverse("discipline:case_status", args=[self.case.pk, "closed"])
        )
        self.assertEqual(close_response.status_code, 302)
        self.case.refresh_from_db()
        self.assertIsNotNone(self.case.closed_at)

        reopen_response = self.client.post(
            reverse("discipline:case_status", args=[self.case.pk, "reopened"])
        )
        self.assertEqual(reopen_response.status_code, 302)
        self.case.refresh_from_db()
        self.assertIsNone(self.case.closed_at)
    def test_parent_does_not_see_internal_meetings_or_other_users_statements(self):
        parent_user = get_user_model().objects.create_user(username="privacy-parent", password="test-password-123")
        student = Student.objects.create(
            first_name="Private", last_name="Learner", gender="Female",
            date_of_birth="2014-01-01", class_name="Grade 7", stream="A",
            parent_name="Parent", parent_phone="0700000000",
        )
        Parent.objects.create(user=parent_user, full_name="Parent", phone="0700000000").children.add(student)
        case = DisciplineCase.objects.create(student=student, student_name="Private Learner", description="Case summary")
        DisciplineMeeting.objects.create(
            case=case, title="CONFIDENTIAL STAFF DELIBERATION",
            scheduled_at=timezone.now(), created_by=self.user,
        )
        DisciplineStatement.objects.create(
            case=case, author=self.user, author_name="Officer",
            statement_type="staff", body="CONFIDENTIAL WITNESS DETAILS", confidential=True,
        )
        self.client.login(username="privacy-parent", password="test-password-123")
        response = self.client.get(reverse("discipline:case_detail", args=[case.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "CONFIDENTIAL STAFF DELIBERATION")
        self.assertNotContains(response, "CONFIDENTIAL WITNESS DETAILS")

    def test_manager_can_review_appeal_and_review_is_audited(self):
        manager = get_user_model().objects.create_user(
            username="appeal-review-manager", password="test-password-123", is_staff=True,
        )
        appeal = DisciplineAppeal.objects.create(
            case=self.case, requested_by_name="discipline-staff",
            requester_role="staff", grounds="Please review this decision.",
        )
        self.client.login(username="appeal-review-manager", password="test-password-123")
        response = self.client.post(
            reverse("discipline:review_appeal", args=[self.case.pk, appeal.pk]),
            {"status": "upheld", "review_outcome": "The original decision is upheld."},
        )
        self.assertEqual(response.status_code, 302)
        appeal.refresh_from_db()
        self.assertEqual(appeal.status, "upheld")
        self.assertEqual(appeal.reviewed_by, manager)
        self.assertIsNotNone(appeal.reviewed_at)
        self.assertTrue(self.case.audit_logs.filter(action="appeal_reviewed").exists())


class DisciplineEvidenceDownloadSecurityTests(TestCase):
    def setUp(self):
        from django.core.files.base import ContentFile
        from discipline.models import DisciplineIncidentReport
        from discipline.storage import PrivateDisciplineEvidenceStorage

        User = get_user_model()
        self.manager = User.objects.create_user(
            username="evidence-manager",
            password="test-password-123",
            is_staff=True,
        )
        self.ordinary_user = User.objects.create_user(
            username="evidence-ordinary",
            password="test-password-123",
        )
        self.case = DisciplineCase.objects.create(
            student_name="Evidence Test Student",
            description="Evidence download permission test",
            reporter=self.manager,
        )
        self.report = DisciplineIncidentReport.objects.create(
            case=self.case,
            submitted_by=self.manager,
            factual_account="Test evidence report",
        )
        self.storage = PrivateDisciplineEvidenceStorage()
        self.file_name = self.storage.save(
            "test_evidence.txt",
            ContentFile(b"Private discipline evidence test"),
        )
        self.report.attachments.name = self.file_name
        self.report.save(update_fields=["attachments"])

    def tearDown(self):
        if getattr(self, "storage", None) and getattr(self, "file_name", None):
            try:
                self.storage.delete(self.file_name)
            except (OSError, ValueError):
                pass

    def download_url(self):
        return reverse(
            "discipline:download_evidence",
            args=[self.case.pk, self.report.pk],
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.download_url())
        self.assertEqual(response.status_code, 302)

    def test_ordinary_logged_in_user_cannot_download_evidence(self):
        self.client.force_login(self.ordinary_user)
        response = self.client.get(self.download_url())
        self.assertIn(response.status_code, (302, 403))
        self.assertFalse(
            self.case.audit_logs.filter(action="evidence_downloaded").exists()
        )

    def test_manager_can_download_evidence_and_download_is_audited(self):
        self.client.force_login(self.manager)
        response = self.client.get(self.download_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"].lower())
        self.assertTrue(
            self.case.audit_logs.filter(
                actor=self.manager,
                action="evidence_downloaded",
            ).exists()
        )
        content = b"".join(response.streaming_content)
        self.assertEqual(content, b"Private discipline evidence test")

