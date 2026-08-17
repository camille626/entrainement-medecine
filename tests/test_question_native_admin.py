"""L'admin Django natif ne doit pas permettre de perdre la mise en forme (issue #111)."""

import pytest
from django.contrib.auth.models import User

from qcm.models import Course, Question, Semester, StudyYear


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        username="superadmin",
        email="superadmin@example.com",
        password="motdepasse123",  # pragma: allowlist secret
    )


@pytest.fixture
def study_year(db):
    return StudyYear.objects.create(name="P2", order=2)


@pytest.fixture
def semester(study_year):
    return Semester.objects.create(study_year=study_year, name="S1", order=1)


@pytest.fixture
def course(semester):
    return Course.objects.create(
        name="Anatomie", short_name="anat", moodle_id=42, semester=semester
    )


@pytest.fixture
def question(course):
    return Question.objects.create(
        text="<p>Quel est le rôle du fémur ?</p>",
        feedback="<p>Le fémur est l'os le plus long du corps.</p>",
        course=course,
        qtype="multichoice",
        moodle_id=2001,
    )


@pytest.mark.django_db
class TestQuestionAdminReadonlyTextFields:
    """text/feedback ne doivent être édités que via l'éditeur Quill custom."""

    def _get(self, client, superuser, question):
        client.force_login(superuser)
        response = client.get(f"/admin/qcm/question/{question.pk}/change/")
        assert response.status_code == 200
        return response.content.decode()

    def test_text_field_is_readonly(self, client, superuser, question):
        content = self._get(client, superuser, question)
        assert '<textarea name="text"' not in content

    def test_feedback_field_is_readonly(self, client, superuser, question):
        content = self._get(client, superuser, question)
        assert '<textarea name="feedback"' not in content

    def test_other_fields_still_editable(self, client, superuser, question):
        content = self._get(client, superuser, question)
        assert 'name="course"' in content
        assert 'name="tags"' in content
