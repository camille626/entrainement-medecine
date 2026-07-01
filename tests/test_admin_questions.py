"""Tests pour l'upload de questions Moodle XML (issue #34)."""

import pytest
from django.contrib.auth.models import User

from qcm.models import Course, Question, Semester, StudyYear


SAMPLE_XML = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b"<quiz>"
    b'<question type="multichoice">'
    b"<name><text>Q1</text></name>"
    b'<questiontext format="html"><text><![CDATA[<p>Is the sky blue?</p>]]></text></questiontext>'
    b'<generalfeedback format="html"><text><![CDATA[<p>Yes it is blue.</p>]]></text></generalfeedback>'
    b'<answer fraction="100" format="html"><text><![CDATA[<p>Yes</p>]]></text></answer>'
    b'<answer fraction="-100" format="html"><text><![CDATA[<p>No</p>]]></text></answer>'
    b"</question>"
    b'<question type="multichoice">'
    b"<name><text>Q2</text></name>"
    b'<questiontext format="html"><text><![CDATA[<p>Which are mammals?</p>]]></text></questiontext>'
    b'<generalfeedback format="html"><text></text></generalfeedback>'
    b'<answer fraction="33.33333" format="html"><text><![CDATA[<p>Dog</p>]]></text></answer>'
    b'<answer fraction="33.33333" format="html"><text><![CDATA[<p>Cat</p>]]></text></answer>'
    b'<answer fraction="33.33333" format="html"><text><![CDATA[<p>Whale</p>]]></text></answer>'
    b'<answer fraction="-100" format="html"><text><![CDATA[<p>Spider</p>]]></text></answer>'
    b"</question>"
    b'<question type="shortanswer">'
    b'<questiontext format="html"><text>Ignored type</text></questiontext>'
    b"</question>"
    b"</quiz>"
)

INVALID_XML = b"ceci n'est pas du XML valide <<<"


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="admin",
        password="pass",  # pragma: allowlist secret
        is_staff=True,
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username="student",
        password="pass",  # pragma: allowlist secret
        is_staff=False,
    )


@pytest.fixture
def course(db):
    year = StudyYear.objects.create(name="P2", order=1)
    semester = Semester.objects.create(name="S1", study_year=year, order=1)
    c = Course.objects.create(name="Cours test", moodle_id=9999)
    semester.courses.add(c)
    return c


# ── Parser ────────────────────────────────────────────────────────────────────


class TestParseMoodleXml:
    def test_returns_only_multichoice(self):
        from qcm.question_upload import parse_moodle_xml

        questions = parse_moodle_xml(SAMPLE_XML)
        assert len(questions) == 2  # shortanswer ignoré

    def test_question_text_extracted(self):
        from qcm.question_upload import parse_moodle_xml

        q = parse_moodle_xml(SAMPLE_XML)[0]
        assert "Is the sky blue" in q["text"]

    def test_feedback_extracted(self):
        from qcm.question_upload import parse_moodle_xml

        q = parse_moodle_xml(SAMPLE_XML)[0]
        assert "Yes it is blue" in q["feedback"]

    def test_answers_extracted(self):
        from qcm.question_upload import parse_moodle_xml

        q = parse_moodle_xml(SAMPLE_XML)[0]
        assert len(q["answers"]) == 2

    def test_fraction_100_converts_to_1(self):
        from qcm.question_upload import parse_moodle_xml

        q = parse_moodle_xml(SAMPLE_XML)[0]
        correct = next(a for a in q["answers"] if "Yes" in a["text"])
        assert correct["fraction"] == pytest.approx(1.0)

    def test_fraction_minus100_converts_to_minus1(self):
        from qcm.question_upload import parse_moodle_xml

        q = parse_moodle_xml(SAMPLE_XML)[0]
        wrong = next(a for a in q["answers"] if "No" in a["text"])
        assert wrong["fraction"] == pytest.approx(-1.0)

    def test_fraction_partial_converts_correctly(self):
        from qcm.question_upload import parse_moodle_xml

        q = parse_moodle_xml(SAMPLE_XML)[1]
        fracs = [a["fraction"] for a in q["answers"] if a["fraction"] > 0]
        assert all(abs(f - 1 / 3) < 0.001 for f in fracs)

    def test_invalid_xml_raises_value_error(self):
        from qcm.question_upload import parse_moodle_xml

        with pytest.raises(ValueError):
            parse_moodle_xml(INVALID_XML)

    def test_xml_tags_extracted(self):
        from qcm.question_upload import parse_moodle_xml

        xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b"<quiz>"
            b'<question type="multichoice">'
            b"<name><text>Q</text></name>"
            b'<questiontext format="html"><text>Question?</text></questiontext>'
            b'<generalfeedback format="html"><text></text></generalfeedback>'
            b'<answer fraction="100"><text>Yes</text></answer>'
            b'<answer fraction="-100"><text>No</text></answer>'
            b"<tags>"
            b"<tag><text>annale 2024</text></tag>"
            b"<tag><text>hemato</text></tag>"
            b"</tags>"
            b"</question>"
            b"</quiz>"
        )

        q = parse_moodle_xml(xml)[0]
        assert "annale 2024" in q["xml_tags"]
        assert "hemato" in q["xml_tags"]
        assert len(q["xml_tags"]) == 2

    def test_question_without_tags_has_empty_list(self):
        from qcm.question_upload import parse_moodle_xml

        q = parse_moodle_xml(SAMPLE_XML)[0]
        assert q["xml_tags"] == []


