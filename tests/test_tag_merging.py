import pytest
from django.contrib.auth.models import User

from qcm.models import Course, Question, Tag, TagCategory, TagMergeLog
from qcm.tag_merging import (
    TagMergeError,
    convert_tag_to_chapter,
    merge_course_tags,
    undo_tag_merge_log,
)


@pytest.fixture
def ec_category(db):
    return TagCategory.objects.create(name="EC", tag_type=TagCategory.SOUSCATEGORIE)


@pytest.fixture
def chapter_category(db):
    return TagCategory.objects.create(name="Chapitre", tag_type=TagCategory.CHAPITRE)


@pytest.fixture
def course_cardio(db):
    return Course.objects.create(
        name="P2 - système cardiovasculaire", short_name="cardio", moodle_id=1
    )


@pytest.fixture
def course_digestif(db):
    return Course.objects.create(
        name="P2 - appareil digestif", short_name="digestif", moodle_id=3
    )


@pytest.fixture
def semio(ec_category):
    return Tag.objects.create(name="semio", moodle_id=100, category=ec_category)


@pytest.fixture
def semio_cardio(ec_category):
    return Tag.objects.create(name="semio cardio", moodle_id=101, category=ec_category)


def _question(course, moodle_id, *tags):
    q = Question.objects.create(
        text="<p>Q</p>", course=course, qtype="multichoice", moodle_id=moodle_id
    )
    if tags:
        q.tags.set(tags)
    return q


@pytest.mark.django_db
class TestMergeCourseTags:
    def test_migrates_tags_on_targeted_course_questions(
        self, course_cardio, semio, semio_cardio
    ):
        q = _question(course_cardio, 1, semio)

        result = merge_course_tags(course_cardio, semio, semio_cardio)

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == ["semio cardio"]
        assert result.questions_migrated == 1

    def test_does_not_affect_other_courses(
        self, course_cardio, course_digestif, semio, semio_cardio
    ):
        other = _question(course_digestif, 1, semio)

        merge_course_tags(course_cardio, semio, semio_cardio)

        other.refresh_from_db()
        assert list(other.tags.values_list("name", flat=True)) == ["semio"]

    def test_reparents_chapter_tags_scoped_to_course(
        self, course_cardio, course_digestif, chapter_category, semio, semio_cardio
    ):
        ecg = Tag.objects.create(
            name="ECG",
            moodle_id=200,
            category=chapter_category,
            parent_ec=semio,
            course=course_cardio,
        )
        other_course_chapter = Tag.objects.create(
            name="coliques nephretiques",
            moodle_id=201,
            category=chapter_category,
            parent_ec=semio,
            course=course_digestif,
        )

        result = merge_course_tags(course_cardio, semio, semio_cardio)

        ecg.refresh_from_db()
        other_course_chapter.refresh_from_db()
        assert ecg.parent_ec == semio_cardio
        assert other_course_chapter.parent_ec == semio
        assert result.reparented_tags == ["ECG"]

    def test_dry_run_makes_no_changes(self, course_cardio, semio, semio_cardio):
        q = _question(course_cardio, 1, semio)

        result = merge_course_tags(course_cardio, semio, semio_cardio, dry_run=True)

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == ["semio"]
        assert result.questions_migrated == 1

    def test_same_from_and_to_tag_raises_tag_merge_error(self, course_cardio, semio):
        with pytest.raises(TagMergeError):
            merge_course_tags(course_cardio, semio, semio)

    def test_is_idempotent_when_from_tag_already_absent(
        self, course_cardio, semio, semio_cardio
    ):
        q = _question(course_cardio, 1, semio_cardio)

        result = merge_course_tags(course_cardio, semio, semio_cardio)

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == ["semio cardio"]
        assert result.questions_migrated == 0


