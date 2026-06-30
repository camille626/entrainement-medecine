"""Management command: one-shot import of a dumpdata JSON fixture plus media files.

Pour migrer les données d'un déploiement existant (ex: SQLite local) vers un
nouveau déploiement (ex: NAS via Docker) sans dupliquer les fichiers médias
binaires dans le dump JSON de `dumpdata`.
"""

import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


def _zip_strip_prefix(members: list[str]) -> str:
    """Détecte un répertoire wrapper commun à tous les membres du zip et le retourne.

    Retourne 'media/' si tous les chemins commencent par 'media/' ET que ce
    dossier contient lui-même des sous-répertoires (donc c'est bien un wrapper,
    pas un dossier de contenu comme 'question_images/').

    Cela permet de gérer les archives créées avec `zip -r media.zip media/`
    qui produisent des chemins préfixés (media/question_images/foo.jpg) au lieu
    des chemins directs attendus (question_images/foo.jpg).
    Retourne '' dans tous les autres cas (pas de strip).
    """
    if not members:
        return ""
    tops = {m.split("/")[0] for m in members if m}
    if len(tops) == 1:
        prefix = tops.pop() + "/"
        # Ne strip que si le dossier top-level contient des sous-répertoires
        # (c'est un wrapper), pas s'il est lui-même un dossier de contenu direct.
        sub_paths = [
            m[len(prefix) :]
            for m in members
            if m.startswith(prefix) and m[len(prefix) :]
        ]
        has_subdirs = any("/" in sub for sub in sub_paths)
        if has_subdirs and all(m.startswith(prefix) for m in members):
            return prefix
    return ""


class Command(BaseCommand):
    help = (
        "Charge un fixture JSON (dumpdata) et extrait optionnellement une "
        "archive zip de fichiers médias dans MEDIA_ROOT. À lancer une seule "
        "fois sur une base vierge."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixture",
            required=True,
            help="Chemin du fixture JSON (généré par `manage.py dumpdata`)",
        )
        parser.add_argument(
            "--media-zip",
            default=None,
            help="Chemin d'une archive zip à extraire dans MEDIA_ROOT",
        )

    def handle(self, *args, **options):
        fixture_path = Path(options["fixture"])
        if not fixture_path.exists():
            raise CommandError(f"Fixture introuvable : {fixture_path}")

        media_zip = options.get("media_zip")
        if media_zip:
            self._extract_media_zip(Path(media_zip))

        self.stdout.write(f"Chargement de {fixture_path}")
        call_command("loaddata", str(fixture_path))

        self.stdout.write(self.style.SUCCESS("Import terminé."))

    def _extract_media_zip(self, zip_path: Path) -> None:
        if not zip_path.exists():
            raise CommandError(f"Archive média introuvable : {zip_path}")

        self.stdout.write(f"Extraction de {zip_path} vers {settings.MEDIA_ROOT}")
        media_root = Path(settings.MEDIA_ROOT)

        with zipfile.ZipFile(zip_path) as archive:
            members = archive.namelist()
            for member in members:
                if member.startswith("/") or ".." in Path(member).parts:
                    raise CommandError(f"Entrée d'archive suspecte : {member}")

            prefix = _zip_strip_prefix(members)

            for info in archive.infolist():
                target_path = info.filename[len(prefix) :]
                if not target_path:
                    continue
                target = media_root / target_path
                if info.filename.endswith("/"):
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(info.filename))
