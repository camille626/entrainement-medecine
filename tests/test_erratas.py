"""Tests pour les vues et templates d'erratas."""

import pytest
from django.contrib.auth.models import User

from qcm.models import Course, Errata, Question, Semester, StudyYear


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
def question_with_pluginfile(course):
    return Question.objects.create(
        text='<p>Légendez ce schéma <img src="@@PLUGINFILE@@/schema_os.png"></p>',
        course=course,
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

    def test_no_standalone_accept_button_for_image(
        self, client, staff_user, errata_image
    ):
        """Le bouton 'Accepter le signalement' seul ne doit pas apparaître pour IMAGE."""
        client.force_login(staff_user)
        response = client.get("/errata/")
        content = response.content.decode()
        # Le bouton standalone pointe vers /accept/ sans upload
        assert f'action="/errata/{errata_image.pk}/accept/"' not in content

    def test_upload_and_accept_button_present_for_image(
        self, client, staff_user, errata_image
    ):
        """Le bouton 'Uploader et accepter' doit être présent pour IMAGE."""
        client.force_login(staff_user)
        response = client.get("/errata/")
        content = response.content.decode()
        assert "Uploader et accepter le signalement" in content


@pytest.fixture
def question_simple(course):
    return Question.objects.create(
        text="<p>Quelle est la capitale de la France ?</p>",
        course=course,
        qtype="multichoice",
        moodle_id=1002,
    )


@pytest.fixture
def errata_tag(question_simple, staff_user):
    return Errata.objects.create(
        question=question_simple,
        reported_by=staff_user,
        error_type=Errata.TAG,
        description="Tag manquant",
    )


@pytest.mark.django_db
class TestErrataTagTemplate:
    """Les erratas non-IMAGE conservent leur bouton 'Accepter le signalement'."""

    def test_accept_button_present_for_tag(self, client, staff_user, errata_tag):
        """Le bouton 'Accepter le signalement' doit rester pour les erratas TAG."""
        client.force_login(staff_user)
        response = client.get("/errata/")
        content = response.content.decode()
        assert f'action="/errata/{errata_tag.pk}/accept/"' in content


@pytest.mark.django_db
class TestErrataModifyQuestionLink:
    """Le bouton 'Modifier la question' doit pointer vers l'éditeur custom."""

    def test_errata_image_modifier_link_points_to_custom_editor(
        self, client, staff_user, errata_image
    ):
        """Pour IMAGE : le lien modifier pointe vers /admin-site/questions/."""
        client.force_login(staff_user)
        response = client.get("/errata/")
        content = response.content.decode()
        assert f"/admin-site/questions/{errata_image.question_id}/modifier/" in content

    def test_errata_image_no_django_admin_link(self, client, staff_user, errata_image):
        """Plus aucun lien vers l'admin Django pour modifier une question."""
        client.force_login(staff_user)
        response = client.get("/errata/")
        content = response.content.decode()
        assert "/admin/qcm/question/" not in content

    def test_errata_tag_modifier_link_points_to_custom_editor(
        self, client, staff_user, errata_tag
    ):
        """Pour TAG : le lien modifier pointe aussi vers /admin-site/questions/."""
        client.force_login(staff_user)
        response = client.get("/errata/")
        content = response.content.decode()
        assert f"/admin-site/questions/{errata_tag.question_id}/modifier/" in content


@pytest.mark.django_db
class TestQuestionFormMoodleFilename:
    """L'éditeur custom de question ne doit pas afficher le champ nom Moodle."""

    def test_moodle_filename_label_not_in_question_form(
        self, client, staff_user, question_with_pluginfile
    ):
        """Le label 'Nom du fichier Moodle' n'apparaît pas dans l'éditeur."""
        client.force_login(staff_user)
        response = client.get(
            f"/admin-site/questions/{question_with_pluginfile.pk}/modifier/"
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Nom du fichier Moodle" not in content

    def test_new_image_filename_hidden_input_in_question_form(
        self, client, staff_user, question_with_pluginfile
    ):
        """L'input new_image_filename est présent en hidden dans l'éditeur."""
        client.force_login(staff_user)
        response = client.get(
            f"/admin-site/questions/{question_with_pluginfile.pk}/modifier/"
        )
        content = response.content.decode()
        assert 'type="hidden" name="new_image_filename"' in content
