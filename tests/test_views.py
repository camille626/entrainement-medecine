"""Tests RED pour l'interface d'entraînement (issue #5)."""

import pytest

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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def study_year(db):
    return StudyYear.objects.create(name="P2", order=2)


@pytest.fixture
def semester_s1(study_year):
    return Semester.objects.create(study_year=study_year, name="S1", order=1)


@pytest.fixture
def course(semester_s1):
    return Course.objects.create(
        name="P2 - La cellule",
        short_name="cell",
        moodle_id=11,
        semester=semester_s1,
    )


@pytest.fixture
def category(course):
    return Category.objects.create(name="Membrane", course=course, moodle_id=100)


@pytest.fixture
def question(category):
    return Question.objects.create(
        text="<p>À propos de la membrane :</p>",
        feedback="<p>A. VRAI — B. FAUX</p>",
        category=category,
        qtype="multichoice",
        moodle_id=500,
    )


@pytest.fixture
def answer_correct(question):
    return Answer.objects.create(
        text="<p>Bicouche lipidique</p>",
        question=question,
        fraction=1.0,
        is_correct=True,
    )


@pytest.fixture
def answer_wrong(question):
    return Answer.objects.create(
        text="<p>Monocouche</p>",
        question=question,
        fraction=0.0,
        is_correct=False,
    )


@pytest.fixture
def session(course, question):
    session = QuizSession.objects.create(course=course, mode="training")
    QuizSessionQuestion.objects.create(session=session, question=question, order=1)
    return session


@pytest.fixture
def logged_user(db):
    from django.contrib.auth.models import User

    return User.objects.create_user(
        username="testuser",
        password="pass",  # pragma: allowlist secret
    )


@pytest.fixture
def client(client, logged_user):
    client.force_login(logged_user)
    return client


# ---------------------------------------------------------------------------
# Tests de la page d'accueil
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestHomeView:
    def test_home_returns_200(self, client, semester_s1):
        response = client.get("/")
        assert response.status_code == 200

    def test_home_shows_semester(self, client, semester_s1):
        response = client.get("/")
        assert b"S1" in response.content

    def test_home_shows_course(self, client, course):
        response = client.get("/")
        assert b"La cellule" in response.content


# ---------------------------------------------------------------------------
# Tests de la page de configuration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestConfigurationView:
    def test_get_returns_200(self, client, course):
        response = client.get("/entrainement/")
        assert response.status_code == 200

    def test_get_shows_course(self, client, course):
        response = client.get("/entrainement/")
        assert b"La cellule" in response.content

    def test_post_creates_session_and_redirects(
        self, client, course, question, answer_correct
    ):
        response = client.post(
            "/entrainement/",
            {
                "courses": [course.pk],
                "mode": "training",
                "nb_questions": 1,
            },
        )
        assert response.status_code == 302
        assert QuizSession.objects.count() == 1
        session = QuizSession.objects.first()
        assert session.mode == "training"
        assert QuizSessionQuestion.objects.filter(session=session).count() == 1

    def test_post_redirects_to_session(self, client, course, question, answer_correct):
        response = client.post(
            "/entrainement/",
            {"courses": [course.pk], "mode": "training", "nb_questions": 1},
        )
        assert "/entrainement/session/" in response["Location"]


# ---------------------------------------------------------------------------
# Tests de la page de question
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestQuestionView:
    def test_question_returns_200(self, client, session):
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert response.status_code == 200

    def test_question_shows_text(self, client, session, question):
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert b"membrane" in response.content

    def test_question_shows_answers(
        self, client, session, answer_correct, answer_wrong
    ):
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert b"Bicouche" in response.content

    def test_question_shows_position(self, client, session):
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert b"1" in response.content

    def test_completed_session_redirects_to_fin(
        self, client, session, question, answer_correct
    ):
        # Mark question as answered
        UserAnswer.objects.create(
            session=session,
            question=question,
            answer=answer_correct,
            is_correct=True,
        )
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert response.status_code == 302
        assert "/fin/" in response["Location"]


# ---------------------------------------------------------------------------
# Tests de l'endpoint Check (HTMX)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCheckView:
    def test_check_returns_200(self, client, session, question, answer_correct):
        response = client.post(
            f"/entrainement/session/{session.pk}/check/",
            {"answers": [answer_correct.pk]},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200

    def test_check_creates_user_answers(
        self, client, session, question, answer_correct
    ):
        client.post(
            f"/entrainement/session/{session.pk}/check/",
            {"answers": [answer_correct.pk]},
            HTTP_HX_REQUEST="true",
        )
        assert UserAnswer.objects.count() == 1
        ua = UserAnswer.objects.first()
        assert ua.question == question
        assert ua.answer == answer_correct

    def test_check_shows_correction(self, client, session, question, answer_correct):
        response = client.post(
            f"/entrainement/session/{session.pk}/check/",
            {"answers": [answer_correct.pk]},
            HTTP_HX_REQUEST="true",
        )
        assert b"Correction" in response.content or b"VRAI" in response.content

    def test_check_shows_feedback(self, client, session, question, answer_correct):
        response = client.post(
            f"/entrainement/session/{session.pk}/check/",
            {"answers": [answer_correct.pk]},
            HTTP_HX_REQUEST="true",
        )
        assert b"VRAI" in response.content


# ---------------------------------------------------------------------------
# Tests de la page de fin
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestFinView:
    def test_fin_returns_200(self, client, session, question, answer_correct):
        UserAnswer.objects.create(
            session=session,
            question=question,
            answer=answer_correct,
            is_correct=True,
        )
        response = client.get(f"/entrainement/session/{session.pk}/fin/")
        assert response.status_code == 200

    def test_fin_shows_note_sur_20(self, client, session, question, answer_correct):
        UserAnswer.objects.create(
            session=session,
            question=question,
            answer=answer_correct,
            is_correct=True,
        )
        response = client.get(f"/entrainement/session/{session.pk}/fin/")
        assert response.status_code == 200
        assert b"/20" in response.content

    def test_fin_shows_correction_accordion(
        self, client, session, question, answer_correct
    ):
        UserAnswer.objects.create(
            session=session,
            question=question,
            answer=answer_correct,
            is_correct=True,
        )
        response = client.get(f"/entrainement/session/{session.pk}/fin/")
        assert (
            b"accordion" in response.content or b"R\xc3\xa9vision" in response.content
        )