@pytest.mark.django_db
class TestConvertTagToChapter:
    @pytest.fixture
    def radio(self, ec_category):
        return Tag.objects.create(name="radio", moodle_id=300, category=ec_category)

    def test_updates_tag_fields(
        self, course_cardio, chapter_category, radio, semio_cardio
    ):
        convert_tag_to_chapter(course_cardio, radio, semio_cardio)

        radio.refresh_from_db()
        assert radio.category == chapter_category
        assert radio.parent_ec == semio_cardio
        assert radio.course == course_cardio

    def test_adds_parent_ec_tag_to_questions(
        self, course_cardio, chapter_category, radio, semio_cardio
    ):
        q = _question(course_cardio, 1, radio)

        result = convert_tag_to_chapter(course_cardio, radio, semio_cardio)

        q.refresh_from_db()
        assert set(q.tags.values_list("name", flat=True)) == {"radio", "semio cardio"}
        assert result.questions_updated == 1

    def test_scoped_to_course(
        self, course_cardio, course_digestif, chapter_category, radio, semio_cardio
    ):
        other = _question(course_digestif, 1, radio)

        convert_tag_to_chapter(course_cardio, radio, semio_cardio)

        other.refresh_from_db()
        assert list(other.tags.values_list("name", flat=True)) == ["radio"]

    def test_dry_run_makes_no_changes(
        self, course_cardio, chapter_category, radio, semio_cardio
    ):
        q = _question(course_cardio, 1, radio)

        convert_tag_to_chapter(course_cardio, radio, semio_cardio, dry_run=True)

        radio.refresh_from_db()
        q.refresh_from_db()
        assert radio.category != chapter_category
        assert radio.parent_ec is None
        assert list(q.tags.values_list("name", flat=True)) == ["radio"]

    def test_rejects_non_ec_parent(self, course_cardio, chapter_category, radio):
        not_ec = Tag.objects.create(
            name="pas un EC", moodle_id=301, category=chapter_category
        )

        with pytest.raises(TagMergeError):
            convert_tag_to_chapter(course_cardio, radio, not_ec)

    def test_missing_chapter_category_raises_tag_merge_error(
        self, course_cardio, radio, semio_cardio
    ):
        # Pas de fixture chapter_category ici : la TagCategory "Chapitre" n'existe pas.
        with pytest.raises(TagMergeError):
            convert_tag_to_chapter(course_cardio, radio, semio_cardio)

    def test_is_idempotent(self, course_cardio, chapter_category, radio, semio_cardio):
        q = _question(course_cardio, 1, radio)

        for _ in range(2):
            convert_tag_to_chapter(course_cardio, radio, semio_cardio)

        q.refresh_from_db()
        assert set(q.tags.values_list("name", flat=True)) == {"radio", "semio cardio"}


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staff_test",
        password="pass",  # pragma: allowlist secret
        is_staff=True,
    )


@pytest.mark.django_db
class TestMergeLogging:
    def test_merge_creates_log(self, course_cardio, semio, semio_cardio, staff_user):
        _question(course_cardio, 1, semio)

        result = merge_course_tags(
            course_cardio, semio, semio_cardio, performed_by=staff_user
        )

        assert result.log_id is not None
        log = TagMergeLog.objects.get(pk=result.log_id)
        assert log.action == TagMergeLog.MERGE
        assert log.course == course_cardio
        assert log.performed_by == staff_user
        assert log.undone_at is None
        assert log.snapshot["from_tag_id"] == semio.pk
        assert log.snapshot["to_tag_id"] == semio_cardio.pk

    def test_dry_run_does_not_create_log(self, course_cardio, semio, semio_cardio):
        _question(course_cardio, 1, semio)

        result = merge_course_tags(course_cardio, semio, semio_cardio, dry_run=True)

        assert result.log_id is None
        assert TagMergeLog.objects.count() == 0

    def test_convert_to_chapter_creates_log(
        self, course_cardio, chapter_category, semio_cardio
    ):
        ec_category = semio_cardio.category
        radio = Tag.objects.create(name="radio", moodle_id=500, category=ec_category)

        result = convert_tag_to_chapter(course_cardio, radio, semio_cardio)

        assert result.log_id is not None
        log = TagMergeLog.objects.get(pk=result.log_id)
        assert log.action == TagMergeLog.CONVERT_TO_CHAPTER
        assert log.snapshot["tag_id"] == radio.pk
        assert log.snapshot["parent_ec_id"] == semio_cardio.pk


