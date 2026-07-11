"""Tests pour les statistiques personnalisées (issue #16)."""

import pytest
from django.contrib.auth.models import User

from qcm.models import (
    Answer,
    Course,
    QuizSession,
    QuizSessionQuestion,
    Semester,
    StudyYear,
    UserAnswer,
    UserEnrollment,
)


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="etudiant",
        password="pass",  # pragma: allowlist secret
        first_name="Camille",
    )


@pytest.fixture
def study_data(user):
    """Create a full study setup with sessions and answers."""
    sy = StudyYear.objects.create(name="P2", order=2)
    sem = Semester.objects.create(study_year=sy, name="S1", order=1)
    course = Course.objects.create(
        name="P2 - La cellule", short_name="cell", moodle_id=11, semester=sem
    )
    UserEnrollment.objects.create(user=user, course=course)

    from qcm.models import Question

    q1 = Question.objects.create(
        text="Q1", course=course, qtype="multichoice", moodle_id=500
    )
    q2 = Question.objects.create(
        text="Q2", course=course, qtype="multichoice", moodle_id=501
    )
    a1_correct = Answer.objects.create(
        text="A correct", question=q1, fraction=1.0, is_correct=True
    )
    a2_wrong = Answer.objects.create(
        text="A wrong", question=q2, fraction=0.0, is_correct=False
    )

    # Create a session with 1 correct + 1 wrong answer
    session = QuizSession.objects.create(user=user, course=course, mode="training")
    QuizSessionQuestion.objects.create(session=session, question=q1, order=1)
    QuizSessionQuestion.objects.create(session=session, question=q2, order=2)
    UserAnswer.objects.create(
        session=session, question=q1, answer=a1_correct, is_correct=True
    )
    UserAnswer.objects.create(
        session=session, question=q2, answer=a2_wrong, is_correct=False
    )

    return {
        "course": course,
        "session": session,
        "q1": q1,
        "q2": q2,
    }


@pytest.mark.django_db
class TestStatsPage:
    def test_stats_page_returns_200(self, client, user):
        client.force_login(user)
        response = client.get("/statistiques/")
        assert response.status_code == 200

    def test_stats_page_requires_login(self, client):
        response = client.get("/statistiques/")
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    def test_stats_shows_total_questions(self, client, user, study_data):
        client.force_login(user)
        response = client.get("/statistiques/")
        assert b"2" in response.content  # 2 questions answered

    def test_stats_shows_course_breakdown(self, client, user, study_data):
        client.force_login(user)
        response = client.get("/statistiques/")
        assert b"La cellule" in response.content

    def test_stats_shows_note_sur_20(self, client, user, study_data):
        client.force_login(user)
        response = client.get("/statistiques/")
        assert b"/20" in response.content

    def test_stats_shows_progress_data(self, client, user, study_data):
        client.force_login(user)
        response = client.get("/statistiques/")
        # Should have chart data
        assert (
            b"chart" in response.content.lower()
            or b"progression" in response.content.lower()
        )

    def test_stats_counts_ddimageortext_like_other_types(
        self, client, user, study_data
    ):
        """Les questions à légender (ddimageortext) sont comptées comme les autres
        types dans le total disponible (issue #63)."""
        from qcm.models import Question

        Question.objects.create(
            text="Légende",
            course=study_data["course"],
            qtype=Question.DDIMAGEORTEXT,
        )

        client.force_login(user)
        response = client.get("/statistiques/")

        # q1, q2 (multichoice) + la question ddimageortext
        assert response.context["total_available"] == 3
        course_stat = next(
            s
            for s in response.context["course_stats"]
            if s["course"] == study_data["course"]
        )
        assert course_stat["nb_available"] == 3

    def test_stats_note_accounts_for_ddimageortext_partial_credit(
        self, client, user, study_data
    ):
        """Une réponse ddimageortext partiellement correcte pèse dans la note
        globale (issue #63) — fraction_override doit primer sur is_correct."""
        from qcm.models import Question, UserAnswer

        ddi_question = Question.objects.create(
            text="Légende",
            course=study_data["course"],
            qtype=Question.DDIMAGEORTEXT,
        )
        UserAnswer.objects.create(
            session=study_data["session"],
            question=ddi_question,
            answer=None,
            is_correct=False,
            fraction_override=0.5,
        )

        client.force_login(user)
        response = client.get("/statistiques/")

        # q1 correct (1.0) + q2 incorrect (0.0) + ddi partiel (0.5) sur 3 * 20
        assert response.context["note_20"] == 10.0

    def test_stats_includes_courses_never_practiced(self, client, user, study_data):
        """Le total et le breakdown par cours incluent aussi les cours jamais
        pratiqués (ni inscription, ni réponse) — issue #63."""
        from qcm.models import Course, Question, Semester, StudyYear

        sy = StudyYear.objects.create(name="P3", order=3)
        sem = Semester.objects.create(study_year=sy, name="S1", order=1)
        other_course = Course.objects.create(
            name="P3 - Jamais pratiqué",
            short_name="autre",
            moodle_id=999,
            semester=sem,
        )
        Question.objects.create(
            text="Q jamais pratiquée", course=other_course, qtype="multichoice"
        )

        client.force_login(user)
        response = client.get("/statistiques/")

        # q1, q2 (cours inscrit) + la question du cours jamais pratiqué
        assert response.context["total_available"] == 3
        never_practiced_stat = next(
            s for s in response.context["course_stats"] if s["course"] == other_course
        )
        assert never_practiced_stat["nb_done"] == 0
        assert never_practiced_stat["nb_available"] == 1


@pytest.mark.django_db
class TestStatsNavbar:
    def test_stats_tab_is_active_link(self, client, user):
        client.force_login(user)
        response = client.get("/statistiques/")
        content = response.content.decode()
        # The stats tab should be active (not disabled) on the stats page
        assert "Statistiques" in content
