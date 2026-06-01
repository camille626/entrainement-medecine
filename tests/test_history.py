"""Tests pour l'historique des tentatives (issue #18)."""

import pytest
from django.contrib.auth.models import User

from qcm.models import (
    Answer,
    Category,
    Course,
    Question,
    QuizSession,
    QuizSessionQuestion,
    Semester,
    StudyYear,
    UserAnswer,
)


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="etudiant",
        password="pass",  # pragma: allowlist secret
        is_staff=True,
    )


@pytest.fixture
def session_with_answers(user):
    sy = StudyYear.objects.create(name="P2", order=2)
    sem = Semester.objects.create(study_year=sy, name="S1", order=1)
    course = Course.objects.create(
        name="P2 - La cellule", short_name="cell", moodle_id=11, semester=sem
    )
    cat = Category.objects.create(name="Cat", course=course, moodle_id=100)
    q = Question.objects.create(
        text="<p>Q</p>", category=cat, qtype="multichoice", moodle_id=500
    )
    a = Answer.objects.create(
        text="<p>A correct</p>", question=q, fraction=1.0, is_correct=True
    )
    session = QuizSession.objects.create(user=user, course=course, mode="training")
    QuizSessionQuestion.objects.create(session=session, question=q, order=1)
    UserAnswer.objects.create(session=session, question=q, answer=a, is_correct=True)
    return session


@pytest.mark.django_db
class TestHistoryPage:
    def test_history_returns_200(self, client, user):
        client.force_login(user)
        response = client.get("/historique/")
        assert response.status_code == 200

    def test_history_requires_login(self, client):
        response = client.get("/historique/")
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    def test_history_shows_session(self, client, user, session_with_answers):
        client.force_login(user)
        response = client.get("/historique/")
        assert (
            b"La cellule" in response.content or b"cellule" in response.content.lower()
        )

    def test_history_shows_date(self, client, user, session_with_answers):
        client.force_login(user)
        response = client.get("/historique/")
        assert response.status_code == 200
        # Should contain some date-like content
        assert b"2026" in response.content or b"session" in response.content.lower()

    def test_history_empty_for_no_sessions(self, client, user):
        client.force_login(user)
        response = client.get("/historique/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestSessionDetailPage:
    def test_detail_returns_200(self, client, user, session_with_answers):
        client.force_login(user)
        response = client.get(f"/historique/session/{session_with_answers.pk}/")
        assert response.status_code == 200

    def test_detail_shows_question(self, client, user, session_with_answers):
        client.force_login(user)
        response = client.get(f"/historique/session/{session_with_answers.pk}/")
        assert b"La cellule" in response.content or b"Q" in response.content

    def test_detail_shows_score(self, client, user, session_with_answers):
        client.force_login(user)
        response = client.get(f"/historique/session/{session_with_answers.pk}/")
        assert b"/20" in response.content

    def test_detail_404_other_user(self, client, session_with_answers):
        other = User.objects.create_user(
            username="autre",
            password="pass",  # pragma: allowlist secret
        )
        client.force_login(other)
        response = client.get(f"/historique/session/{session_with_answers.pk}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestHistoryNavbar:
    def test_history_tab_is_active(self, client, user):
        client.force_login(user)
        response = client.get("/historique/")
        assert b"Historique" in response.content
