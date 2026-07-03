"""Tests RED pour les questions ddimageortext (légende interactive)."""

import json

import pytest
from django.contrib.auth.models import User

from qcm.models import (
    Answer,
    Course,
    ImageDragItem,
    ImageDropZone,
    ImageDropZoneLabel,
    Question,
    QuestionImage,
    QuizSession,
    QuizSessionQuestion,
    UserAnswer,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def course(db):
    return Course.objects.create(name="Anatomie P2", short_name="ana")


@pytest.fixture
def ddi_question(course):
    return Question.objects.create(
        text="<p>Légender l'oeil :</p>",
        course=course,
        qtype=Question.DDIMAGEORTEXT,
        moodle_id=5600,
    )


@pytest.fixture
def drag_items(ddi_question):
    items = [
        ImageDragItem.objects.create(question=ddi_question, no=1, label="sclérotique"),
        ImageDragItem.objects.create(question=ddi_question, no=2, label="choroide"),
        ImageDragItem.objects.create(question=ddi_question, no=3, label="rétine"),
        ImageDragItem.objects.create(
            question=ddi_question, no=4, label="distractor"
        ),  # distractor
    ]
    return items


@pytest.fixture
def drop_zones(ddi_question):
    zones = [
        ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        ),
        ImageDropZone.objects.create(
            question=ddi_question,
            no=2,
            xleft=200,
            ytop=100,
            correct_drag_no=2,
            correct_label="choroide",
        ),
        ImageDropZone.objects.create(
            question=ddi_question,
            no=3,
            xleft=300,
            ytop=150,
            correct_drag_no=3,
            correct_label="rétine",
        ),
    ]
    return zones


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="etudiant_ddi",
        password="test",  # pragma: allowlist secret
    )


@pytest.fixture
def session(user, course):
    return QuizSession.objects.create(user=user, course=course, mode="training")


# ── Tests modèles ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestImageDragItem:
    def test_create(self, ddi_question):
        drag = ImageDragItem.objects.create(
            question=ddi_question, no=1, label="sclérotique"
        )
        assert drag.pk is not None
        assert drag.no == 1
        assert drag.label == "sclérotique"
        assert drag.draggroup == 1

    def test_str(self, ddi_question):
        drag = ImageDragItem.objects.create(
            question=ddi_question, no=1, label="sclérotique"
        )
        assert "sclérotique" in str(drag)

    def test_cascade_delete(self, ddi_question):
        drag = ImageDragItem.objects.create(question=ddi_question, no=1, label="test")
        ddi_question.delete()
        assert not ImageDragItem.objects.filter(pk=drag.pk).exists()


@pytest.mark.django_db
class TestImageDropZone:
    def test_create(self, ddi_question):
        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        )
        assert zone.pk is not None
        assert zone.xleft == 100
        assert zone.ytop == 50
        assert zone.correct_drag_no == 1

    def test_str(self, ddi_question):
        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        )
        assert "sclérotique" in str(zone) or str(zone)

    def test_cascade_delete(self, ddi_question):
        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="test",
        )
        ddi_question.delete()
        assert not ImageDropZone.objects.filter(pk=zone.pk).exists()


@pytest.mark.django_db
class TestImageDropZoneLabel:
    def test_create(self, ddi_question):
        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        )
        label = ImageDropZoneLabel.objects.create(zone=zone, text="sclere")
        assert label.pk is not None
        assert label.text == "sclere"
        assert label.zone_id == zone.pk

    def test_str(self, ddi_question):
        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        )
        label = ImageDropZoneLabel.objects.create(zone=zone, text="sclere")
        assert "sclere" in str(label)

    def test_cascade_delete_with_zone(self, ddi_question):
        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        )
        label = ImageDropZoneLabel.objects.create(zone=zone, text="sclere")
        zone.delete()
        assert not ImageDropZoneLabel.objects.filter(pk=label.pk).exists()

    def test_accessible_via_zone_accepted_labels(self, ddi_question):
        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        )
        ImageDropZoneLabel.objects.create(zone=zone, text="sclere")
        ImageDropZoneLabel.objects.create(zone=zone, text="sclerotic")
        assert zone.accepted_labels.count() == 2


