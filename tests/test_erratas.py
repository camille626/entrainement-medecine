"""Tests pour les vues et templates d'erratas."""

import pytest
from django.contrib.auth.models import User

from qcm.models import Category, Course, Errata, Question, Semester, StudyYear


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="admin_staff",
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
def category(course):
    return Category.objects.create(name="Os", course=course, moodle_id=99)


@pytest.fixture
def question_with_pluginfile(category):
    return Question.objects.create(
        text='<p>Légendez ce schéma <img src="@@PLUGINFILE@@/schema_os.png"></p>',
        category=category,
        qtype="multichoice",
        moodle_id=1001,
    )


@pytest.fixture
def errata_image(question_with_pluginfile, staff_user):
    return Errata.objects.create(
        question=question_with_pluginfile,
        reported_by=staff_user,
        error_type=Errata.IMAGE,
        description="Image manquante dans l'énoncé",
    )


@pytest.mark.django_db
class TestErrataImageTemplate:
    """L'interface errata IMAGE ne doit pas exposer le nom de fichier Moodle."""

    def test_moodle_filename_label_not_visible(self, client, staff_user, errata_image):
        """Le label 'Nom du fichier Moodle' ne doit pas apparaître dans la page."""
        client.force_login(staff_user)
        response = client.get("/errata/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Nom du fichier Moodle" not in content

    def test_moodle_filename_helper_text_not_visible(
        self, client, staff_user, errata_image
    ):
        """Le texte d'aide sur @@PLUGINFILE@@ ne doit pas apparaître."""
        client.force_login(staff_user)
        response = client.get("/errata/")
        content = response.content.decode()
        assert "@@PLUGINFILE@@" not in content

    def test_moodle_filename_hidden_input_present(
        self, client, staff_user, errata_image
    ):
        """L'input moodle_filename doit rester dans le DOM en tant que hidden."""
        client.force_login(staff_user)
        response = client.get("/errata/")
        content = response.content.decode()
        assert 'type="hidden" name="moodle_filename"' in content

    def test_description_signalee_not_shown_for_image(
        self, client, staff_user, errata_image
    ):
        """'Description signalée' ne doit pas apparaître pour les erratas IMAGE."""
        client.force_login(staff_user)
        response = client.get("/errata/")
        content = response.content.decode()
        assert "Description signal" not in content

    def test_description_not_shown_for_image(self, client, staff_user, errata_image):
        """La description brute ne doit pas s'afficher pour les erratas IMAGE."""
        client.force_login(staff_user)
        response = client.get("/errata/")
        content = response.content.decode()
        assert "Image(s) non r" not in content
