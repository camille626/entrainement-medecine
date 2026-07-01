import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("qcm", "0033_migrate_question_course_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="question",
            name="course",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="questions",
                to="qcm.course",
            ),
        ),
        migrations.RemoveField(
            model_name="question",
            name="category",
        ),
        migrations.DeleteModel(
            name="Category",
        ),
    ]
