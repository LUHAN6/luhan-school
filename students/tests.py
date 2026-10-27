from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase

from accounts.models import UserProfile
from parents.models import Parent
from students.models import Student
from students.views import create_parent_account


class CreateParentAccountTests(TestCase):
    def make_student(
        self,
        admission_no,
        parent_name="Grace Njeri",
        parent_phone="0712345678",
    ):
        return Student.objects.create(
            admission_no=admission_no,
            first_name="Learner",
            middle_name="",
            last_name=admission_no,
            gender="Female",
            date_of_birth=date(2015, 1, 1),
            class_name="Grade 4",
            stream="Blue",
            parent_name=parent_name,
            parent_phone=parent_phone,
        )

    def test_new_parent_account_has_unusable_password(self):
        student = self.make_student("TEST-PARENT-001")

        parent = create_parent_account(student)

        self.assertIsNotNone(parent)
        self.assertEqual(parent.user.profile.role, "PARENT")
        self.assertFalse(parent.user.has_usable_password())
        self.assertTrue(parent.children.filter(pk=student.pk).exists())

    def test_siblings_with_same_parent_details_share_parent_account(self):
        first_student = self.make_student("TEST-PARENT-002")
        second_student = self.make_student("TEST-PARENT-003")

        first_parent = create_parent_account(first_student)
        second_parent = create_parent_account(second_student)

        self.assertEqual(first_parent.pk, second_parent.pk)
        self.assertEqual(Parent.objects.count(), 1)
        self.assertEqual(first_parent.children.count(), 2)

    def test_username_collision_does_not_take_over_staff_account(self):
        existing_user = User.objects.create_user(
            username="Grace_Njeri",
            password="Existing-Password-Only-For-Test-123!",
        )
        existing_profile = UserProfile.objects.create(
            user=existing_user,
            role="STAFF",
            phone="0700000000",
        )
        student = self.make_student("TEST-PARENT-004")

        parent = create_parent_account(student)

        existing_user.refresh_from_db()
        existing_profile.refresh_from_db()

        self.assertNotEqual(parent.user_id, existing_user.pk)
        self.assertEqual(existing_user.profile.role, "STAFF")
        self.assertEqual(existing_user.profile.phone, "0700000000")
        self.assertTrue(existing_user.has_usable_password())
        self.assertNotEqual(parent.user.username, existing_user.username)

    def test_existing_parent_record_with_wrong_role_is_rejected(self):
        existing_user = User.objects.create_user(
            username="existing_guardian",
            password="Existing-Password-Only-For-Test-456!",
        )
        UserProfile.objects.create(
            user=existing_user,
            role="STAFF",
        )
        parent = Parent.objects.create(
            user=existing_user,
            full_name="Grace Njeri",
            phone="0712345678",
        )
        student = self.make_student("TEST-PARENT-005")

        with self.assertRaisesMessage(ValueError, "role is not PARENT"):
            create_parent_account(student)

        self.assertFalse(parent.children.filter(pk=student.pk).exists())

    def test_existing_privileged_parent_account_is_rejected(self):
        existing_user = User.objects.create_user(
            username="privileged_guardian",
            password="Existing-Password-Only-For-Test-789!",
            is_staff=True,
        )
        UserProfile.objects.create(
            user=existing_user,
            role="PARENT",
        )
        parent = Parent.objects.create(
            user=existing_user,
            full_name="Grace Njeri",
            phone="0712345678",
        )
        student = self.make_student("TEST-PARENT-006")

        with self.assertRaisesMessage(ValueError, "privileged account"):
            create_parent_account(student)

        self.assertFalse(parent.children.filter(pk=student.pk).exists())
