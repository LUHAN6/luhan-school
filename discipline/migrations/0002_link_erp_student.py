from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("discipline", "0001_initial"),
        ("students", "__first__"),
    ]

    operations = [
        migrations.AddField(
            model_name="disciplinecase",
            name="student",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="discipline_cases",
                to="students.student",
            ),
        ),
    ]
