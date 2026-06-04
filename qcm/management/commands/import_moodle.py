"""Django management command to import Moodle data into QCM models."""

from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from qcm.models import (
    Answer,
    Category,
    Course,
    ImageDragItem,
    ImageDropZone,
    Question,
    QuestionImage,
    Semester,
    Tag,
)

from .moodle_parser import build_context_to_course, parse_sql_dump


def _decode_pg_copy(text: str) -> str:
    """Decode PostgreSQL COPY escape sequences in text fields."""
    return (
        text.replace("\\r\\n", "<br>").replace("\\n", "<br>").replace("\\r", "").strip()
    )


COURSE_IDS = {11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}
DEFAULT_DUMP = "data/raw/plateforme-medecine_moodlecloud.sql"

S1_MOODLE_IDS = {11, 12, 13, 14, 15, 16, 17, 18}
S2_MOODLE_IDS = {19, 20, 21, 22, 23}

EXCLUDED_TAGS = {"le chat"}


class Command(BaseCommand):
    help = "Import Moodle questions into the QCM database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dump",
            default=DEFAULT_DUMP,
            help="Path to the Moodle PostgreSQL dump file",
        )
        parser.add_argument(
            "--moodledata",
            default=None,
            help="Path to the Moodle data directory (filedir) for background images",
        )

    def handle(self, *args, **options):
        dump_path = options["dump"]
        self.stdout.write(f"Parsing dump: {dump_path}")
        data = parse_sql_dump(dump_path)

        excluded_q_ids = self._compute_ai_only_question_ids(data)
        courses_created = self._import_courses(data)
        context_to_course = build_context_to_course(data)
        cats_created = self._import_categories(data, context_to_course)
        questions_created = self._import_questions(data, excluded_q_ids)
        answers_created = self._import_answers(data)
        tags_created, links_created = self._import_tags(data)
        drags_created, zones_created = self._import_ddimageortext_data(data)

        moodledata = options.get("moodledata")
        if moodledata is None:
            dump_dir = Path(dump_path).parent
            candidate = dump_dir / "moodledata" / "filedir"
            if candidate.exists():
                moodledata = str(dump_dir / "moodledata")
        images_created = 0
        if moodledata:
            images_created = self._import_ddimageortext_images(data, moodledata)

        self.stdout.write(
            self.style.SUCCESS(
                f"\nImport terminé :\n"
                f"  Cours       : {courses_created} créés\n"
                f"  Catégories  : {cats_created} créées\n"
                f"  Questions   : {questions_created} créées\n"
                f"  Réponses    : {answers_created} créées\n"
                f"  Tags        : {tags_created} créés, {links_created} liaisons\n"
                f"  Drag items  : {drags_created} créés\n"
                f"  Drop zones  : {zones_created} créées\n"
                f"  Images bg   : {images_created} créées"
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

    def _compute_ai_only_question_ids(self, data: dict) -> set[int]:
        """Return moodle_ids of questions tagged 'le chat' but not 'annale'."""
        tag_by_id = {row["id"]: row.get("rawname", "") for row in data.get("m_tag", [])}
        le_chat_ids = {k for k, v in tag_by_id.items() if v == "le chat"}
        annale_ids = {k for k, v in tag_by_id.items() if v == "annale"}

        q_tags: dict[str, set[str]] = {}
        for row in data.get("m_tag_instance", []):
            if row.get("itemtype") != "question":
                continue
            q_tags.setdefault(row["itemid"], set()).add(row["tagid"])

        return {
            int(qid)
            for qid, tags in q_tags.items()
            if le_chat_ids & tags and not (annale_ids & tags)
        }

    def _import_questions(
        self, data: dict, excluded_ids: set[int] | None = None
    ) -> int:
        created = 0
        excluded_ids = excluded_ids or set()
        cat_by_moodle: dict[int, Category] = {
            c.moodle_id: c for c in Category.objects.all()
        }

        supported_qtypes = {"multichoice", "shortanswer", "ddimageortext"}
        for row in data.get("m_question", []):
            qtype = row.get("qtype")
            if qtype not in supported_qtypes:
                continue
            if int(row["id"]) in excluded_ids:
                continue
            # Find which category this question belongs to via m_question_bank_entries
            category = self._find_category_for_question(row, data, cat_by_moodle)
            if category is None:
                continue
            raw_feedback = row.get("generalfeedback") or ""
            raw_text = row.get("questiontext") or ""
            feedback = _decode_pg_copy(raw_feedback)
            question_text = _decode_pg_copy(raw_text)
            _, is_new = Question.objects.update_or_create(
                moodle_id=int(row["id"]),
                defaults={
                    "text": question_text,
                    "feedback": feedback,
                    "category": category,
                    "qtype": qtype,
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
            answer_text = _decode_pg_copy(row.get("answer") or "")
            _, is_new = Answer.objects.update_or_create(
                question=question,
                text=answer_text,
                defaults={
                    "fraction": fraction,
                    "is_correct": fraction > 0.0,
                },
            )
            if is_new:
                created += 1
        return created

    def _import_tags(self, data: dict) -> tuple[int, int]:
        tags_created = 0
        links_created = 0

        tag_by_moodle: dict[int, Tag] = {}
        for row in data.get("m_tag", []):
            if row.get("rawname") in EXCLUDED_TAGS:
                continue
            moodle_id = int(row["id"])
            tag, is_new = Tag.objects.get_or_create(
                moodle_id=moodle_id,
                defaults={"name": row["rawname"]},
            )
            tag_by_moodle[moodle_id] = tag
            if is_new:
                tags_created += 1

        q_by_moodle: dict[int, Question] = {
            q.moodle_id: q for q in Question.objects.all()
        }

        q_to_tags: dict[int, list[Tag]] = {}
        for row in data.get("m_tag_instance", []):
            if row.get("itemtype") != "question":
                continue
            tag_moodle_id = int(row["tagid"])
            found_tag: Tag | None = tag_by_moodle.get(tag_moodle_id)
            if found_tag is None:
                continue
            q_moodle_id = int(row["itemid"])
            q_to_tags.setdefault(q_moodle_id, []).append(found_tag)

        for q_moodle_id, tags in q_to_tags.items():
            question = q_by_moodle.get(q_moodle_id)
            if question is None:
                continue
            question.tags.set(tags)
            links_created += len(tags)

        return tags_created, links_created

    def _import_ddimageortext_data(self, data: dict) -> tuple[int, int]:
        """Import drag items and drop zones for ddimageortext questions."""
        drags_created = 0
        zones_created = 0

        q_by_moodle: dict[int, Question] = {
            q.moodle_id: q
            for q in Question.objects.filter(qtype=Question.DDIMAGEORTEXT)
            if q.moodle_id is not None
        }

        # Import drag items — keyed by (questionid, drag_no)
        drag_by_moodle: dict[tuple[int, int], str] = {}
        for row in data.get("m_qtype_ddimageortext_drags", []):
            q_id = int(row["questionid"])
            question = q_by_moodle.get(q_id)
            if question is None:
                continue
            no = int(row["no"])
            label = _decode_pg_copy(row.get("label") or "")
            draggroup = int(row.get("draggroup") or 1)
            _, is_new = ImageDragItem.objects.update_or_create(
                question=question,
                no=no,
                defaults={"label": label, "draggroup": draggroup},
            )
            drag_by_moodle[(q_id, no)] = label
            if is_new:
                drags_created += 1

        # Import drop zones (need drag labels for correct_label)
        for row in data.get("m_qtype_ddimageortext_drops", []):
            q_id = int(row["questionid"])
            question = q_by_moodle.get(q_id)
            if question is None:
                continue
            no = int(row["no"])
            xleft = int(row.get("xleft") or 0)
            ytop = int(row.get("ytop") or 0)
            correct_drag_no = int(row.get("choice") or 0)
            correct_label = drag_by_moodle.get((q_id, correct_drag_no), "")
            _, is_new = ImageDropZone.objects.update_or_create(
                question=question,
                no=no,
                defaults={
                    "xleft": xleft,
                    "ytop": ytop,
                    "correct_drag_no": correct_drag_no,
                    "correct_label": correct_label,
                },
            )
            if is_new:
                zones_created += 1

        return drags_created, zones_created

    def _import_ddimageortext_images(self, data: dict, moodledata_dir: str) -> int:
        """Import background images for ddimageortext questions from moodledata/filedir."""
        filedir = Path(moodledata_dir) / "filedir"
        if not filedir.exists():
            self.stdout.write(
                self.style.WARNING(f"filedir not found at {filedir}, skipping images")
            )
            return 0

        q_by_moodle: dict[int, Question] = {
            q.moodle_id: q
            for q in Question.objects.filter(qtype=Question.DDIMAGEORTEXT)
            if q.moodle_id is not None
        }

        created = 0
        for row in data.get("m_files", []):
            if row.get("component") != "qtype_ddimageortext":
                continue
            filename = row.get("filename", "")
            if not filename or filename == "." or filename == "\\N":
                continue
            contenthash = row.get("contenthash", "")
            if not contenthash or len(contenthash) < 4:
                continue
            q_id_str = row.get("itemid")
            if not q_id_str:
                continue
            try:
                q_id = int(q_id_str)
            except (ValueError, TypeError):
                continue
            question = q_by_moodle.get(q_id)
            if question is None:
                continue

            src = filedir / contenthash[:2] / contenthash[2:4] / contenthash
            if not src.exists():
                continue

            existing = QuestionImage.objects.filter(
                question=question, moodle_filename=filename
            ).first()
            if existing:
                continue

            with open(src, "rb") as fh:
                qi = QuestionImage(question=question, moodle_filename=filename)
                qi.file.save(filename, ContentFile(fh.read()), save=True)
            created += 1

        return created