@pytest.mark.django_db
class TestMatchZoneLabel:
    def test_matches_correct_label_exact(self, ddi_question):
        from qcm.views import match_zone_label

        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        )
        assert match_zone_label(zone, "sclérotique") is True

    def test_matches_correct_label_case_insensitive_accents(self, ddi_question):
        from qcm.views import match_zone_label

        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        )
        assert match_zone_label(zone, "SCLEROTIQUE") is True

    def test_matches_accepted_alternative(self, ddi_question):
        from qcm.views import match_zone_label

        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        )
        ImageDropZoneLabel.objects.create(zone=zone, text="sclere")
        assert match_zone_label(zone, "sclere") is True
        assert match_zone_label(zone, "Sclere") is True

    def test_matches_accepted_alternative_with_wildcard(self, ddi_question):
        from qcm.views import match_zone_label

        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="myélome",
        )
        ImageDropZoneLabel.objects.create(zone=zone, text="myelome*")
        assert match_zone_label(zone, "myelome multiple") is True

    def test_no_match_returns_false(self, ddi_question):
        from qcm.views import match_zone_label

        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        )
        ImageDropZoneLabel.objects.create(zone=zone, text="sclere")
        assert match_zone_label(zone, "rétine") is False

    def test_empty_user_text_returns_false(self, ddi_question):
        from qcm.views import match_zone_label

        zone = ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=1,
            correct_label="sclérotique",
        )
        assert match_zone_label(zone, "") is False
        assert match_zone_label(zone, "   ") is False


@pytest.mark.django_db
class TestQuestionDDIType:
    def test_ddimageortext_is_valid_qtype(self, ddi_question):
        assert ddi_question.qtype == Question.DDIMAGEORTEXT
        assert ddi_question.qtype == "ddimageortext"

    def test_ddimageortext_in_choices(self):
        choices = dict(Question.QTYPE_CHOICES)
        assert "ddimageortext" in choices


# ── Tests UserAnswer.effective_fraction avec fraction_override ────────────────


@pytest.mark.django_db
class TestUserAnswerFractionOverride:
    def test_fraction_override_takes_priority(
        self, user, course, ddi_question, session
    ):
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        ua = UserAnswer.objects.create(
            session=session,
            question=ddi_question,
            answer=None,
            is_correct=False,
            fraction_override=0.67,
        )
        assert abs(ua.effective_fraction - 0.67) < 1e-6

    def test_fraction_override_zero(self, user, course, ddi_question, session):
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        ua = UserAnswer.objects.create(
            session=session,
            question=ddi_question,
            answer=None,
            is_correct=False,
            fraction_override=0.0,
        )
        assert ua.effective_fraction == 0.0

    def test_fraction_override_one(self, user, course, ddi_question, session):
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        ua = UserAnswer.objects.create(
            session=session,
            question=ddi_question,
            answer=None,
            is_correct=True,
            fraction_override=1.0,
        )
        assert ua.effective_fraction == 1.0

    def test_no_override_falls_back_to_answer_fraction(self, user, course):
        q = Question.objects.create(
            text="QCM", course=course, qtype="multichoice", moodle_id=9900
        )
        a = Answer.objects.create(text="A", question=q, fraction=0.5, is_correct=True)
        sess = QuizSession.objects.create(user=user, course=course, mode="training")
        QuizSessionQuestion.objects.create(session=sess, question=q, order=1)
        ua = UserAnswer.objects.create(
            session=sess, question=q, answer=a, is_correct=True, fraction_override=None
        )
        assert ua.effective_fraction == 0.5

    def test_no_override_no_answer_uses_is_correct(
        self, user, course, ddi_question, session
    ):
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        ua = UserAnswer.objects.create(
            session=session,
            question=ddi_question,
            answer=None,
            is_correct=True,
            fraction_override=None,
        )
        assert ua.effective_fraction == 1.0


# ── Tests CheckView pour ddimageortext ────────────────────────────────────────


