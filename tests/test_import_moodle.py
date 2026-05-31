import pytest
from django.core.management import call_command

from qcm.models import Answer, Category, Course, Question


MINI_DUMP = """\
SET client_encoding = 'UTF8';
SET standard_conforming_strings = 'on';

COPY "public"."m_course" ("id", "category", "sortorder", "fullname", "shortname", "idnumber", "summary", "summaryformat", "format", "showgrades", "newsitems", "startdate", "enddate", "relativedatesmode", "marker", "maxbytes", "legacyfiles", "showreports", "visible", "visibleold", "downloadcontent", "groupmode", "groupmodeforce", "defaultgroupingid", "lang", "calendartype", "theme", "timecreated", "timemodified", "requested", "enablecompletion", "completionnotify", "cacherev", "originalcourseid", "showactivitydates", "showcompletionconditions", "pdfexportfont") FROM stdin;
11\t1\t1\tP2 - La cellule\tcell\t\t\t1\ttopics\t1\t5\t1609459200\t0\t0\t0\t0\t0\t0\t1\t1\t\\N\t0\t0\t0\t\t\t\t1609459200\t1609459200\t0\t1\t0\t0\t\\N\t1\t1\t\\N
8\t1\t2\tStarting with Moodle\tmoodle\t\t\t1\ttopics\t1\t5\t1609459200\t0\t0\t0\t0\t0\t0\t1\t1\t\\N\t0\t0\t0\t\t\t\t1609459200\t1609459200\t0\t1\t0\t0\t\\N\t1\t1\t\\N
\\.

COPY "public"."m_course_modules" ("id", "course", "module", "instance", "section", "idnumber", "added", "score", "indent", "visible", "visibleoncoursepage", "visibleold", "groupmode", "groupingid", "completion", "completiongradeitemnumber", "completionpassgrade", "completionview", "completionexpected", "showdescription", "availability", "deletioninprogress", "downloadcontent", "lang") FROM stdin;
42\t11\t18\t1\t1\t\t1609459200\t0\t0\t1\t1\t1\t0\t0\t0\t\\N\t0\t0\t0\t0\t\\N\t0\t\\N\t\\N
31\t8\t18\t2\t1\t\t1609459200\t0\t0\t1\t1\t1\t0\t0\t0\t\\N\t0\t0\t0\t0\t\\N\t0\t\\N\t\\N
\\.

COPY "public"."m_context" ("id", "contextlevel", "instanceid", "path", "depth", "locked") FROM stdin;
110\t70\t42\t/1/3/110\t3\t0
83\t70\t31\t/1/3/83\t3\t0
109\t50\t11\t/1/109\t2\t0
81\t50\t8\t/1/81\t2\t0
\\.

COPY "public"."m_question_categories" ("id", "name", "contextid", "info", "infoformat", "stamp", "parent", "sortorder", "idnumber") FROM stdin;
48\ttop\t110\t\t0\ttest+top\t0\t0\t\\N
49\tDefault for P2 - La cellule course question bank\t110\t\t0\ttest+cat1\t48\t999\t\\N
50\tEntrainement cytosquelette\t110\t\t0\ttest+cat2\t48\t999\t\\N
51\ttop\t83\t\t0\ttest+top2\t0\t0\t\\N
\\.

COPY "public"."m_question" ("id", "parent", "name", "questiontext", "questiontextformat", "generalfeedback", "generalfeedbackformat", "defaultmark", "penalty", "qtype", "length", "stamp", "timecreated", "timemodified", "createdby", "modifiedby") FROM stdin;
200\t0\tQ1\t<p>À propos de la membrane plasmique :</p>\t1\t\t1\t1.0000000\t0.3333333\tmultichoice\t1\ttest+q1\t1609459200\t1609459200\t2\t2
201\t0\tQ2\t<p>À propos du cytosquelette :</p>\t1\t\t1\t1.0000000\t0.3333333\tmultichoice\t1\ttest+q2\t1609459200\t1609459200\t2\t2
202\t0\tQ3\t<p>Question texte court :</p>\t1\t\t1\t1.0000000\t0.3333333\tshortanswer\t1\ttest+q3\t1609459200\t1609459200\t2\t2
\\.

COPY "public"."m_question_bank_entries" ("id", "questioncategoryid", "idnumber", "ownerid", "nextversion") FROM stdin;
100\t49\t\\N\t2\t\\N
101\t50\t\\N\t2\t\\N
102\t49\t\\N\t2\t\\N
\\.

COPY "public"."m_question_versions" ("id", "questionbankentryid", "version", "questionid", "status") FROM stdin;
200\t100\t1\t200\tready
201\t101\t1\t201\tready
202\t102\t1\t202\tready
\\.

COPY "public"."m_question_answers" ("id", "question", "answer", "answerformat", "fraction", "feedback", "feedbackformat") FROM stdin;
301\t200\t<p>Bicouche lipidique</p>\t1\t1.0000000\t\t1
302\t200\t<p>Monocouche lipidique</p>\t1\t0.0000000\t\t1
303\t200\t<p>Proposition partiellement correcte</p>\t1\t0.3333333\t\t1
304\t201\t<p>Actine et tubuline</p>\t1\t1.0000000\t\t1
305\t201\t<p>Collagène</p>\t1\t0.0000000\t\t1
306\t201\t<p>Réponse à moitié juste</p>\t1\t0.5000000\t\t1
\\.
"""