# ── Vues ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminQuestionsUploadView:
    def test_get_accessible_for_staff(self, client, staff_user):
        client.force_login(staff_user)
        response = client.get("/questions/upload/")
        assert response.status_code == 200

    def test_get_blocked_for_non_staff(self, client, regular_user):
        client.force_login(regular_user)
        response = client.get("/questions/upload/")
        assert response.status_code == 404

    def test_get_blocked_for_anonymous(self, client):
        response = client.get("/questions/upload/")
        assert response.status_code in (302, 404)

    def test_post_valid_xml_stores_in_session(self, client, staff_user):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(staff_user)
        xml_file = SimpleUploadedFile(
            "questions.xml", SAMPLE_XML, content_type="text/xml"
        )
        response = client.post("/questions/upload/", {"xml_file": xml_file})
        assert response.status_code == 302
        assert response["Location"] == "/questions/upload/preview/"
        session = client.session
        assert "upload_questions" in session
        assert len(session["upload_questions"]) == 2

    def test_post_invalid_xml_shows_error(self, client, staff_user):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(staff_user)
        xml_file = SimpleUploadedFile("bad.xml", INVALID_XML, content_type="text/xml")
        response = client.post("/questions/upload/", {"xml_file": xml_file})
        assert response.status_code == 200
        assert (
            b"invalide" in response.content.lower()
            or b"erreur" in response.content.lower()
        )


@pytest.mark.django_db
class TestAdminQuestionsPreviewView:
    def test_get_shows_questions_from_session(self, client, staff_user):
        client.force_login(staff_user)
        session = client.session
        session["upload_questions"] = [
            {
                "text": "<p>Q1</p>",
                "feedback": "",
                "answers": [
                    {"text": "A", "fraction": 1.0},
                    {"text": "B", "fraction": -1.0},
                ],
            }
        ]
        session.save()
        response = client.get("/questions/upload/preview/")
        assert response.status_code == 200
        assert b"Q1" in response.content

    def test_get_empty_session_redirects(self, client, staff_user):
        client.force_login(staff_user)
        response = client.get("/questions/upload/preview/")
        assert response.status_code == 302
        assert "/questions/upload/" in response["Location"]


@pytest.mark.django_db
class TestAdminQuestionsConfirmView:
    def test_confirm_creates_questions(self, client, staff_user, course):
        client.force_login(staff_user)
        data = {
            "course_id": str(course.pk),
            "q_count": "1",
            "q_0_text": "<p>Nouvelle question</p>",
            "q_0_feedback": "<p>Feedback</p>",
            "q_0_a_count": "2",
            "q_0_a_0_text": "Réponse A",
            "q_0_a_0_fraction": "1.0",
            "q_0_a_1_text": "Réponse B",
            "q_0_a_1_fraction": "-1.0",
        }
        response = client.post("/questions/confirmer/", data)
        assert response.status_code == 302
        assert Question.objects.filter(course=course).count() == 1

    def test_confirm_creates_answers(self, client, staff_user, course):
        client.force_login(staff_user)
        data = {
            "course_id": str(course.pk),
            "q_count": "1",
            "q_0_text": "<p>Question</p>",
            "q_0_feedback": "",
            "q_0_a_count": "2",
            "q_0_a_0_text": "Correcte",
            "q_0_a_0_fraction": "1.0",
            "q_0_a_1_text": "Fausse",
            "q_0_a_1_fraction": "-1.0",
        }
        client.post("/questions/confirmer/", data)
        q = Question.objects.get(course=course)
        assert q.answers.count() == 2
        assert q.answers.get(text="Correcte").fraction == pytest.approx(1.0)
        assert q.answers.get(text="Fausse").fraction == pytest.approx(-1.0)

    def test_confirm_moodle_id_is_none(self, client, staff_user, course):
        client.force_login(staff_user)
        data = {
            "course_id": str(course.pk),
            "q_count": "1",
            "q_0_text": "<p>Q</p>",
            "q_0_feedback": "",
            "q_0_a_count": "2",
            "q_0_a_0_text": "A",
            "q_0_a_0_fraction": "1.0",
            "q_0_a_1_text": "B",
            "q_0_a_1_fraction": "0.0",
        }
        client.post("/questions/confirmer/", data)
        q = Question.objects.get(course=course)
        assert q.moodle_id is None

    def test_confirm_clears_session(self, client, staff_user, course):
        client.force_login(staff_user)
        session = client.session
        session["upload_questions"] = [{"text": "x", "feedback": "", "answers": []}]
        session.save()
        data = {
            "course_id": str(course.pk),
            "q_count": "1",
            "q_0_text": "<p>Q</p>",
            "q_0_feedback": "",
            "q_0_a_count": "2",
            "q_0_a_0_text": "A",
            "q_0_a_0_fraction": "1.0",
            "q_0_a_1_text": "B",
            "q_0_a_1_fraction": "0.0",
        }
        client.post("/questions/confirmer/", data)
        assert "upload_questions" not in client.session