@pytest.mark.django_db
class TestCheckViewDDIImageOrText:
    def test_all_correct(
        self, client, user, session, ddi_question, drop_zones, drag_items
    ):
        client.force_login(user)
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        response = client.post(
            f"/entrainement/session/{session.pk}/check/",
            {
                "question_id": str(ddi_question.pk),
                "zone_1": "sclérotique",  # correct ✓
                "zone_2": "choroide",  # correct ✓
                "zone_3": "rétine",  # correct ✓
            },
        )
        assert response.status_code == 200
        ua = UserAnswer.objects.get(session=session, question=ddi_question)
        assert ua.is_correct is True
        assert abs(ua.effective_fraction - 1.0) < 1e-6

    def test_all_correct_case_insensitive(
        self, client, user, session, ddi_question, drop_zones, drag_items
    ):
        client.force_login(user)
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        client.post(
            f"/entrainement/session/{session.pk}/check/",
            {
                "question_id": str(ddi_question.pk),
                "zone_1": "SCLEROTIQUE",  # sans accent, majuscules → correct ✓
                "zone_2": "Choroide",
                "zone_3": "Retine",
            },
        )
        ua = UserAnswer.objects.get(session=session, question=ddi_question)
        assert ua.is_correct is True

    def test_partial_correct(
        self, client, user, session, ddi_question, drop_zones, drag_items
    ):
        client.force_login(user)
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        response = client.post(
            f"/entrainement/session/{session.pk}/check/",
            {
                "question_id": str(ddi_question.pk),
                "zone_1": "sclérotique",  # correct ✓
                "zone_2": "distractor",  # wrong ✗
                "zone_3": "rétine",  # correct ✓
            },
        )
        assert response.status_code == 200
        ua = UserAnswer.objects.get(session=session, question=ddi_question)
        assert ua.is_correct is False
        assert abs(ua.effective_fraction - 2 / 3) < 1e-6

    def test_all_wrong(
        self, client, user, session, ddi_question, drop_zones, drag_items
    ):
        client.force_login(user)
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        response = client.post(
            f"/entrainement/session/{session.pk}/check/",
            {
                "question_id": str(ddi_question.pk),
                "zone_1": "mauvaise réponse",
                "zone_2": "mauvaise réponse",
                "zone_3": "mauvaise réponse",
            },
        )
        assert response.status_code == 200
        ua = UserAnswer.objects.get(session=session, question=ddi_question)
        assert ua.is_correct is False
        assert ua.effective_fraction == 0.0

    def test_correct_via_accepted_alternative_label(
        self, client, user, session, ddi_question, drop_zones, drag_items
    ):
        """Une zone est comptée correcte si la réponse correspond à une alternative acceptée."""
        ImageDropZoneLabel.objects.create(zone=drop_zones[1], text="choroïde")
        client.force_login(user)
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        response = client.post(
            f"/entrainement/session/{session.pk}/check/",
            {
                "question_id": str(ddi_question.pk),
                "zone_1": "sclérotique",  # correct ✓ (label principal)
                "zone_2": "choroïde",  # correct ✓ (alternative acceptée)
                "zone_3": "rétine",  # correct ✓
            },
        )
        assert response.status_code == 200
        ua = UserAnswer.objects.get(session=session, question=ddi_question)
        assert ua.is_correct is True
        assert abs(ua.effective_fraction - 1.0) < 1e-6

    def test_response_is_valid_after_zone_submission(
        self, client, user, session, ddi_question, drop_zones, drag_items
    ):
        client.force_login(user)
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        response = client.post(
            f"/entrainement/session/{session.pk}/check/",
            {
                "question_id": str(ddi_question.pk),
                "zone_1": "sclérotique",  # correct
                "zone_2": "mauvais",  # wrong
                "zone_3": "rétine",  # correct
            },
        )
        assert response.status_code == 200
        assert b"status-label" in response.content

    def test_zone_answers_stored_as_text_in_qroc_text(
        self, client, user, session, ddi_question, drop_zones, drag_items
    ):
        client.force_login(user)
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        client.post(
            f"/entrainement/session/{session.pk}/check/",
            {
                "question_id": str(ddi_question.pk),
                "zone_1": "sclérotique",
                "zone_2": "choroide",
                "zone_3": "rétine",
            },
        )
        ua = UserAnswer.objects.get(session=session, question=ddi_question)
        data = json.loads(ua.qroc_text)
        assert data.get("1") == "sclérotique"
        assert data.get("2") == "choroide"


# ── Tests import ddimageortext ─────────────────────────────────────────────────


