"""Import question images from the Moodle dump into QuestionImage records."""

import shutil
from pathlib import Path
from urllib.parse import unquote

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from qcm.management.commands.moodle_parser import parse_sql_dump
from qcm.models import Errata, Notification, Question, QuestionImage


DEFAULT_DUMP = "data/raw/plateforme-medecine_moodlecloud.sql"
FILEDIR = Path("data/raw/moodledata/filedir")


def _build_image_map(data: dict) -> dict[str, list[tuple[str, str]]]:
    """Return {question_moodle_id: [(moodle_filename, contenthash), ...]}."""
    img_map: dict[str, list[tuple[str, str]]] = {}
    for f in data.get("m_files", []):
        if (
            (f.get("mimetype") or "").startswith("image/")
            and f.get("component") == "question"
            and f.get("filearea") == "questiontext"
            and f.get("filename") not in (".", None)
        ):
            img_map.setdefault(f["itemid"], []).append(
                (f["filename"], f["contenthash"])
            )
    return img_map


def _hash_to_path(base: Path, contenthash: str) -> Path:
    return base / contenthash[:2] / contenthash[2:4] / contenthash


class Command(BaseCommand):
    help = (
        "Import question images from the Moodle dump into QuestionImage records "
        "and close the corresponding IMAGE erratas."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dump",
            default=DEFAULT_DUMP,
            help="Path to the Moodle dump file",
        )
        parser.add_argument(
            "--filedir",
            default=str(FILEDIR),
            help="Path to moodledata/filedir",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview without copying files or writing to DB",
        )

    def handle(self, *args, **options):
        dump_path = options["dump"]
        filedir = Path(options["filedir"])
        dry_run = options["dry_run"]

        if not Path(dump_path).exists():
            raise CommandError(f"Dump introuvable : {dump_path}")
        if not filedir.exists():
            raise CommandError(f"filedir introuvable : {filedir}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("Mode dry-run — aucune modification.\n")
            )

        self.stdout.write("Parsing dump…")
        data = parse_sql_dump(dump_path)
        img_map = _build_image_map(data)
        self.stdout.write(f"  {len(img_map)} question(s) avec images dans le dump.")

        media_root = Path(settings.MEDIA_ROOT)
        dest_base = media_root / "question_images"
        if not dry_run:
            dest_base.mkdir(parents=True, exist_ok=True)

        imported = 0
        skipped_exists = 0
        skipped_no_file = 0
        erratas_closed = 0

        questions = (
            Question.objects.filter(text__contains="@@PLUGINFILE@@")
            .select_related("category")
            .prefetch_related("images")
        )

        for q in questions:
            q_id = str(q.moodle_id) if q.moodle_id else None
            if not q_id or q_id not in img_map:
                continue

            existing_filenames = {img.moodle_filename for img in q.images.all()}

            for moodle_filename, contenthash in img_map[q_id]:
                # URL-decode the filename for matching against @@PLUGINFILE@@ refs
                decoded_filename = unquote(moodle_filename)

                # Check if this image is actually referenced in the question text
                if decoded_filename not in q.text and moodle_filename not in q.text:
                    continue

                # Already imported?
                if (
                    decoded_filename in existing_filenames
                    or moodle_filename in existing_filenames
                ):
                    skipped_exists += 1
                    continue

                # Find the physical file
                src = _hash_to_path(filedir, contenthash)
                if not src.exists():
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Fichier manquant dans filedir: Q#{q.moodle_id} {moodle_filename}"
                        )
                    )
                    skipped_no_file += 1
                    continue

                # Destination: question_images/q<moodle_id>/<filename>
                dest_dir = dest_base / f"q{q.moodle_id}"
                dest_file = dest_dir / decoded_filename
                relative_path = f"question_images/q{q.moodle_id}/{decoded_filename}"

                if dry_run:
                    self.stdout.write(
                        f"  [dry-run] Q#{q.moodle_id} ← {moodle_filename} ({src.stat().st_size // 1024}KB)"
                    )
                    imported += 1
                    continue

                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest_file)

                QuestionImage.objects.update_or_create(
                    question=q,
                    moodle_filename=decoded_filename,
                    defaults={"file": relative_path},
                )
                imported += 1

                # Accept pending IMAGE errata for this question
                pending_erratas = Errata.objects.filter(
                    question=q,
                    error_type=Errata.IMAGE,
                    status=Errata.PENDING,
                )
                for errata in pending_erratas:
                    errata.status = Errata.ACCEPTED
                    errata.resolved_at = timezone.now()
                    errata.save(update_fields=["status", "resolved_at"])
                    Notification.objects.create(
                        user=errata.reported_by,
                        message=(
                            f"✅ L'image manquante sur la question #{q.moodle_id} "
                            f"a été importée automatiquement."
                        ),
                        link="/errata/",
                    )
                    erratas_closed += 1

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{imported} image(s) seraient importées "
                    f"({skipped_exists} déjà présentes, {skipped_no_file} fichiers manquants)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n{imported} image(s) importées, "
                    f"{erratas_closed} errata(s) fermés "
                    f"({skipped_exists} déjà présentes, {skipped_no_file} fichiers manquants)."
                )
            )
