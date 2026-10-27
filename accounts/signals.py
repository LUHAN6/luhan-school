import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from students.models import Student
from .models import UserProfile


User = get_user_model()
logger = logging.getLogger(__name__)


@receiver(post_save, sender=Student)
def create_student_account(sender, instance, created, **kwargs):
    """
    Create a password-disabled student account for a new learner.

    Never adopt an existing user based only on a matching admission number.
    """
    if not created:
        return

    admission_no = (instance.admission_no or "").strip()
    if not admission_no:
        return

    if UserProfile.objects.filter(student=instance).exists():
        return

    with transaction.atomic():
        # Admission numbers must not be used to claim existing accounts.
        existing_user = User.objects.filter(
            username__iexact=admission_no
        ).first()

        if existing_user is not None:
            logger.warning(
                "Student account not created for student_id=%s: "
                "username matching admission number already exists "
                "(user_id=%s). Manual review is required.",
                instance.pk,
                existing_user.pk,
            )
            return

        user = User.objects.create_user(
            username=admission_no,
            password=None,
            first_name=instance.first_name or "",
            last_name=instance.last_name or "",
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])

        UserProfile.objects.create(
            user=user,
            student=instance,
            role="STUDENT",
            custom_role=None,
            is_active=True,
        )
