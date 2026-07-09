"""Tests pour le système errata (issue #19)."""

import pytest
from django.contrib.auth.models import User
from django.core import mail

from qcm.models import (
    Answer,
    Course,
    Errata,
    ImageDropZone,
    Question,
    Semester,
    StudyYear,
)


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="etudiant",
        password="pass",  # pragma: allowlist secret
        email="etudiant@example.com",
        is_staff=True,
    )


@pytest.fixture
def question(db):
    sy = StudyYear.objects.create(name="P2", order=2)
    sem = Semester.objects.create(study_year=sy, name="S1", order=1)
    course = Course.objects.create(
        name="P2 - La cellule", short_name="cell", moodle_id=11, semester=sem
    )
    q = Question.objects.create(
        text="<p>Question test</p>",
        course=course,
        qtype="multichoice",
        moodle_id=500,
    )
    Answer.objects.create(text="A correct", question=q, fraction=1.0, is_correct=True)
    Answer.objects.create(text="A wrong", question=q, fraction=0.0, is_correct=False)
    return q


@pytest.fixture
def ddi_zone(question):
    """Zone de dépôt rattachée à une question ddimageortext distincte (issue #54)."""
    ddi_question = Question.objects.create(
        text="<p>Légender l'oeil :</p>",
        course=question.course,
        qtype=Question.DDIMAGEORTEXT,
        moodle_id=5601,
    )
    return ImageDropZone.objects.create(
        question=ddi_question,
        no=1,
        xleft=100,
        ytop=50,
        correct_drag_no=1,
        correct_label="sclérotique",
    )


@pytest.mark.django_db
class TestErrataModel:
    def test_create_errata(self, user, question):
        errata = Errata.objects.create(
            question=question,
            reported_by=user,
            error_type="correction",
            description="La réponse B devrait être correcte.",
        )
        assert errata.pk is not None
        assert errata.status == "pending"
        assert errata.created_at is not None

    def test_errata_str(self, user, question):
        errata = Errata.objects.create(
            question=question,
            reported_by=user,
            error_type="tag",
            description="Mauvais tag",
        )
        assert str(errata)  # should not raise

    def test_errata_with_concerned_answers(self, user, question):
        errata = Errata.objects.create(
            question=question,
            reported_by=user,
            error_type="correction",
            description="Erreur",
        )
        answer = question.answers.first()
        errata.concerned_answers.add(answer)
        assert errata.concerned_answers.count() == 1

    def test_ddi_answer_type_choice_exists(self):
        assert Errata.DDI_ANSWER == "ddi_answer"
        assert (
            Errata.DDI_ANSWER,
            "Une de mes réponses est correcte (légende interactive)",
        ) in (Errata.TYPE_CHOICES)

    def test_errata_with_concerned_zone(self, user, ddi_zone):
        errata = Errata.objects.create(
            question=ddi_zone.question,
            reported_by=user,
            error_type=Errata.DDI_ANSWER,
            qroc_suggested_text="choroïde",
            concerned_zone=ddi_zone,
        )
        assert errata.concerned_zone == ddi_zone

    def test_errata_concerned_zone_is_nullable(self, user, question):
        errata = Errata.objects.create(
            question=question,
            reported_by=user,
            error_type=Errata.OTHER,
            description="Sans zone",
        )
        assert errata.concerned_zone is None

    def test_errata_concerned_zone_set_null_on_zone_delete(self, user, ddi_zone):
        errata = Errata.objects.create(
            question=ddi_zone.question,
            reported_by=user,
            error_type=Errata.DDI_ANSWER,
            qroc_suggested_text="choroïde",
            concerned_zone=ddi_zone,
        )
        ddi_zone.delete()
        errata.refresh_from_db()
        assert errata.concerned_zone_id is None


@pytest.mark.django_db
class TestErrataSubmission:
    def test_submit_errata_returns_200(self, client, user, question):
        client.force_login(user)
        response = client.post(
            f"/errata/question/{question.pk}/",
            {
                "error_type": "autre",
                "description": "Il y a une erreur dans cette question.",
            },
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200

    def test_submit_errata_creates_object(self, client, user, question):
        client.force_login(user)
        client.post(
            f"/errata/question/{question.pk}/",
            {
                "error_type": "correction",
                "description": "La correction est incorrecte.",
            },
            HTTP_HX_REQUEST="true",
        )
        assert Errata.objects.filter(question=question, reported_by=user).exists()

    def test_submit_requires_login(self, client, question):
        response = client.post(
            f"/errata/question/{question.pk}/",
            {"error_type": "autre", "description": "Erreur"},
        )
        assert response.status_code == 302
        assert "/login/" in response["Location"]


@pytest.mark.django_db
class TestErrataListPage:
    def test_list_returns_200(self, client, user):
        client.force_login(user)
        response = client.get("/errata/")
        assert response.status_code == 200

    def test_list_shows_errata(self, client, user, question):
        Errata.objects.create(
            question=question,
            reported_by=user,
            error_type="autre",
            description="Signalement test",
        )
        client.force_login(user)
        response = client.get("/errata/")
        assert b"Signalement test" in response.content


@pytest.mark.django_db
class TestErrataAdminActions:
    @pytest.fixture
    def admin(self, db):
        return User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass",  # pragma: allowlist secret
        )

    @pytest.fixture
    def pending_errata(self, user, question):
        return Errata.objects.create(
            question=question,
            reported_by=user,
            error_type="tag",
            description="Mauvais tag",
        )

    def test_accept_creates_notification(self, client, admin, pending_errata):
        from qcm.models import Notification

        client.force_login(admin)
        client.post(
            "/admin/qcm/errata/",
            {
                "action": "accept_erratas",
                "_selected_action": [pending_errata.pk],
            },
        )
        # Notification created for the reporter (no email)
        assert Notification.objects.filter(user=pending_errata.reported_by).exists()
        assert len(mail.outbox) == 0

    def test_accept_updates_status(self, client, admin, pending_errata):
        client.force_login(admin)
        client.post(
            "/admin/qcm/errata/",
            {
                "action": "accept_erratas",
                "_selected_action": [pending_errata.pk],
            },
        )
        pending_errata.refresh_from_db()
        assert pending_errata.status == "accepted"

    def test_reject_updates_status(self, client, admin, pending_errata):
        client.force_login(admin)
        client.post(
            "/admin/qcm/errata/",
            {
                "action": "reject_erratas",
                "_selected_action": [pending_errata.pk],
            },
        )
        pending_errata.refresh_from_db()
        assert pending_errata.status == "rejected"