@pytest.fixture
def mini_dump(tmp_path):
    dump_file = tmp_path / "moodle_mini.sql"
    dump_file.write_text(MINI_DUMP, encoding="utf-8")
    return str(dump_file)


@pytest.mark.django_db
class TestImportMoodleCommand:
    def test_imports_correct_courses(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        assert Course.objects.count() == 1
        assert Course.objects.filter(name="P2 - La cellule").exists()

    def test_excludes_blocked_courses(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        assert not Course.objects.filter(name="Starting with Moodle").exists()

    def test_course_fields(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        course = Course.objects.get(moodle_id=11)
        assert course.name == "P2 - La cellule"
        assert course.short_name == "cell"

    def test_excludes_top_categories(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        assert not Category.objects.filter(name="top").exists()

    def test_imports_real_categories(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        assert Category.objects.count() == 2
        assert Category.objects.filter(
            name="Default for P2 - La cellule course question bank"
        ).exists()
        assert Category.objects.filter(name="Entrainement cytosquelette").exists()

    def test_categories_linked_to_course(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        course = Course.objects.get(moodle_id=11)
        assert Category.objects.filter(course=course).count() == 2

    def test_imports_multichoice_questions_only(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        assert Question.objects.count() == 2
        assert not Question.objects.filter(qtype="shortanswer").exists()

    def test_questions_linked_to_category(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        assert Question.objects.filter(moodle_id=200).exists()
        assert Question.objects.filter(moodle_id=201).exists()

    def test_imports_answers(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        assert Answer.objects.count() == 6

    def test_answer_is_correct_from_fraction(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        correct = Answer.objects.get(fraction=1.0, question__moodle_id=200)
        wrong = Answer.objects.get(fraction=0.0, question__moodle_id=200)
        assert correct.is_correct is True
        assert wrong.is_correct is False

    def test_partial_fraction_is_correct(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        partial_third = Answer.objects.get(
            question__moodle_id=200, text="<p>Proposition partiellement correcte</p>"
        )
        partial_half = Answer.objects.get(
            question__moodle_id=201, text="<p>Réponse à moitié juste</p>"
        )
        assert partial_third.is_correct is True
        assert partial_half.is_correct is True

    def test_idempotent(self, mini_dump):
        call_command("import_moodle", dump=mini_dump)
        call_command("import_moodle", dump=mini_dump)
        assert Course.objects.count() == 1
        assert Category.objects.count() == 2
        assert Question.objects.count() == 2
        assert Answer.objects.count() == 6