@pytest.mark.django_db
class TestUndoMerge:
    def test_undo_restores_from_tag_and_removes_to_tag(
        self, course_cardio, semio, semio_cardio
    ):
        q = _question(course_cardio, 1, semio)
        result = merge_course_tags(course_cardio, semio, semio_cardio)
        log = TagMergeLog.objects.get(pk=result.log_id)

        undo_tag_merge_log(log)

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == ["semio"]

    def test_undo_keeps_to_tag_if_question_already_had_it(
        self, course_cardio, semio, semio_cardio
    ):
        q = _question(course_cardio, 1, semio, semio_cardio)
        result = merge_course_tags(course_cardio, semio, semio_cardio)
        log = TagMergeLog.objects.get(pk=result.log_id)

        undo_tag_merge_log(log)

        q.refresh_from_db()
        assert set(q.tags.values_list("name", flat=True)) == {"semio", "semio cardio"}

    def test_undo_reparents_chapter_tags_back(
        self, course_cardio, chapter_category, semio, semio_cardio
    ):
        ecg = Tag.objects.create(
            name="ECG",
            moodle_id=600,
            category=chapter_category,
            parent_ec=semio,
            course=course_cardio,
        )
        result = merge_course_tags(course_cardio, semio, semio_cardio)
        log = TagMergeLog.objects.get(pk=result.log_id)

        undo_tag_merge_log(log)

        ecg.refresh_from_db()
        assert ecg.parent_ec == semio

    def test_undo_marks_log_undone_at(self, course_cardio, semio, semio_cardio):
        result = merge_course_tags(course_cardio, semio, semio_cardio)
        log = TagMergeLog.objects.get(pk=result.log_id)

        undo_tag_merge_log(log)

        log.refresh_from_db()
        assert log.undone_at is not None

    def test_double_undo_raises_tag_merge_error(
        self, course_cardio, semio, semio_cardio
    ):
        result = merge_course_tags(course_cardio, semio, semio_cardio)
        log = TagMergeLog.objects.get(pk=result.log_id)
        undo_tag_merge_log(log)

        with pytest.raises(TagMergeError):
            undo_tag_merge_log(log)

    def test_undo_raises_if_tag_deleted_since(self, course_cardio, semio, semio_cardio):
        result = merge_course_tags(course_cardio, semio, semio_cardio)
        log = TagMergeLog.objects.get(pk=result.log_id)
        semio.delete()

        with pytest.raises(TagMergeError):
            undo_tag_merge_log(log)


@pytest.mark.django_db
class TestUndoConvertToChapter:
    @pytest.fixture
    def radio(self, ec_category):
        return Tag.objects.create(name="radio", moodle_id=700, category=ec_category)

    def test_undo_restores_previous_tag_fields(
        self, course_cardio, chapter_category, ec_category, radio, semio_cardio
    ):
        result = convert_tag_to_chapter(course_cardio, radio, semio_cardio)
        log = TagMergeLog.objects.get(pk=result.log_id)

        undo_tag_merge_log(log)

        radio.refresh_from_db()
        assert radio.category == ec_category
        assert radio.parent_ec is None
        assert radio.course is None

    def test_undo_removes_parent_ec_tag_from_question(
        self, course_cardio, chapter_category, radio, semio_cardio
    ):
        q = _question(course_cardio, 1, radio)
        result = convert_tag_to_chapter(course_cardio, radio, semio_cardio)
        log = TagMergeLog.objects.get(pk=result.log_id)

        undo_tag_merge_log(log)

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == ["radio"]

    def test_undo_keeps_parent_ec_if_question_already_had_it(
        self, course_cardio, chapter_category, radio, semio_cardio
    ):
        q = _question(course_cardio, 1, radio, semio_cardio)
        result = convert_tag_to_chapter(course_cardio, radio, semio_cardio)
        log = TagMergeLog.objects.get(pk=result.log_id)

        undo_tag_merge_log(log)

        q.refresh_from_db()
        assert set(q.tags.values_list("name", flat=True)) == {"radio", "semio cardio"}
