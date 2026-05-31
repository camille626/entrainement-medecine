from django.db import migrations


S1_MOODLE_IDS = {11, 12, 13, 14, 15, 16, 17, 18}
S2_MOODLE_IDS = {19, 20, 21, 22, 23}


def create_p2_semesters(apps, schema_editor):
    StudyYear = apps.get_model("qcm", "StudyYear")
    Semester = apps.get_model("qcm", "Semester")
    Course = apps.get_model("qcm", "Course")

    p2 = StudyYear.objects.create(name="P2", order=2)
    s1 = Semester.objects.create(study_year=p2, name="S1", order=1)
    s2 = Semester.objects.create(study_year=p2, name="S2", order=2)

    Course.objects.filter(moodle_id__in=S1_MOODLE_IDS).update(semester=s1)
    Course.objects.filter(moodle_id__in=S2_MOODLE_IDS).update(semester=s2)


def remove_p2_semesters(apps, schema_editor):
    StudyYear = apps.get_model("qcm", "StudyYear")
    Course = apps.get_model("qcm", "Course")

    Course.objects.filter(moodle_id__in=S1_MOODLE_IDS | S2_MOODLE_IDS).update(
        semester=None
    )
    StudyYear.objects.filter(name="P2").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("qcm", "0003_add_studyyear_semester"),
    ]

    operations = [
        migrations.RunPython(create_p2_semesters, remove_p2_semesters),
    ]
