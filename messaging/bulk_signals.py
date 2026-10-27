from django.db.models.signals import post_save, m2m_changed
from django.dispatch import receiver

from parents.models import Parent
from students.models import Student, OnlineApplication
from .bulk_sync import sync_erp_contacts


@receiver(post_save, sender=Parent, dispatch_uid="bulk_sync_parent_saved")
def sync_after_parent_save(sender, instance, **kwargs):
    sync_erp_contacts()


@receiver(m2m_changed, sender=Parent.children.through, dispatch_uid="bulk_sync_parent_children")
def sync_after_parent_children_change(sender, action, **kwargs):
    if action in ("post_add", "post_remove", "post_clear"):
        sync_erp_contacts()


@receiver(post_save, sender=Student, dispatch_uid="bulk_sync_student_saved")
def sync_after_student_save(sender, instance, **kwargs):
    sync_erp_contacts()


@receiver(post_save, sender=OnlineApplication, dispatch_uid="bulk_sync_application_saved")
def sync_after_application_save(sender, instance, **kwargs):
    if instance.status == "Admitted":
        sync_erp_contacts()
