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

    def _extract_media_zip(self, zip_path: Path):
        if not zip_path.exists():
            raise CommandError(f"Archive média introuvable : {zip_path}")

        self.stdout.write(f"Extraction de {zip_path} vers {settings.MEDIA_ROOT}")
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                if member.startswith("/") or ".." in Path(member).parts:
                    raise CommandError(f"Entrée d'archive suspecte : {member}")
            archive.extractall(settings.MEDIA_ROOT)
