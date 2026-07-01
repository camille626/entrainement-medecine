"""Tests TDD pour les images de questions (issue #29)."""

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError

from qcm.models import (
    Course,
    Errata,
    Question,
    QuestionImage,
    Semester,
    StudyYear,
)


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def course(db):
    sy = StudyYear.objects.create(name="P2", order=2)
    sem = Semester.objects.create(study_year=sy, name="S1", order=1)
    return Course.objects.create(
        name="P2 - Anatomie radiologique",
        short_name="anat_radio",
        moodle_id=99,
        semester=sem,
    )


@pytest.fixture
def question(course):
    return Question.objects.create(
        text='<p>Observez ce schéma :</p><img src="@@PLUGINFILE@@/schema.png" alt="schema">',
        course=course,
        qtype="multichoice",
        moodle_id=300,
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="admin",
        password="pass",  # pragma: allowlist secret
        is_staff=True,
    )


@pytest.fixture
def normal_user(db):
    return User.objects.create_user(
        username="etudiant",
        password="pass",  # pragma: allowlist secret
    )


@pytest.fixture
def errata_image(question, normal_user):
    return Errata.objects.create(
        question=question,
        reported_by=normal_user,
        error_type=Errata.IMAGE,
        description="Image manquante dans la question",
    )


def make_image_file(name: str = "schema.png") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        b"GIF89a\x01\x00\x01\x00\x00\xff\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x00;",
        content_type="image/gif",
    )


# ── Tests modèle QuestionImage ───────────────────────────────────────────────


@pytest.mark.django_db
class TestQuestionImageModel:
    def test_create_question_image(self, question):
        img = QuestionImage.objects.create(
            question=question,
            moodle_filename="schema.png",
            file=make_image_file("schema.png"),
        )
        assert img.pk is not None
        assert img.moodle_filename == "schema.png"
        assert img.question == question

    def test_str_representation(self, question):
        img = QuestionImage.objects.create(
            question=question,
            moodle_filename="schema.png",
            file=make_image_file("schema.png"),
        )
        assert "schema.png" in str(img)
        assert str(question.pk) in str(img)

    def test_unique_together_raises_on_duplicate(self, question):
        QuestionImage.objects.create(
            question=question,
            moodle_filename="schema.png",
            file=make_image_file("schema.png"),
        )
        with pytest.raises(IntegrityError):
            QuestionImage.objects.create(
                question=question,
                moodle_filename="schema.png",
                file=make_image_file("schema.png"),
            )

    def test_same_filename_different_questions_allowed(self, question, course):
        other_q = Question.objects.create(
            text="<p>Autre question</p>",
            course=course,
            qtype="multichoice",
            moodle_id=301,
        )
        QuestionImage.objects.create(
            question=question,
            moodle_filename="schema.png",
            file=make_image_file("schema.png"),
        )
        # Même filename, question différente → OK
        img2 = QuestionImage.objects.create(
            question=other_q,
            moodle_filename="schema.png",
            file=make_image_file("schema.png"),
        )
        assert img2.pk is not None


# ── Tests render_text() ──────────────────────────────────────────────────────


@pytest.mark.django_db
class TestQuestionRenderText:
    def test_text_without_pluginfile_unchanged(self, course):
        q = Question.objects.create(
            text="<p>Question sans image</p>",
            course=course,
            qtype="multichoice",
            moodle_id=400,
        )
        assert q.render_text() == "<p>Question sans image</p>"

    def test_pluginfile_replaced_when_image_uploaded(self, question):
        QuestionImage.objects.create(
            question=question,
            moodle_filename="schema.png",
            file=make_image_file("schema.png"),
        )
        rendered = question.render_text()
        assert "@@PLUGINFILE@@" not in rendered
        assert 'src="/media/question_images/' in rendered

    def test_pluginfile_shows_placeholder_when_image_missing(self, question):
        rendered = question.render_text()
        assert "@@PLUGINFILE@@" not in rendered
        assert "Image non disponible" in rendered

    def test_multiple_images_in_text(self, course):
        q = Question.objects.create(
            text=(
                "<p>Voici deux images :</p>"
                '<img src="@@PLUGINFILE@@/img1.png" alt="img1">'
                '<img src="@@PLUGINFILE@@/img2.jpg" alt="img2">'
            ),
            course=course,
            qtype="multichoice",
            moodle_id=401,
        )
        QuestionImage.objects.create(
            question=q, moodle_filename="img1.png", file=make_image_file("img1.png")
        )
        rendered = q.render_text()
        assert "@@PLUGINFILE@@" not in rendered
        # img1 résolu, img2 manquant
        assert "/media/question_images/" in rendered
        assert "Image non disponible" in rendered

    def test_img_attributes_preserved_when_resolved(self, question):
        QuestionImage.objects.create(
            question=question,
            moodle_filename="schema.png",
            file=make_image_file("schema.png"),
        )
        rendered = question.render_text()
        assert 'alt="schema"' in rendered


# ── Tests vue upload image via errata ────────────────────────────────────────


@pytest.mark.django_db
class TestErrataUploadImageView:
    def test_upload_creates_question_image_and_accepts_errata(
        self, client, staff_user, errata_image
    ):
        client.force_login(staff_user)
        response = client.post(
            f"/errata/{errata_image.pk}/upload-image/",
            {
                "moodle_filename": "schema.png",
                "image_file": make_image_file("schema.png"),
            },
            follow=True,
        )
        assert response.status_code == 200
        errata_image.refresh_from_db()
        assert errata_image.status == Errata.ACCEPTED
        assert QuestionImage.objects.filter(
            question=errata_image.question, moodle_filename="schema.png"
        ).exists()

    def test_non_staff_gets_404(self, client, normal_user, errata_image):
        client.force_login(normal_user)
        response = client.post(
            f"/errata/{errata_image.pk}/upload-image/",
            {
                "moodle_filename": "schema.png",
                "image_file": make_image_file("schema.png"),
            },
        )
        assert response.status_code == 404

    def test_unauthenticated_redirects_to_login(self, client, errata_image):
        response = client.post(
            f"/errata/{errata_image.pk}/upload-image/",
            {
                "moodle_filename": "schema.png",
                "image_file": make_image_file("schema.png"),
            },
        )
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    def test_notification_sent_to_reporter(self, client, staff_user, errata_image):
        from qcm.models import Notification

        client.force_login(staff_user)
        client.post(
            f"/errata/{errata_image.pk}/upload-image/",
            {
                "moodle_filename": "schema.png",
                "image_file": make_image_file("schema.png"),
            },
        )
        assert Notification.objects.filter(user=errata_image.reported_by).exists()
