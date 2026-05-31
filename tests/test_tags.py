import pytest

from qcm.models import Category, Course, Question, Tag


@pytest.fixture
def course(db):
    return Course.objects.create(
        name="P2 - La cellule", short_name="cell", moodle_id=11
    )


@pytest.fixture
def category(course):
    return Category.objects.create(name="Membrane", course=course, moodle_id=100)


@pytest.fixture
def question(category):
    return Question.objects.create(
        text="<p>Question test</p>",
        category=category,
        qtype="multichoice",
        moodle_id=500,
    )


@pytest.mark.django_db
class TestTag:
    def test_create_tag(self, db):
        tag = Tag.objects.create(name="annale 2024", moodle_id=52)
        assert tag.pk is not None
        assert tag.name == "annale 2024"

    def test_str(self, db):
        tag = Tag.objects.create(name="immuno", moodle_id=15)
        assert str(tag) == "immuno"

    def test_name_unique(self, db):
        from django.db import IntegrityError

        Tag.objects.create(name="hemato", moodle_id=28)
        with pytest.raises(IntegrityError):
            Tag.objects.create(name="hemato", moodle_id=99)

    def test_moodle_id_unique(self, db):
        from django.db import IntegrityError

        Tag.objects.create(name="hemato", moodle_id=28)
        with pytest.raises(IntegrityError):
            Tag.objects.create(name="autre", moodle_id=28)


@pytest.mark.django_db
class TestQuestionTags:
    def test_question_has_no_tags_by_default(self, question):
        assert question.tags.count() == 0

    def test_add_tag_to_question(self, question):
        tag = Tag.objects.create(name="annale 2024", moodle_id=52)
        question.tags.add(tag)
        assert question.tags.count() == 1
        assert tag in question.tags.all()

    def test_multiple_tags(self, question):
        t1 = Tag.objects.create(name="annale 2024", moodle_id=52)
        t2 = Tag.objects.create(name="immuno", moodle_id=15)
        question.tags.set([t1, t2])
        assert question.tags.count() == 2

    def test_tag_questions_reverse(self, question):
        tag = Tag.objects.create(name="annale 2023", moodle_id=17)
        question.tags.add(tag)
        assert question in tag.questions.all()
