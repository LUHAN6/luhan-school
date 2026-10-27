from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from accounts.models import UserProfile
from students.models import Student


class StudentAccountSignalSafetyTests(TestCase):
    def make_student(self, admission_no):
        return Student.objects.create(
            admission_no=admission_no,
            first_name="Signal",
            middle_name="",
            last_name="Test",
            gender="Female",
            date_of_birth=date(2015, 1, 1),
            class_name="Grade 4",
            stream="Blue",
        )

    def test_new_student_gets_account_with_unusable_password(self):
        student = self.make_student("SIG-NEW-001")

        profile = UserProfile.objects.get(student=student)

        self.assertEqual(profile.role, "STUDENT")
        self.assertEqual(profile.user.username, "SIG-NEW-001")
        self.assertFalse(profile.user.has_usable_password())
        self.assertEqual(profile.user.first_name, "Signal")

    def test_matching_staff_username_is_not_adopted(self):
        existing_user = User.objects.create_user(
            username="SIG-STAFF-002",
            password="Staff-Test-Password-Only-123!",
            is_staff=True,
        )
        existing_profile = UserProfile.objects.create(
            user=existing_user,
            role="STAFF",
        )

        student = self.make_student("sig-staff-002")

        existing_user.refresh_from_db()
        existing_profile.refresh_from_db()

        self.assertEqual(existing_user.profile.role, "STAFF")
        self.assertTrue(existing_user.is_staff)
        self.assertTrue(existing_user.has_usable_password())
        self.assertFalse(
            UserProfile.objects.filter(student=student).exists()
        )

    def test_matching_superuser_username_is_not_adopted(self):
        existing_user = User.objects.create_superuser(
            username="SIG-ADMIN-003",
            email="signal-admin-test@example.invalid",
            password="Admin-Test-Password-Only-123!",
        )

        student = self.make_student("SIG-ADMIN-003")

        existing_user.refresh_from_db()

        self.assertTrue(existing_user.is_superuser)
        self.assertTrue(existing_user.is_staff)
        self.assertFalse(
            UserProfile.objects.filter(student=student).exists()
        )

    def test_username_of_another_student_account_is_not_adopted(self):
        first_student = self.make_student("SIG-ORIGINAL-004")
        first_profile = UserProfile.objects.get(student=first_student)

        # Change the existing account's username to the next admission number
        # to simulate a collision without changing its learner relationship.
        first_profile.user.username = "SIG-COLLISION-005"
        first_profile.user.save(update_fields=["username"])

        second_student = self.make_student("SIG-COLLISION-005")

        first_profile.refresh_from_db()

        self.assertEqual(first_profile.student_id, first_student.pk)
        self.assertFalse(
            UserProfile.objects.filter(student=second_student).exists()
        )
        self.assertEqual(
            User.objects.filter(username__iexact="SIG-COLLISION-005").count(),
            1,
        )

    def test_updating_existing_student_does_not_create_another_account(self):
        student = self.make_student("SIG-UPDATE-006")
        original_profile = UserProfile.objects.get(student=student)

        student.first_name = "Updated"
        student.save()

        self.assertEqual(
            UserProfile.objects.filter(student=student).count(),
            1,
        )
        self.assertEqual(
            UserProfile.objects.get(student=student).pk,
            original_profile.pk,
        )
