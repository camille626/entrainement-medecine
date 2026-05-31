import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from qcm.models import Answer, Category, Course, Question, QuizSession, UserAnswer


@pytest.fixture
def course(db):
    return Course.objects.create(name="P2 - La cellule", short_name="cell")


@pytest.fixture
def category(course):
    return Category.objects.create(
        name="La membrane plasmique", course=course, moodle_id=100
    )


@pytest.fixture
def question(category):
    return Question.objects.create(
        text="<p>À propos de la membrane plasmique :</p>",
        category=category,
        qtype="multichoice",
        moodle_id=200,
    )


@pytest.fixture
def answer(question):
    return Answer.objects.create(
        text="<p>Elle est composée d'une bicouche lipidique</p>",
        question=question,
        fraction=1.0,
        is_correct=True,
    )


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="etudiant",
        password="test",  # pragma: allowlist secret
    )


@pytest.mark.django_db
class TestCourse:
    def test_create_course(self, course):
        assert course.pk is not None
        assert course.name == "P2 - La cellule"
        assert course.short_name == "cell"

    def test_str_representation(self, course):
        assert str(course) == "P2 - La cellule"

    def test_short_name_max_length(self, db):
        course = Course(name="Test", short_name="x" * 51)
        with pytest.raises(ValidationError):
            course.full_clean()


@pytest.mark.django_db
class TestCategory:
    def test_create_category(self, category, course):
        assert category.pk is not None
        assert category.name == "La membrane plasmique"
        assert category.course == course

    def test_moodle_id_unique(self, category):
        with pytest.raises(IntegrityError):
            Category.objects.create(
                name="Autre catégorie",
                course=category.course,
                moodle_id=100,
            )

    def test_str_representation(self, category):
        assert str(category) == "La membrane plasmique"


@pytest.mark.django_db
class TestQuestion:
    def test_create_question(self, question, category):
        assert question.pk is not None
        assert question.category == category
        assert question.qtype == "multichoice"
        assert question.moodle_id == 200

    def test_moodle_id_unique(self, question):
        with pytest.raises(IntegrityError):
            Question.objects.create(
                text="<p>Autre question</p>",
                category=question.category,
                qtype="multichoice",
                moodle_id=200,
            )

    def test_str_representation(self, question):
        assert "200" in str(question)

    def test_cascade_delete_with_category(self, question, category):
        category.delete()
        assert not Question.objects.filter(pk=question.pk).exists()


@pytest.mark.django_db
class TestAnswer:
    def test_create_correct_answer(self, answer, question):
        assert answer.pk is not None
        assert answer.question == question
        assert answer.is_correct is True
        assert answer.fraction == 1.0

    def test_create_wrong_answer(self, question):
        wrong = Answer.objects.create(
            text="<p>Réponse incorrecte</p>",
            question=question,
            fraction=0.0,
            is_correct=False,
        )
        assert wrong.is_correct is False

    def test_cascade_delete_with_question(self, answer, question):
        question.delete()
        assert not Answer.objects.filter(pk=answer.pk).exists()


@pytest.mark.django_db
class TestQuizSession:
    def test_create_session(self, user, course):
        session = QuizSession.objects.create(user=user, course=course, mode="training")
        assert session.pk is not None
        assert session.mode == "training"
        assert session.completed_at is None

    def test_review_mode(self, user, course):
        session = QuizSession.objects.create(user=user, course=course, mode="review")
        assert session.mode == "review"

    def test_invalid_mode_raises(self, user, course):
        session = QuizSession(user=user, course=course, mode="invalid_mode")
        with pytest.raises(ValidationError):
            session.full_clean()


@pytest.mark.django_db
class TestUserAnswer:
    def test_create_user_answer(self, user, course, question, answer):
        session = QuizSession.objects.create(user=user, course=course, mode="training")
        ua = UserAnswer.objects.create(
            session=session,
            question=question,
            answer=answer,
            is_correct=True,
        )
        assert ua.pk is not None
        assert ua.is_correct is True
        assert ua.answered_at is not None

    def test_cascade_delete_with_session(self, user, course, question, answer):
        session = QuizSession.objects.create(user=user, course=course, mode="training")
        ua = UserAnswer.objects.create(
            session=session, question=question, answer=answer, is_correct=True
        )
        session.delete()
        assert not UserAnswer.objects.filter(pk=ua.pk).exists()
