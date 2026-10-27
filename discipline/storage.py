from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateDisciplineEvidenceStorage(FileSystemStorage):
    """Store discipline evidence outside public media."""

    def __init__(self):
        location = settings.BASE_DIR / "private_discipline_evidence"
        super().__init__(location=str(location), base_url=None)

    @property
    def base_url(self):
        """Never expose a public base URL for private evidence."""
        return None

    def url(self, name):
        """Private evidence must use the protected download view."""
        raise ValueError(
            "Discipline evidence is private. Use the protected download view."
        )
