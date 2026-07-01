"""Tests pour le navigateur de questions et les tags en session (issue #20)."""

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
    Tag,
    TagCategory,
    UserAnswer,
)


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="student",
        password="pass",  # pragma: allowlist secret
        is_staff=False,
    )


@pytest.fixture
def session_with_questions(db, user):
    """Session de 3 questions avec tags EC et chapitre sur la première."""
    year = StudyYear.objects.create(name="P2", order=1)
    semester = Semester.objects.create(name="S1", study_year=year, order=1)
    course = Course.objects.create(name="Cours test", moodle_id=1001)
    semester.courses.add(course)

    # Tags
    tc_ec = TagCategory.objects.create(name="EC", tag_type="souscategorie")
    tc_ch = TagCategory.objects.create(name="Chapitres", tag_type="chapitre")
    tag_ec = Tag.objects.create(name="hemato", category=tc_ec, moodle_id=5001)
    tag_ch = Tag.objects.create(name="GR", category=tc_ch, moodle_id=5002)

    questions = []
    for i in range(3):
        q = Question.objects.create(
            text=f"<p>Question {i + 1}</p>",
            course=course,
            moodle_id=3000 + i,
        )
        Answer.objects.create(text="A", question=q, fraction=1.0, is_correct=True)
        Answer.objects.create(text="B", question=q, fraction=-1.0, is_correct=False)
        questions.append(q)

    # Tags sur la première question
    questions[0].tags.add(tag_ec, tag_ch)

    session = QuizSession.objects.create(user=user, mode="training")
    for i, q in enumerate(questions):
        QuizSessionQuestion.objects.create(session=session, question=q, order=i + 1)

    return session, questions, tag_ec, tag_ch


# ── QuestionView : sq_list et tags ────────────────────────────────────────────


@pytest.mark.django_db
class TestQuestionViewContext:
    def test_sq_list_in_context(self, client, user, session_with_questions):
        session, questions, _, _ = session_with_questions
        client.force_login(user)
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert response.status_code == 200
        assert "sq_list" in response.context
        assert len(response.context["sq_list"]) == 3

    def test_sq_list_all_not_answered_initially(
        self, client, user, session_with_questions
    ):
        session, questions, _, _ = session_with_questions
        client.force_login(user)
        response = client.get(f"/entrainement/session/{session.pk}/")
        statuses = [sq["status"] for sq in response.context["sq_list"]]
        assert all(s == "not_answered" for s in statuses)

    def test_ec_tags_in_context(self, client, user, session_with_questions):
        session, questions, tag_ec, _ = session_with_questions
        client.force_login(user)
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert "ec_tags" in response.context
        assert tag_ec in response.context["ec_tags"]

    def test_chapter_tags_in_context(self, client, user, session_with_questions):
        session, questions, _, tag_ch = session_with_questions
        client.force_login(user)
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert "chapter_tags" in response.context
        assert tag_ch in response.context["chapter_tags"]


# ── Navigation directe via ?q=<ordre> ────────────────────────────────────────


@pytest.mark.django_db
class TestQuestionNavigation:
    def test_navigate_to_question_by_order(self, client, user, session_with_questions):
        session, questions, _, _ = session_with_questions
        client.force_login(user)
        # Navigate to question 2 (order=2)
        response = client.get(f"/entrainement/session/{session.pk}/?q=2")
        assert response.status_code == 200
        assert response.context["question"] == questions[1]

    def test_navigate_to_question_3(self, client, user, session_with_questions):
        session, questions, _, _ = session_with_questions
        client.force_login(user)
        response = client.get(f"/entrainement/session/{session.pk}/?q=3")
        assert response.status_code == 200
        assert response.context["question"] == questions[2]

    def test_current_sq_marked_in_list(self, client, user, session_with_questions):
        session, questions, _, _ = session_with_questions
        client.force_login(user)
        response = client.get(f"/entrainement/session/{session.pk}/?q=2")
        sq_list = response.context["sq_list"]
        current = next(sq for sq in sq_list if sq["is_current"])
        assert current["order"] == 2


# ── Question déjà répondue ────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAnsweredQuestionNavigation:
    def _answer_question(self, session, question, correct=True):
        answers = list(question.answers.all())
        answer = next(a for a in answers if a.is_correct == correct)
        UserAnswer.objects.create(
            session=session,
            question=question,
            answer=answer,
            is_correct=answer.is_correct,
        )

    def test_is_answered_false_for_unanswered(
        self, client, user, session_with_questions
    ):
        session, questions, _, _ = session_with_questions
        client.force_login(user)
        response = client.get(f"/entrainement/session/{session.pk}/?q=1")
        assert response.context["is_answered"] is False

    def test_is_answered_true_for_answered(self, client, user, session_with_questions):
        session, questions, _, _ = session_with_questions
        self._answer_question(session, questions[0])
        client.force_login(user)
        response = client.get(f"/entrainement/session/{session.pk}/?q=1")
        assert response.context["is_answered"] is True

    def test_sq_status_correct_after_correct_answer(
        self, client, user, session_with_questions
    ):
        session, questions, _, _ = session_with_questions
        self._answer_question(session, questions[0], correct=True)
        client.force_login(user)
        response = client.get(f"/entrainement/session/{session.pk}/?q=1")
        sq_list = response.context["sq_list"]
        assert sq_list[0]["status"] == "correct"

    def test_sq_status_incorrect_after_wrong_answer(
        self, client, user, session_with_questions
    ):
        session, questions, _, _ = session_with_questions
        self._answer_question(session, questions[0], correct=False)
        client.force_login(user)
        response = client.get(f"/entrainement/session/{session.pk}/?q=1")
        sq_list = response.context["sq_list"]
        assert sq_list[0]["status"] == "incorrect"

    def test_navigator_shows_in_template(self, client, user, session_with_questions):
        session, questions, _, _ = session_with_questions
        client.force_login(user)
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert b"question-nav" in response.content