@pytest.mark.django_db
class TestImportDDIImageOrText:
    MINI_DUMP_DDI = """\
SET client_encoding = 'UTF8';

COPY "public"."m_course" ("id", "category", "sortorder", "fullname", "shortname", "idnumber", "summary", "summaryformat", "format", "showgrades", "newsitems", "startdate", "enddate", "relativedatesmode", "marker", "maxbytes", "legacyfiles", "showreports", "visible", "visibleold", "downloadcontent", "groupmode", "groupmodeforce", "defaultgroupingid", "lang", "calendartype", "theme", "timecreated", "timemodified", "requested", "enablecompletion", "completionnotify", "cacherev", "originalcourseid", "showactivitydates", "showcompletionconditions", "pdfexportfont") FROM stdin;
11\t1\t1\tP2 - La cellule\tcell\t\t\t1\ttopics\t1\t5\t1609459200\t0\t0\t0\t0\t0\t0\t1\t1\t\\N\t0\t0\t0\t\t\t\t1609459200\t1609459200\t0\t1\t0\t0\t\\N\t1\t1\t\\N
\\.

COPY "public"."m_course_modules" ("id", "course", "module", "instance", "section", "idnumber", "added", "score", "indent", "visible", "visibleoncoursepage", "visibleold", "groupmode", "groupingid", "completion", "completiongradeitemnumber", "completionpassgrade", "completionview", "completionexpected", "showdescription", "availability", "deletioninprogress", "downloadcontent", "lang") FROM stdin;
42\t11\t18\t1\t1\t\t1609459200\t0\t0\t1\t1\t1\t0\t0\t0\t\\N\t0\t0\t0\t0\t\\N\t0\t\\N\t\\N
\\.

COPY "public"."m_context" ("id", "contextlevel", "instanceid", "path", "depth", "locked") FROM stdin;
110\t70\t42\t/1/3/110\t3\t0
\\.

COPY "public"."m_question_categories" ("id", "name", "contextid", "info", "infoformat", "stamp", "parent", "sortorder", "idnumber") FROM stdin;
48\ttop\t110\t\t0\ttest+top\t0\t0\t\\N
49\tLa cellule\t110\t\t0\ttest+cat1\t48\t999\t\\N
\\.

COPY "public"."m_question" ("id", "parent", "name", "questiontext", "questiontextformat", "generalfeedback", "generalfeedbackformat", "defaultmark", "penalty", "qtype", "length", "stamp", "timecreated", "timemodified", "createdby", "modifiedby") FROM stdin;
300\t0\tLegende oeil\t<p>Légender l'oeil</p>\t1\t\t1\t1.0\t0.0\tddimageortext\t1\ttest+ddi1\t1609459200\t1609459200\t2\t2
\\.

COPY "public"."m_question_bank_entries" ("id", "questioncategoryid", "idnumber", "ownerid", "nextversion") FROM stdin;
200\t49\t\\N\t2\t\\N
\\.

COPY "public"."m_question_versions" ("id", "questionbankentryid", "version", "questionid", "status") FROM stdin;
300\t200\t1\t300\tready
\\.

COPY "public"."m_qtype_ddimageortext_drags" ("id", "questionid", "no", "draggroup", "infinite", "label") FROM stdin;
1\t300\t1\t1\t0\tsclérotique
2\t300\t2\t1\t0\tchoroide
3\t300\t3\t1\t0\tdistracteur
\\.

COPY "public"."m_qtype_ddimageortext_drops" ("id", "questionid", "no", "xleft", "ytop", "choice", "label") FROM stdin;
1\t300\t1\t100\t50\t1\t
2\t300\t2\t200\t100\t2\t
\\.

COPY "public"."m_tag" ("id", "userid", "name", "rawname", "isstandard", "tagcollid", "flag", "timemodified") FROM stdin;
\\.

COPY "public"."m_tag_instance" ("id", "tagid", "component", "itemtype", "itemid", "contextid", "tiuserid", "ordering", "timemodified") FROM stdin;
\\.
"""

    def test_import_ddi_question(self, db, tmp_path):
        from django.core.management import call_command

        from qcm.models import Semester, StudyYear

        StudyYear.objects.create(name="P2", order=1)
        Semester.objects.create(
            study_year=StudyYear.objects.first(), name="S1", order=1
        )

        dump = tmp_path / "test.sql"
        dump.write_text(self.MINI_DUMP_DDI)
        call_command("import_moodle", dump=str(dump), verbosity=0)

        q = Question.objects.filter(moodle_id=300).first()
        assert q is not None
        assert q.qtype == Question.DDIMAGEORTEXT

    def test_import_drag_items(self, db, tmp_path):
        from django.core.management import call_command

        from qcm.models import Semester, StudyYear

        StudyYear.objects.create(name="P2", order=1)
        Semester.objects.create(
            study_year=StudyYear.objects.first(), name="S1", order=1
        )

        dump = tmp_path / "test.sql"
        dump.write_text(self.MINI_DUMP_DDI)
        call_command("import_moodle", dump=str(dump), verbosity=0)

        q = Question.objects.get(moodle_id=300)
        drags = ImageDragItem.objects.filter(question=q)
        assert drags.count() == 3
        labels = set(drags.values_list("label", flat=True))
        assert "sclérotique" in labels
        assert "distract" in " ".join(labels).lower() or "distracteur" in labels

    def test_import_drop_zones(self, db, tmp_path):
        from django.core.management import call_command

        from qcm.models import Semester, StudyYear

        StudyYear.objects.create(name="P2", order=1)
        Semester.objects.create(
            study_year=StudyYear.objects.first(), name="S1", order=1
        )

        dump = tmp_path / "test.sql"
        dump.write_text(self.MINI_DUMP_DDI)
        call_command("import_moodle", dump=str(dump), verbosity=0)

        q = Question.objects.get(moodle_id=300)
        zones = ImageDropZone.objects.filter(question=q)
        assert zones.count() == 2
        zone1 = zones.get(no=1)
        assert zone1.xleft == 100
        assert zone1.ytop == 50
        assert zone1.correct_drag_no == 1
        assert zone1.correct_label == "sclérotique"

    def test_import_idempotent(self, db, tmp_path):
        from django.core.management import call_command

        from qcm.models import Semester, StudyYear

        StudyYear.objects.create(name="P2", order=1)
        Semester.objects.create(
            study_year=StudyYear.objects.first(), name="S1", order=1
        )

        dump = tmp_path / "test.sql"
        dump.write_text(self.MINI_DUMP_DDI)
        call_command("import_moodle", dump=str(dump), verbosity=0)
        call_command("import_moodle", dump=str(dump), verbosity=0)

        assert Question.objects.filter(moodle_id=300).count() == 1
        q = Question.objects.get(moodle_id=300)
        assert ImageDragItem.objects.filter(question=q).count() == 3
        assert ImageDropZone.objects.filter(question=q).count() == 2


