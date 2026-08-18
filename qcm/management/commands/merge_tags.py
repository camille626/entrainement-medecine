"""Management command: merge/convert/remove EC tags scoped to a single course (issue #108)."""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from qcm.models import Course, Question, Tag
from qcm.tag_merging import TagMergeError, convert_tag_to_chapter, merge_course_tags


REQUIRED_OPTIONS = {
    "merge": ["from_tag", "to_tag"],
    "convert-to-chapter": ["tag", "parent_ec"],
    "remove": ["tag"],
}


def _resolve_course(name: str) -> Course:
    name = name.strip()
    exact = Course.objects.filter(name=name)
    if exact.count() == 1:
        return exact.get()

    fuzzy = Course.objects.filter(name__icontains=name)
    count = fuzzy.count()
    if count == 0:
        raise CommandError(f"Cours introuvable : '{name}'.")
    if count > 1:
        matches = ", ".join(repr(c.name) for c in fuzzy)
        raise CommandError(
            f"Plusieurs cours correspondent à '{name}' : {matches}. "
            "Précisez un nom plus spécifique."
        )
    return fuzzy.get()


def _resolve_tag(name: str) -> Tag:
    try:
        return Tag.objects.get(name=name)
    except Tag.DoesNotExist as exc:
        raise CommandError(f"Tag introuvable : '{name}'.") from exc


class Command(BaseCommand):
    help = (
        "Merge, convert-to-chapter, or remove EC/chapter tags scoped to a single "
        "course (issue #108). Idempotent — chaque action peut être relancée sans "
        "effet de bord."
    )

    def add_arguments(self, parser):
        parser.add_argument("action", choices=list(REQUIRED_OPTIONS))
        parser.add_argument(
            "--course", required=True, help="Nom (ou fragment) du cours"
        )
        parser.add_argument("--from-tag", default=None, help="[merge] tag source")
        parser.add_argument("--to-tag", default=None, help="[merge] tag cible")
        parser.add_argument(
            "--tag",
            default=None,
            help="[convert-to-chapter|remove] tag concerné",
        )
        parser.add_argument(
            "--parent-ec",
            default=None,
            help="[convert-to-chapter] tag EC à assigner comme parent",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Prévisualise les changements sans modifier la base",
        )

    def handle(self, *args, **options):
        action = options["action"]
        course = _resolve_course(options["course"])

        missing = [
            f"--{opt.replace('_', '-')}"
            for opt in REQUIRED_OPTIONS[action]
            if not options.get(opt)
        ]
        if missing:
            raise CommandError(f"L'action '{action}' nécessite : {', '.join(missing)}.")

        dry_run = options["dry_run"]
        try:
            if action == "merge":
                self._merge(course, options["from_tag"], options["to_tag"], dry_run)
            elif action == "convert-to-chapter":
                self._convert_to_chapter(
                    course, options["tag"], options["parent_ec"], dry_run
                )
            else:
                self._remove(course, options["tag"], dry_run)
        except TagMergeError as exc:
            raise CommandError(str(exc)) from exc

    def _merge(self, course, from_tag_name, to_tag_name, dry_run):
        from_tag = _resolve_tag(from_tag_name)
        to_tag = _resolve_tag(to_tag_name)

        result = merge_course_tags(course, from_tag, to_tag, dry_run=dry_run)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] merge '{from_tag.name}' -> '{to_tag.name}' "
                    f"({course.name}) : {result.questions_migrated} question(s), "
                    f"reparent {result.reparented_tags}"
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"merge '{from_tag.name}' -> '{to_tag.name}' ({course.name}) : "
                f"{result.questions_migrated} question(s) migrée(s), "
                f"{len(result.reparented_tags)} tag(s)-chapitres reparenté(s)."
            )
        )

    def _convert_to_chapter(self, course, tag_name, parent_ec_name, dry_run):
        tag = _resolve_tag(tag_name)
        parent_tag = _resolve_tag(parent_ec_name)

        result = convert_tag_to_chapter(course, tag, parent_tag, dry_run=dry_run)

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] convert-to-chapter '{tag.name}' ({course.name}), "
                    f"parent_ec='{parent_tag.name}' : "
                    f"{result.questions_updated} question(s) recevraient "
                    f"'{parent_tag.name}'."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"'{tag.name}' converti en chapitre de '{parent_tag.name}' "
                f"({course.name}) : {result.questions_updated} question(s) "
                "mise(s) à jour."
            )
        )

    def _remove(self, course, tag_name, dry_run):
        tag = _resolve_tag(tag_name)
        questions = list(Question.objects.filter(course=course, tags=tag))

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] remove '{tag.name}' ({course.name}) : "
                    f"{len(questions)} question(s) perdraient ce tag."
                )
            )
            return

        with transaction.atomic():
            for q in questions:
                q.tags.remove(tag)

        self.stdout.write(
            self.style.SUCCESS(
                f"remove '{tag.name}' ({course.name}) : {len(questions)} "
                "question(s) mise(s) à jour (tag global conservé)."
            )
        )
