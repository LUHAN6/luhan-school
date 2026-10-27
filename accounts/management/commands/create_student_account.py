from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from students.models import Student
from accounts.models import UserProfile


User = get_user_model()


class Command(BaseCommand):
    help = "Set an initial password for a student account"

    def add_arguments(self, parser):
        parser.add_argument("admission_no", type=str)

    def handle(self, *args, **options):
        admission_no = options["admission_no"].strip()

        if not admission_no:
            raise CommandError("Admission number cannot be empty.")

        student = Student.objects.filter(
            admission_no__iexact=admission_no
        ).first()

        if student is None:
            raise CommandError(
                f"Student {admission_no} does not exist."
            )

        profile = UserProfile.objects.filter(
            student=student
        ).select_related("user").first()

        if profile is not None:
            if profile.role != "STUDENT":
                raise CommandError(
                    "The linked profile is not a STUDENT profile. "
                    "No changes were made."
                )

            user = profile.user

            if user.has_usable_password():
                raise CommandError(
                    "This student account already has a usable password. "
                    "No changes were made. Use the administrator password "
                    "reset process if a reset is required."
                )
        else:
            collision = User.objects.filter(
                username__iexact=student.admission_no
            ).first()

            if collision is not None:
                raise CommandError(
                    "A username matching this admission number already "
                    "belongs to an account not linked to this student. "
                    "No changes were made; investigate the account first."
                )

            user = User(
                username=student.admission_no,
                first_name=student.first_name,
                last_name=student.last_name,
            )

        password = getpass("Set student password (input hidden): ")
        confirmation = getpass("Confirm student password: ")

        if not password:
            raise CommandError("Password cannot be empty.")

        if password != confirmation:
            raise CommandError(
                "Passwords do not match. No changes were made."
            )

        if len(password) < 12:
            raise CommandError(
                "Use a password of at least 12 characters."
            )

        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            raise CommandError(
                "Password rejected: " + " ".join(exc.messages)
            )

        with transaction.atomic():
            if profile is None:
                user.set_unusable_password()
                user.save()

                UserProfile.objects.create(
                    user=user,
                    role="STUDENT",
                    student=student,
                )

            user.set_password(password)
            user.save(update_fields=["password"])

        self.stdout.write(
            self.style.SUCCESS("Student password set successfully.")
        )
        self.stdout.write(f"Username: {user.username}")
        self.stdout.write("The password was not printed to the terminal.")
