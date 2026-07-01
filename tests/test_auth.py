"""Tests pour l'authentification (issue #13)."""

import pytest
from django.contrib.auth.models import User

from qcm.models import (
    Answer,
    Course,
    Question,
    QuizSession,
    Semester,
    StudyYear,
)


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="etudiant",
        password="motdepasse123",  # pragma: allowlist secret
        first_name="Camille",
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
        name="P2 - La cellule", short_name="cell", moodle_id=11, semester=semester
    )


@pytest.fixture
def question(course):
    q = Question.objects.create(
        text="<p>Question test</p>",
        course=course,
        qtype="multichoice",
        moodle_id=500,
    )
    Answer.objects.create(
        text="<p>Réponse</p>", question=q, fraction=1.0, is_correct=True
    )
    return q


# ---------------------------------------------------------------------------
# Tests de protection des routes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRouteProtection:
    def test_home_redirects_to_login_when_anonymous(self, client):
        response = client.get("/")
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    def test_configuration_redirects_when_anonymous(self, client):
        response = client.get("/entrainement/")
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    def test_session_redirects_when_anonymous(self, client):
        response = client.get("/entrainement/session/999/")
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    def test_fin_redirects_when_anonymous(self, client):
        response = client.get("/entrainement/session/999/fin/")
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    def test_home_accessible_when_logged_in(self, client, user):
        client.force_login(user)
        response = client.get("/")
        assert response.status_code == 200

    def test_configuration_accessible_when_logged_in(self, client, user, course):
        client.force_login(user)
        response = client.get("/entrainement/")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Tests du login
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLogin:
    def test_login_page_returns_200(self, client):
        response = client.get("/login/")
        assert response.status_code == 200

    def test_login_page_shows_form(self, client):
        response = client.get("/login/")
        assert (
            b"username" in response.content or b"connexion" in response.content.lower()
        )

    def test_valid_login_redirects(self, client, user):
        response = client.post(
            "/login/",
            {
                "username": "etudiant",
                "password": "motdepasse123",  # pragma: allowlist secret
            },
        )
        assert response.status_code == 302
        assert response["Location"] in ["/", "http://testserver/"]

    def test_invalid_login_shows_error(self, client, user):
        response = client.post(
            "/login/",
            {"username": "etudiant", "password": "mauvais"},  # pragma: allowlist secret
        )
        assert response.status_code == 200  # reste sur la page

    def test_login_redirects_to_next(self, client, user):
        response = client.post(
            "/login/?next=/entrainement/",
            {
                "username": "etudiant",
                "password": "motdepasse123",  # pragma: allowlist secret
            },
        )
        assert response.status_code == 302
        assert "/entrainement/" in response["Location"]


# ---------------------------------------------------------------------------
# Tests du logout
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLogout:
    def test_logout_redirects_to_login(self, client, user):
        client.force_login(user)
        response = client.post("/logout/")
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    def test_after_logout_home_redirects_to_login(self, client, user):
        client.force_login(user)
        client.post("/logout/")
        response = client.get("/")
        assert response.status_code == 302
        assert "/login/" in response["Location"]


# ---------------------------------------------------------------------------
# Tests de la liaison QuizSession.user
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestQuizSessionUser:
    def test_session_linked_to_logged_user(self, client, user, course, question):
        from qcm.models import UserEnrollment

        UserEnrollment.objects.create(user=user, course=course)
        client.force_login(user)
        client.post(
            "/entrainement/",
            {"courses": [course.pk], "mode": "training", "nb_questions": 1},
        )
        session = QuizSession.objects.first()
        assert session is not None
        assert session.user == user
