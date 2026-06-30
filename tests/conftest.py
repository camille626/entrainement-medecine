import pytest


@pytest.fixture(autouse=True)
def media_root_tmp(settings, tmp_path):
    """Redirige MEDIA_ROOT vers un dossier temporaire pour chaque test.

    Évite que les tests ne créent des fichiers dans media/ du repo.
    Les tests qui overrident settings.MEDIA_ROOT explicitement continuent
    à fonctionner (leur override local prend le dessus).
    """
    settings.MEDIA_ROOT = tmp_path / "media"


def test_media_root_is_not_repo_media_dir(settings):
    """MEDIA_ROOT pendant les tests ne doit pas pointer vers le media/ du repo."""
    from pathlib import Path

    repo_media = Path(__file__).parent.parent / "media"
    assert Path(settings.MEDIA_ROOT) != repo_media
