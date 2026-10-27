from django.db import models
from django.contrib.auth.models import User


class Message(models.Model):

    MESSAGE_TYPES = [
        ("general", "General"),
        ("academic", "Academic"),
        ("fees", "Fees"),
        ("attendance", "Attendance"),
        ("event", "Event"),
        ("emergency", "Emergency"),
    ]

    APPROVAL_STATUS_CHOICES = [
        ("approved", "Approved"),
        ("pending", "Pending Approval"),
        ("rejected", "Rejected"),
    ]

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="received_messages",
    )

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_messages",
    )

    subject = models.CharField(
        max_length=200
    )

    message = models.TextField()

    message_type = models.CharField(
        max_length=20,
        choices=MESSAGE_TYPES,
        default="general",
    )

    # --------------------------------------------------------
    # ADMIN APPROVAL
    # --------------------------------------------------------

    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default="approved",
    )

    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_messages",
    )

    approved_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    rejection_reason = models.TextField(
        blank=True,
        default="",
    )

    # --------------------------------------------------------
    # ANNOUNCEMENT LINK
    # --------------------------------------------------------

    announcement = models.ForeignKey(
        "noticeboard.Notice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )

    is_read = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} - {self.recipient.username}"

# Bulk SMS and email campaign models
from .bulk_models import ContactGroup, Contact, MessageTemplate, Campaign, MessageLog
