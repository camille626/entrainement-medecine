import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from qcm.models import Course, Question, Tag, TagCategory


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
def course_respi(db):
    # Espace final volontaire : reproduit la donnée réelle en DB.
    return Course.objects.create(
        name="P2 - appareil respiratoire ", short_name="respi", moodle_id=2
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
class TestMergeAction:
    def test_merge_migrates_tags_on_targeted_course_questions(
        self, course_cardio, semio, semio_cardio
    ):
        q = _question(course_cardio, 1, semio)

        call_command(
            "merge_tags",
            "merge",
            course=course_cardio.name,
            from_tag="semio",
            to_tag="semio cardio",
        )

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == ["semio cardio"]

    def test_merge_does_not_affect_other_courses(
        self, course_cardio, course_digestif, semio, semio_cardio
    ):
        other = _question(course_digestif, 1, semio)

        call_command(
            "merge_tags",
            "merge",
            course=course_cardio.name,
            from_tag="semio",
            to_tag="semio cardio",
        )

        other.refresh_from_db()
        assert list(other.tags.values_list("name", flat=True)) == ["semio"]

    def test_merge_reparents_chapter_tags_scoped_to_course(
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

        call_command(
            "merge_tags",
            "merge",
            course=course_cardio.name,
            from_tag="semio",
            to_tag="semio cardio",
        )

        ecg.refresh_from_db()
        other_course_chapter.refresh_from_db()
        assert ecg.parent_ec == semio_cardio
        assert other_course_chapter.parent_ec == semio

    def test_merge_is_idempotent_when_from_tag_already_absent(
        self, course_cardio, semio, semio_cardio
    ):
        q = _question(course_cardio, 1, semio_cardio)

        call_command(
            "merge_tags",
            "merge",
            course=course_cardio.name,
            from_tag="semio",
            to_tag="semio cardio",
        )

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == ["semio cardio"]

    def test_merge_dry_run_makes_no_changes(self, course_cardio, semio, semio_cardio):
        q = _question(course_cardio, 1, semio)

        call_command(
            "merge_tags",
            "merge",
            course=course_cardio.name,
            from_tag="semio",
            to_tag="semio cardio",
            dry_run=True,
        )

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == ["semio"]

    def test_merge_unknown_course_raises_command_error(self, semio, semio_cardio):
        with pytest.raises(CommandError):
            call_command(
                "merge_tags",
                "merge",
                course="cours inexistant",
                from_tag="semio",
                to_tag="semio cardio",
            )

    def test_merge_unknown_from_tag_raises_command_error(
        self, course_cardio, semio_cardio
    ):
        with pytest.raises(CommandError):
            call_command(
                "merge_tags",
                "merge",
                course=course_cardio.name,
                from_tag="tag inexistant",
                to_tag="semio cardio",
            )

    def test_merge_unknown_to_tag_raises_command_error(self, course_cardio, semio):
        with pytest.raises(CommandError):
            call_command(
                "merge_tags",
                "merge",
                course=course_cardio.name,
                from_tag="semio",
                to_tag="tag inexistant",
            )

    def test_merge_ambiguous_course_raises_command_error(
        self, ec_category, semio, semio_cardio
    ):
        Course.objects.create(name="P2 - appareil respiratoire ", short_name="r1")
        Course.objects.create(name="P2 - appareil respiratoire bis", short_name="r2")

        with pytest.raises(CommandError):
            call_command(
                "merge_tags",
                "merge",
                course="appareil respiratoire",
                from_tag="semio",
                to_tag="semio cardio",
            )

    def test_merge_same_from_and_to_tag_raises_command_error(
        self, course_cardio, semio
    ):
        with pytest.raises(CommandError):
            call_command(
                "merge_tags",
                "merge",
                course=course_cardio.name,
                from_tag="semio",
                to_tag="semio",
            )

    def test_merge_missing_required_options_raises_command_error(self, course_cardio):
        with pytest.raises(CommandError):
            call_command("merge_tags", "merge", course=course_cardio.name)


@pytest.mark.django_db
class TestConvertToChapterAction:
    @pytest.fixture
    def radio(self, ec_category):
        return Tag.objects.create(name="radio", moodle_id=300, category=ec_category)

    def test_convert_to_chapter_updates_tag_fields(
        self, course_cardio, chapter_category, radio, semio_cardio
    ):
        call_command(
            "merge_tags",
            "convert-to-chapter",
            course=course_cardio.name,
            tag="radio",
            parent_ec="semio cardio",
        )

        radio.refresh_from_db()
        assert radio.category == chapter_category
        assert radio.parent_ec == semio_cardio
        assert radio.course == course_cardio

    def test_convert_to_chapter_adds_parent_ec_tag_to_questions(
        self, course_cardio, chapter_category, radio, semio_cardio
    ):
        q = _question(course_cardio, 1, radio)

        call_command(
            "merge_tags",
            "convert-to-chapter",
            course=course_cardio.name,
            tag="radio",
            parent_ec="semio cardio",
        )

        q.refresh_from_db()
        assert set(q.tags.values_list("name", flat=True)) == {"radio", "semio cardio"}

    def test_convert_to_chapter_scoped_to_course(
        self, course_cardio, course_digestif, chapter_category, radio, semio_cardio
    ):
        other = _question(course_digestif, 1, radio)

        call_command(
            "merge_tags",
            "convert-to-chapter",
            course=course_cardio.name,
            tag="radio",
            parent_ec="semio cardio",
        )

        other.refresh_from_db()
        assert list(other.tags.values_list("name", flat=True)) == ["radio"]

    def test_convert_to_chapter_dry_run_makes_no_changes(
        self, course_cardio, chapter_category, radio, semio_cardio
    ):
        q = _question(course_cardio, 1, radio)

        call_command(
            "merge_tags",
            "convert-to-chapter",
            course=course_cardio.name,
            tag="radio",
            parent_ec="semio cardio",
            dry_run=True,
        )

        radio.refresh_from_db()
        q.refresh_from_db()
        assert radio.category != chapter_category
        assert radio.parent_ec is None
        assert list(q.tags.values_list("name", flat=True)) == ["radio"]

    def test_convert_to_chapter_rejects_non_ec_parent(
        self, course_cardio, chapter_category, radio
    ):
        Tag.objects.create(name="pas un EC", moodle_id=301, category=chapter_category)

        with pytest.raises(CommandError):
            call_command(
                "merge_tags",
                "convert-to-chapter",
                course=course_cardio.name,
                tag="radio",
                parent_ec="pas un EC",
            )

    def test_convert_to_chapter_unknown_tag_raises_command_error(
        self, course_cardio, semio_cardio
    ):
        with pytest.raises(CommandError):
            call_command(
                "merge_tags",
                "convert-to-chapter",
                course=course_cardio.name,
                tag="tag inexistant",
                parent_ec="semio cardio",
            )

    def test_convert_to_chapter_missing_chapter_category_raises_command_error(
        self, course_cardio, radio, semio_cardio
    ):
        # Pas de fixture chapter_category ici : la TagCategory "Chapitre" n'existe pas.
        with pytest.raises(CommandError):
            call_command(
                "merge_tags",
                "convert-to-chapter",
                course=course_cardio.name,
                tag="radio",
                parent_ec="semio cardio",
            )

    def test_convert_to_chapter_is_idempotent(
        self, course_cardio, chapter_category, radio, semio_cardio
    ):
        q = _question(course_cardio, 1, radio)

        for _ in range(2):
            call_command(
                "merge_tags",
                "convert-to-chapter",
                course=course_cardio.name,
                tag="radio",
                parent_ec="semio cardio",
            )

        q.refresh_from_db()
        assert set(q.tags.values_list("name", flat=True)) == {"radio", "semio cardio"}

    def test_convert_to_chapter_missing_required_options_raises_command_error(
        self, course_cardio
    ):
        with pytest.raises(CommandError):
            call_command("merge_tags", "convert-to-chapter", course=course_cardio.name)


@pytest.mark.django_db
class TestRemoveAction:
    @pytest.fixture
    def physio(self, ec_category):
        return Tag.objects.create(name="physio", moodle_id=400, category=ec_category)

    def test_remove_removes_tag_only_for_targeted_course(self, course_cardio, physio):
        q = _question(course_cardio, 1, physio)

        call_command("merge_tags", "remove", course=course_cardio.name, tag="physio")

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == []

    def test_remove_does_not_delete_tag_globally(
        self, course_cardio, course_digestif, physio
    ):
        other = _question(course_digestif, 1, physio)

        call_command("merge_tags", "remove", course=course_cardio.name, tag="physio")

        assert Tag.objects.filter(name="physio").exists()
        other.refresh_from_db()
        assert list(other.tags.values_list("name", flat=True)) == ["physio"]

    def test_remove_dry_run_makes_no_changes(self, course_cardio, physio):
        q = _question(course_cardio, 1, physio)

        call_command(
            "merge_tags",
            "remove",
            course=course_cardio.name,
            tag="physio",
            dry_run=True,
        )

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == ["physio"]

    def test_remove_unknown_tag_raises_command_error(self, course_cardio):
        with pytest.raises(CommandError):
            call_command(
                "merge_tags",
                "remove",
                course=course_cardio.name,
                tag="tag inexistant",
            )

    def test_remove_is_idempotent(self, course_cardio, physio):
        q = _question(course_cardio, 1, physio)

        for _ in range(2):
            call_command(
                "merge_tags", "remove", course=course_cardio.name, tag="physio"
            )

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == []

    def test_remove_missing_required_options_raises_command_error(self, course_cardio):
        with pytest.raises(CommandError):
            call_command("merge_tags", "remove", course=course_cardio.name)


@pytest.mark.django_db
class TestCourseResolution:
    def test_course_lookup_handles_trailing_space_in_db(
        self, course_respi, ec_category
    ):
        semio = Tag.objects.create(name="semio", moodle_id=100, category=ec_category)
        Tag.objects.create(name="semio respi", moodle_id=102, category=ec_category)
        q = _question(course_respi, 1, semio)

        call_command(
            "merge_tags",
            "merge",
            course="appareil respiratoire",
            from_tag="semio",
            to_tag="semio respi",
        )

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == ["semio respi"]

    def test_course_lookup_prefers_exact_match(self, ec_category):
        exact = Course.objects.create(
            name="P2 - appareil respiratoire", short_name="r1"
        )
        Course.objects.create(name="P2 - appareil respiratoire bis", short_name="r2")
        semio = Tag.objects.create(name="semio", moodle_id=100, category=ec_category)
        Tag.objects.create(name="semio respi", moodle_id=102, category=ec_category)
        q = _question(exact, 1, semio)

        call_command(
            "merge_tags",
            "merge",
            course="P2 - appareil respiratoire",
            from_tag="semio",
            to_tag="semio respi",
        )

        q.refresh_from_db()
        assert list(q.tags.values_list("name", flat=True)) == ["semio respi"]


@pytest.mark.django_db
class TestInvalidAction:
    def test_unknown_action_choice_rejected(self, course_cardio):
        with pytest.raises(CommandError):
            call_command("merge_tags", "bogus", course=course_cardio.name)
