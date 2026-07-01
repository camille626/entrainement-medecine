from django.db import migrations


def populate_question_course(apps, schema_editor):
    Question = apps.get_model("qcm", "Question")
    for q in Question.objects.select_related("category__course").iterator():
        if q.category_id is not None and q.category.course_id is not None:
            q.course_id = q.category.course_id
            q.save(update_fields=["course_id"])


def reverse_populate(apps, schema_editor):
    Question = apps.get_model("qcm", "Question")
    Question.objects.all().update(course=None)


class Migration(migrations.Migration):
    dependencies = [
        ("qcm", "0032_question_add_course_nullable"),
    ]

    operations = [
        migrations.RunPython(populate_question_course, reverse_populate),
    ]
