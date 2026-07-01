"""Tests pour l'éditeur Quill dans le formulaire de modification de question."""

import pytest
from django.contrib.auth.models import User

from qcm.models import Course, Question, Semester, StudyYear


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="admin_staff_quill",
        password="motdepasse123",  # pragma: allowlist secret
        is_staff=True,
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
def question_with_html(course):
    return Question.objects.create(
        text="<p>Quel est le <strong>rôle</strong> du fémur ?</p>",
        feedback="<p>Le fémur est l'os le plus long du corps.<br>Il supporte le poids.</p>",
        course=course,
        qtype="multichoice",
        moodle_id=2001,
    )


@pytest.mark.django_db
class TestQuestionFormQuill:
    """L'éditeur de question doit utiliser Quill pour énoncé et correction générale."""

    def _get(self, client, staff_user, question):
        client.force_login(staff_user)
        response = client.get(f"/admin-site/questions/{question.pk}/modifier/")
        assert response.status_code == 200
        return response.content.decode()

    def test_quill_css_loaded(self, client, staff_user, question_with_html):
        """La feuille de style Quill snow doit être chargée dans la page."""
        content = self._get(client, staff_user, question_with_html)
        assert "quill.snow.css" in content

    def test_quill_js_loaded(self, client, staff_user, question_with_html):
        """Le script Quill JS doit être chargé dans la page."""
        content = self._get(client, staff_user, question_with_html)
        assert "quill.min.js" in content

    def test_no_textarea_for_text(self, client, staff_user, question_with_html):
        """Le champ énoncé ne doit pas être un textarea (remplacé par Quill)."""
        content = self._get(client, staff_user, question_with_html)
        assert (
            'name="text"' not in content
            or "<textarea" not in content.split('name="text"')[0].split("<")[-1]
        )
        # Vérification directe : aucun <textarea name="text"
        assert '<textarea name="text"' not in content

    def test_no_textarea_for_feedback(self, client, staff_user, question_with_html):
        """Le champ correction générale ne doit pas être un textarea (remplacé par Quill)."""
        content = self._get(client, staff_user, question_with_html)
        assert '<textarea name="feedback"' not in content

    def test_hidden_input_for_text(self, client, staff_user, question_with_html):
        """Un input hidden name="text" doit transporter la valeur HTML vers le POST."""
        content = self._get(client, staff_user, question_with_html)
        assert 'type="hidden" name="text"' in content

    def test_hidden_input_for_feedback(self, client, staff_user, question_with_html):
        """Un input hidden name="feedback" doit transporter la valeur HTML vers le POST."""
        content = self._get(client, staff_user, question_with_html)
        assert 'type="hidden" name="feedback"' in content

    def test_html_content_preserved_in_text(
        self, client, staff_user, question_with_html
    ):
        """Le HTML du champ text doit être présent dans la page (pas strippé)."""
        content = self._get(client, staff_user, question_with_html)
        assert "<strong>" in content

    def test_html_content_preserved_in_feedback(
        self, client, staff_user, question_with_html
    ):
        """Le HTML du champ feedback doit être présent dans la page (pas strippé)."""
        content = self._get(client, staff_user, question_with_html)
        assert "<br>" in content
