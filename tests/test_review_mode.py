"""Tests pour le mode révision (issue #24)."""

import pytest
from django.contrib.auth.models import User

from qcm.models import (
    Answer,
    Course,
    Question,
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
        is_staff=True,
    )


@pytest.fixture
def course_data(user):
    sy = StudyYear.objects.create(name="P2", order=2)
    sem = Semester.objects.create(study_year=sy, name="S1", order=1)
    course = Course.objects.create(
        name="P2 - La cellule", short_name="cell", moodle_id=11, semester=sem
    )
    UserEnrollment.objects.create(user=user, course=course)

    # 3 questions: q1 (failed), q2 (passed), q3 (never done)
    q1 = Question.objects.create(
        text="Q1", course=course, qtype="multichoice", moodle_id=501
    )
    q2 = Question.objects.create(
        text="Q2", course=course, qtype="multichoice", moodle_id=502
    )
    q3 = Question.objects.create(
        text="Q3", course=course, qtype="multichoice", moodle_id=503
    )

    a1_wrong = Answer.objects.create(
        text="Wrong", question=q1, fraction=0.0, is_correct=False
    )
    a2_right = Answer.objects.create(
        text="Right", question=q2, fraction=1.0, is_correct=True
    )
    Answer.objects.create(text="Right3", question=q3, fraction=1.0, is_correct=True)

    # Past session: q1 wrong, q2 right
    past = QuizSession.objects.create(user=user, course=course, mode="training")
    QuizSessionQuestion.objects.create(session=past, question=q1, order=1)
    QuizSessionQuestion.objects.create(session=past, question=q2, order=2)
    UserAnswer.objects.create(
        session=past, question=q1, answer=a1_wrong, is_correct=False
    )
    UserAnswer.objects.create(
        session=past, question=q2, answer=a2_right, is_correct=True
    )

    return {"course": course, "q1": q1, "q2": q2, "q3": q3}


@pytest.mark.django_db
class TestReviewModeFilter:
    def test_config_page_shows_review_filter(self, client, user, course_data):
        client.force_login(user)
        response = client.get("/entrainement/")
        assert (
            b"vision" in response.content.lower()
            or b"r\xc3\xa9vision" in response.content
        )

    def test_review_filter_selects_failed_questions(self, client, user, course_data):
        """Review filter with nb_questions=2 should pick q1 (failed) and q3 (never done), not q2."""
        client.force_login(user)
        response = client.post(
            "/entrainement/",
            {
                "courses": [course_data["course"].pk],
                "mode": "training",
                "nb_questions": 2,  # Only ask for 2 → should get the 2 priority ones
                "question_filter": "review",
            },
        )
        assert response.status_code == 302
        session = QuizSession.objects.filter(user=user).order_by("-started_at").first()
        assert session is not None
        question_ids = set(
            session.session_questions.values_list("question_id", flat=True)
        )
        # q2 (passed at 100%) should NOT be in review session (2 priority questions fill the quota)
        assert course_data["q2"].pk not in question_ids
        assert len(question_ids) == 2

    def test_never_done_filter_excludes_attempted(self, client, user, course_data):
        """'never' filter with nb_questions=1 should return only q3 (never done)."""
        client.force_login(user)
        response = client.post(
            "/entrainement/",
            {
                "courses": [course_data["course"].pk],
                "mode": "training",
                "nb_questions": 1,  # Only 1 question → must be the never-done one
                "question_filter": "never",
            },
        )
        assert response.status_code == 302
        session = QuizSession.objects.filter(user=user).order_by("-started_at").first()
        question_ids = set(
            session.session_questions.values_list("question_id", flat=True)
        )
        assert course_data["q3"].pk in question_ids
        assert course_data["q1"].pk not in question_ids
        assert course_data["q2"].pk not in question_ids

    def test_all_filter_includes_all_questions(self, client, user, course_data):
        """Default 'all' filter should not exclude any question."""
        client.force_login(user)
        client.post(
            "/entrainement/",
            {
                "courses": [course_data["course"].pk],
                "mode": "training",
                "nb_questions": 10,
                "question_filter": "all",
            },
        )
        session = QuizSession.objects.filter(user=user).order_by("-started_at").first()
        question_ids = set(
            session.session_questions.values_list("question_id", flat=True)
        )
        # All 3 questions should potentially be included
        assert len(question_ids) == 3

    def test_review_session_has_review_mode(self, client, user, course_data):
        """Session created with review filter should have mode='review'."""
        client.force_login(user)
        client.post(
            "/entrainement/",
            {
                "courses": [course_data["course"].pk],
                "mode": "training",
                "nb_questions": 5,
                "question_filter": "review",
            },
        )
        session = QuizSession.objects.filter(user=user).order_by("-started_at").first()
        assert session.mode == "review"
