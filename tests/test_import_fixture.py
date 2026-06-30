import json
import zipfile

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from qcm.management.commands.import_fixture import _zip_strip_prefix
from qcm.models import Course


FIXTURE_DATA = [
    {
        "model": "qcm.course",
        "pk": 1,
        "fields": {"name": "Cours importé", "short_name": "imp"},
    }
]


@pytest.fixture
def fixture_file(tmp_path):
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(FIXTURE_DATA), encoding="utf-8")
    return str(path)


@pytest.fixture
def media_zip_file(tmp_path):
    path = tmp_path / "media.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("question_images/test.png", b"fake-png-bytes")
    return str(path)


@pytest.mark.django_db
class TestImportFixtureCommand:
    def test_loads_fixture_data(self, fixture_file):
        call_command("import_fixture", fixture=fixture_file)
        assert Course.objects.filter(name="Cours importé").exists()

    def test_extracts_media_zip(self, fixture_file, media_zip_file, settings, tmp_path):
        media_root = tmp_path / "media_root"
        settings.MEDIA_ROOT = media_root

        call_command("import_fixture", fixture=fixture_file, media_zip=media_zip_file)

        assert (media_root / "question_images" / "test.png").read_bytes() == (
            b"fake-png-bytes"
        )

    def test_missing_fixture_raises(self, tmp_path):
        with pytest.raises(CommandError):
            call_command("import_fixture", fixture=str(tmp_path / "missing.json"))

    def test_missing_media_zip_raises(self, fixture_file, tmp_path):
        with pytest.raises(CommandError):
            call_command(
                "import_fixture",
                fixture=fixture_file,
                media_zip=str(tmp_path / "missing.zip"),
            )

    def test_extracts_media_zip_with_prefix(self, fixture_file, tmp_path, settings):
        """Zip créé avec `zip -r media.zip media/` : préfixe media/ doit être strippé."""
        media_root = tmp_path / "media_root"
        settings.MEDIA_ROOT = media_root

        prefixed_zip = tmp_path / "prefixed.zip"
        with zipfile.ZipFile(prefixed_zip, "w") as archive:
            archive.writestr("media/question_images/test.png", b"fake-png-bytes")

        call_command(
            "import_fixture", fixture=fixture_file, media_zip=str(prefixed_zip)
        )

        assert (media_root / "question_images" / "test.png").read_bytes() == (
            b"fake-png-bytes"
        )
        assert not (media_root / "media").exists()

    def test_rejects_zip_slip_entries(self, fixture_file, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path / "media_root"
        malicious_zip = tmp_path / "evil.zip"
        with zipfile.ZipFile(malicious_zip, "w") as archive:
            archive.writestr("../../etc/evil.txt", b"pwned")

        with pytest.raises(CommandError):
            call_command(
                "import_fixture", fixture=fixture_file, media_zip=str(malicious_zip)
            )


class TestZipStripPrefix:
    def test_strips_common_prefix(self):
        members = [
            "media/",
            "media/question_images/",
            "media/question_images/foo.jpg",
            "media/certificates/bar.pdf",
        ]
        assert _zip_strip_prefix(members) == "media/"

    def test_no_strip_when_multiple_top_dirs(self):
        members = [
            "question_images/",
            "question_images/foo.jpg",
            "certificates/bar.pdf",
        ]
        assert _zip_strip_prefix(members) == ""

    def test_no_strip_when_no_prefix(self):
        members = ["question_images/foo.jpg"]
        assert _zip_strip_prefix(members) == ""

    def test_empty_list(self):
        assert _zip_strip_prefix([]) == ""
