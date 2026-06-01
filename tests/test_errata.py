"""Tests pour le système errata (issue #19)."""

import pytest
from django.contrib.auth.models import User
from django.core import mail

from qcm.models import (
    Answer,
    Category,
    Course,
    Errata,
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
    cat = Category.objects.create(name="Cat", course=course, moodle_id=100)
    q = Question.objects.create(
        text="<p>Question test</p>",
        category=cat,
        qtype="multichoice",
        moodle_id=500,
    )
    Answer.objects.create(text="A correct", question=q, fraction=1.0, is_correct=True)
    Answer.objects.create(text="A wrong", question=q, fraction=0.0, is_correct=False)
    return q


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
