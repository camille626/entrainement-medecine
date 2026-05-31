"""Django management command to import Moodle data into QCM models."""

from django.core.management.base import BaseCommand

from qcm.models import Answer, Category, Course, Question, Semester

from .moodle_parser import build_context_to_course, parse_sql_dump


COURSE_IDS = {11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}
DEFAULT_DUMP = "data/raw/plateforme-medecine_moodlecloud.sql"

S1_MOODLE_IDS = {11, 12, 13, 14, 15, 16, 17, 18}
S2_MOODLE_IDS = {19, 20, 21, 22, 23}


class Command(BaseCommand):
    help = "Import Moodle questions into the QCM database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dump",
            default=DEFAULT_DUMP,
            help="Path to the Moodle PostgreSQL dump file",
        )

    def handle(self, *args, **options):
        dump_path = options["dump"]
        self.stdout.write(f"Parsing dump: {dump_path}")
        data = parse_sql_dump(dump_path)

        courses_created = self._import_courses(data)
        context_to_course = build_context_to_course(data)
        cats_created = self._import_categories(data, context_to_course)
        questions_created = self._import_questions(data)
        answers_created = self._import_answers(data)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nImport terminé :\n"
                f"  Cours       : {courses_created} créés\n"
                f"  Catégories  : {cats_created} créées\n"
                f"  Questions   : {questions_created} créées\n"
                f"  Réponses    : {answers_created} créées"
            )
        )

    def _get_semester(self, moodle_id: int) -> "Semester | None":
        if moodle_id in S1_MOODLE_IDS:
            return Semester.objects.filter(study_year__name="P2", name="S1").first()
        if moodle_id in S2_MOODLE_IDS:
            return Semester.objects.filter(study_year__name="P2", name="S2").first()
        return None

    def _import_courses(self, data: dict) -> int:
        created = 0
        for row in data.get("m_course", []):
            moodle_id = int(row["id"])
            if moodle_id not in COURSE_IDS:
                continue
            semester = self._get_semester(moodle_id)
            _, is_new = Course.objects.update_or_create(
                moodle_id=moodle_id,
                defaults={
                    "name": row["fullname"],
                    "short_name": row["shortname"],
                    "semester": semester,
                },
            )
            if is_new:
                created += 1
        return created

    def _import_categories(self, data: dict, context_to_course: dict[int, int]) -> int:
        created = 0
        for row in data.get("m_question_categories", []):
            if row["name"] == "top":
                continue
            context_id = int(row["contextid"])
            if context_id not in context_to_course:
                continue
            course_moodle_id = context_to_course[context_id]
            try:
                course = Course.objects.get(moodle_id=course_moodle_id)
            except Course.DoesNotExist:
                continue
            _, is_new = Category.objects.get_or_create(
                moodle_id=int(row["id"]),
                defaults={"name": row["name"], "course": course},
            )
            if is_new:
                created += 1
        return created

    def _import_questions(self, data: dict) -> int:
        created = 0
        # Build category lookup: moodle_id → Category instance
        cat_by_moodle: dict[int, Category] = {
            c.moodle_id: c for c in Category.objects.all()
        }

        for row in data.get("m_question", []):
            if row.get("qtype") != "multichoice":
                continue
            # Find which category this question belongs to via m_question_bank_entries
            # Moodle doesn't store category directly on m_question — we need
            # m_question_bank_entries + m_question_versions to find the category.
            # Fallback: assign to first category of the right context via
            # m_question_categories using the stamp prefix (domain match).
            # Simpler approach: use question_bank_entries table if available.
            category = self._find_category_for_question(row, data, cat_by_moodle)
            if category is None:
                continue
            _, is_new = Question.objects.get_or_create(
                moodle_id=int(row["id"]),
                defaults={
                    "text": row.get("questiontext", ""),
                    "category": category,
                    "qtype": "multichoice",
                },
            )
            if is_new:
                created += 1
        return created

    def _find_category_for_question(
        self,
        question_row: dict,
        data: dict,
        cat_by_moodle: dict[int, Category],
    ) -> Category | None:
        """Link question to category via m_question_bank_entries."""
        q_id = str(question_row["id"])

        # m_question_bank_entries: id, questioncategoryid, ...
        # m_question_versions: questionbankentryid, questionid, ...
        versions = data.get("m_question_versions", [])
        entries = data.get("m_question_bank_entries", [])

        entry_by_id = {row["id"]: row for row in entries}

        for version in versions:
            if version.get("questionid") == q_id:
                entry_id = version.get("questionbankentryid")
                entry = entry_by_id.get(entry_id)
                if entry:
                    cat_moodle_id = int(entry["questioncategoryid"])
                    return cat_by_moodle.get(cat_moodle_id)
        return None

    def _import_answers(self, data: dict) -> int:
        created = 0
        q_by_moodle: dict[int, Question] = {
            q.moodle_id: q for q in Question.objects.all()
        }

        for row in data.get("m_question_answers", []):
            q_moodle_id = int(row["question"])
            question = q_by_moodle.get(q_moodle_id)
            if question is None:
                continue
            fraction = float(row.get("fraction", 0.0))
            _, is_new = Answer.objects.update_or_create(
                question=question,
                text=row.get("answer", ""),
                defaults={
                    "fraction": fraction,
                    "is_correct": fraction > 0.0,
                },
            )
            if is_new:
                created += 1
        return created
