"""Management command: create IMAGE erratas for questions with unresolved image refs."""

import re

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from qcm.models import Errata, Question


_IMG_SRC_RE = re.compile(r'<img\b[^>]*\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)


def _needs_image_errata(text: str) -> tuple[bool, str]:
    """Return (needs_errata, reason) for a question text.

    Skips:
    - base64-embedded images (already inline)
    - external http(s) URLs (resolve fine)
    Flags:
    - @@PLUGINFILE@@ references
    - relative paths (e.g. image.png without protocol or @@PLUGINFILE@@)
    """
    srcs = _IMG_SRC_RE.findall(text)
    broken = []
    for src in srcs:
        if src.startswith("data:"):
            continue  # base64 inline — OK
        if src.startswith(("http://", "https://")):
            continue  # external URL — OK
        broken.append(src)
    if broken:
        return True, f"Image(s) non résolue(s) : {', '.join(broken[:3])}"
    return False, ""


class Command(BaseCommand):
    help = (
        "Create IMAGE erratas for questions with unresolved <img> references "
        "(@@PLUGINFILE@@ or relative paths). Idempotent — skips existing erratas."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reporter",
            default=None,
            help="Username of the staff user to set as errata reporter (default: first superuser)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List questions that would get an errata without creating them",
        )

    def handle(self, *args, **options):
        # Resolve reporter user
        username = options["reporter"]
        if username:
            try:
                reporter = User.objects.get(username=username)
            except User.DoesNotExist as exc:
                raise CommandError(f"Utilisateur '{username}' introuvable.") from exc
        else:
            reporter = User.objects.filter(is_superuser=True).order_by("pk").first()
            if reporter is None:
                reporter = User.objects.filter(is_staff=True).order_by("pk").first()
            if reporter is None:
                raise CommandError(
                    "Aucun superuser trouvé. Utilisez --reporter <username>."
                )

        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("Mode dry-run — aucun errata créé.\n"))

        # Already-existing IMAGE erratas (to avoid duplicates)
        existing_q_ids = set(
            Errata.objects.filter(error_type=Errata.IMAGE).values_list(
                "question_id", flat=True
            )
        )

        candidates = Question.objects.filter(text__icontains="<img").select_related(
            "category__course"
        )

        created = 0
        skipped_ok = 0
        skipped_existing = 0

        for q in candidates:
            needs, reason = _needs_image_errata(q.text)
            if not needs:
                skipped_ok += 1
                continue
            if q.pk in existing_q_ids:
                skipped_existing += 1
                continue

            if dry_run:
                self.stdout.write(
                    f"  [dry-run] Q#{q.moodle_id or q.pk} "
                    f"({q.category.course.short_name}) — {reason}"
                )
            else:
                Errata.objects.create(
                    question=q,
                    reported_by=reporter,
                    error_type=Errata.IMAGE,
                    description=reason,
                )
            created += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{created} errata(s) seraient créés "
                    f"({skipped_existing} déjà existants, {skipped_ok} sans image cassée)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{created} errata(s) IMAGE créés "
                    f"({skipped_existing} déjà existants ignorés)."
                )
            )
