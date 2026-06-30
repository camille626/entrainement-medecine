# Isolation MEDIA_ROOT dans les tests pytest (issue #74)

## Problème

Les tests pytest créaient des fichiers parasites dans `media/question_images/`
et `media/certificates/` du repo à chaque exécution. Ces dossiers sont dans
`.gitignore` donc non versionnés, mais ils polluaient le workspace.

## Cause racine

`MEDIA_ROOT = BASE_DIR / "media"` dans `config/settings.py:134` n'était jamais
overridé globalement pour les tests. Tests fautifs :

- `tests/test_images.py` — `QuestionImage.objects.create(file=SimpleUploadedFile(...))`
  → écrit dans `media/question_images/`
- `tests/test_admin_site.py` — idem via vues ddimageortext
- `tests/test_registration.py` — `RegistrationRequest` avec certificat PDF
  → écrit dans `media/certificates/`

Deux tests overridaient déjà correctement MEDIA_ROOT localement :
- `tests/test_import_fixture.py` — `settings.MEDIA_ROOT = tmp_path / "media_root"`
- `tests/test_profile.py:233` — `settings.MEDIA_ROOT = tmp_path`

Il n'existait pas de `conftest.py` dans le projet.

## Correctif

Création de `tests/conftest.py` avec une fixture `autouse=True` :

```python
@pytest.fixture(autouse=True)
def media_root_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
```

Le fixture `settings` de pytest-django applique `override_settings` pour la
durée du test, y compris pour les tests qui ne demandent pas `settings`
explicitement. Les tests qui overrident déjà MEDIA_ROOT localement continuent
à fonctionner (leur override prend le dessus dans le même scope).

Pas de `mkdir()` nécessaire : `FileSystemStorage.save()` crée les répertoires
avec `os.makedirs(..., exist_ok=True)`.

## Test de non-régression

Dans `tests/conftest.py`, un test vérifie que MEDIA_ROOT ne pointe pas vers
le `media/` du repo pendant les tests :

```python
def test_media_root_is_not_repo_media_dir(settings):
    from pathlib import Path
    repo_media = Path(__file__).parent.parent / "media"
    assert Path(settings.MEDIA_ROOT) != repo_media
```

## Pattern général à retenir

Pour tout nouveau test qui génère des fichiers media (FileField, ImageField),
la fixture autouse couvre automatiquement. Si un test a besoin d'un MEDIA_ROOT
spécifique (ex: vérifier l'arborescence après extraction), override localement
avec `settings.MEDIA_ROOT = tmp_path / "..."`.