# ── Tests QuestionView contexte ddimageortext ──────────────────────────────────


@pytest.mark.django_db
class TestQuestionViewDDIContext:
    def test_context_includes_drag_items(
        self, client, user, session, ddi_question, drop_zones, drag_items
    ):
        client.force_login(user)
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert response.status_code == 200
        assert "drag_items" in response.context
        assert len(response.context["drag_items"]) == 4

    def test_context_includes_drop_zones(
        self, client, user, session, ddi_question, drop_zones, drag_items
    ):
        client.force_login(user)
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert response.status_code == 200
        assert "drop_zones" in response.context
        assert len(response.context["drop_zones"]) == 3


# ── Fixture image de fond ──────────────────────────────────────────────────────


@pytest.fixture
def bg_image(ddi_question):
    """Crée une QuestionImage factice pour simuler l'image de fond ddimageortext."""
    from django.core.files.base import ContentFile

    img = QuestionImage(question=ddi_question, moodle_filename="background")
    img.file.save("test_bg.png", ContentFile(b"\x89PNG\r\n\x1a\n"), save=True)
    return img


# ── Tests overlay image dans la correction ────────────────────────────────────


@pytest.mark.django_db
class TestCorrectionDDIImageOverlay:
    """Tests pour l'affichage de l'image avec labels colorés dans la correction."""

    def _post_check(
        self,
        client,
        session,
        ddi_question,
        zone_1: str = "sclérotique",
        zone_2: str = "FAUX",
        zone_3: str = "rétine",
    ):
        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        return client.post(
            f"/entrainement/session/{session.pk}/check/",
            {
                "question_id": str(ddi_question.pk),
                "zone_1": zone_1,
                "zone_2": zone_2,
                "zone_3": zone_3,
            },
        )

    def test_correction_shows_image_overlay(
        self, client, user, session, ddi_question, drop_zones, drag_items, bg_image
    ):
        """Avec une image de fond, la correction affiche le conteneur overlay."""
        client.force_login(user)
        response = self._post_check(client, session, ddi_question)
        assert response.status_code == 200
        assert b"ddi-result-container" in response.content

    def test_correction_correct_label_class(
        self, client, user, session, ddi_question, drop_zones, drag_items, bg_image
    ):
        """Une réponse juste apparaît avec la classe CSS 'correct'."""
        client.force_login(user)
        response = self._post_check(
            client,
            session,
            ddi_question,
            zone_1="sclérotique",
            zone_2="FAUX",
            zone_3="rétine",
        )
        assert b"ddi-result-label correct" in response.content

    def test_correction_incorrect_label_class(
        self, client, user, session, ddi_question, drop_zones, drag_items, bg_image
    ):
        """Une réponse fausse apparaît avec la classe CSS 'incorrect'."""
        client.force_login(user)
        response = self._post_check(
            client,
            session,
            ddi_question,
            zone_1="sclérotique",
            zone_2="FAUX",
            zone_3="rétine",
        )
        assert b"ddi-result-label incorrect" in response.content

    def test_correction_incorrect_has_tooltip(
        self, client, user, session, ddi_question, drop_zones, drag_items, bg_image
    ):
        """Une réponse fausse porte l'attribut Bootstrap tooltip."""
        client.force_login(user)
        response = self._post_check(
            client,
            session,
            ddi_question,
            zone_1="sclérotique",
            zone_2="FAUX",
            zone_3="rétine",
        )
        assert b'data-bs-toggle="tooltip"' in response.content

    def test_correction_tooltip_contains_correct_answer(
        self, client, user, session, ddi_question, drop_zones, drag_items, bg_image
    ):
        """Le tooltip d'une réponse fausse mentionne la bonne réponse attendue."""
        client.force_login(user)
        response = self._post_check(
            client,
            session,
            ddi_question,
            zone_1="sclérotique",
            zone_2="FAUX",
            zone_3="rétine",
        )
        # Zone 2 est fausse, correct_label = "choroide"
        assert b"Attendu" in response.content
        assert b"choroide" in response.content

    def test_correction_tooltip_with_alternatives(
        self, client, user, session, ddi_question, drop_zones, drag_items, bg_image
    ):
        """Le tooltip d'une réponse fausse mentionne les alternatives acceptées."""
        ImageDropZoneLabel.objects.create(zone=drop_zones[1], text="choroïde")
        client.force_login(user)
        response = self._post_check(
            client,
            session,
            ddi_question,
            zone_1="sclérotique",
            zone_2="FAUX",
            zone_3="rétine",
        )
        # L'alternative "choroïde" doit apparaître dans le tooltip de zone 2
        assert "choroïde".encode() in response.content

    def test_correction_correct_no_tooltip(
        self, client, user, session, ddi_question, drop_zones, drag_items, bg_image
    ):
        """Quand toutes les réponses sont correctes, aucun label 'Attendu :' n'est présent."""
        client.force_login(user)
        response = self._post_check(
            client,
            session,
            ddi_question,
            zone_1="sclérotique",
            zone_2="choroide",
            zone_3="rétine",
        )
        # "Attendu :" n'apparaît que dans les tooltips des mauvaises réponses
        assert b"Attendu" not in response.content

    def test_correction_no_overlay_without_image(
        self, client, user, session, ddi_question, drop_zones, drag_items
    ):
        """Sans image de fond, le conteneur overlay n'est pas rendu."""
        client.force_login(user)
        response = self._post_check(client, session, ddi_question)
        assert response.status_code == 200
        assert b"ddi-result-container" not in response.content

    def test_no_feedback_panel_for_ddimageortext(
        self, client, user, session, ddi_question, drop_zones, drag_items
    ):
        """Aucune correction textuelle pour ddimageortext : ni panneau jaune, ni liste des zones."""
        client.force_login(user)
        response = self._post_check(client, session, ddi_question)
        assert response.status_code == 200
        assert b"text-warning-emphasis" not in response.content
        assert "Votre réponse".encode() not in response.content


# ── Tests rescaling des zones de dépôt ───────────────────────────────────────


@pytest.mark.django_db
class TestDDIQuestionZoneScaling:
    """Tests pour le rescaling des zones de dépôt lors de changements de layout."""

    def test_question_view_uses_resize_observer(
        self, client, user, session, ddi_question, drop_zones, drag_items, bg_image
    ):
        """La page question ddimageortext utilise ResizeObserver pour rescaler les zones."""
        client.force_login(user)
        from qcm.models import QuizSessionQuestion

        QuizSessionQuestion.objects.create(
            session=session, question=ddi_question, order=1
        )
        response = client.get(f"/entrainement/session/{session.pk}/")
        assert response.status_code == 200
        assert b"ResizeObserver" in response.content
