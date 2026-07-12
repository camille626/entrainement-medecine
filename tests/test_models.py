import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from qcm.models import Answer, Course, Question, QuizSession, UserAnswer


@pytest.fixture
def course(db):
    return Course.objects.create(name="P2 - La cellule", short_name="cell")


@pytest.fixture
def question(course):
    return Question.objects.create(
        text="<p>À propos de la membrane plasmique :</p>",
        course=course,
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
class TestQuestion:
    def test_create_question(self, question, course):
        assert question.pk is not None
        assert question.course == course
        assert question.qtype == "multichoice"
        assert question.moodle_id == 200

    def test_moodle_id_unique(self, question):
        with pytest.raises(IntegrityError):
            Question.objects.create(
                text="<p>Autre question</p>",
                course=question.course,
                qtype="multichoice",
                moodle_id=200,
            )

    def test_str_representation(self, question):
        assert "200" in str(question)

    def test_updated_at_set_on_create(self, question):
        assert question.updated_at is not None

    def test_updated_at_changes_on_save(self, question):
        original = question.updated_at
        question.text = "<p>Texte modifié</p>"
        question.save()
        question.refresh_from_db()
        assert question.updated_at > original


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
class TestQuestionCourseDirectFK:
    """RED : vérifient que Question pointe directement vers Course (sans Category)."""

    def test_question_has_course_fk(self):
        from django.core.exceptions import FieldDoesNotExist  # noqa: F401

        field = Question._meta.get_field("course")
        assert field.related_model.__name__ == "Course"

    def test_question_no_category_field(self):
        from django.core.exceptions import FieldDoesNotExist

        with pytest.raises(FieldDoesNotExist):
            Question._meta.get_field("category")

    def test_category_model_removed(self):
        import qcm.models as m

        assert not hasattr(m, "Category")


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
