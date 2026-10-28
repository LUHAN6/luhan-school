from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_userprofile_timezone"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="schoolbranding",
            options={
                "verbose_name": "School Branding",
                "verbose_name_plural": "School Branding",
                "permissions": [
                    (
                        "access_staff_academic_portal",
                        "Academics (full access to the staff academic portal)",
                    ),
                ],
            },
        ),
    ]
