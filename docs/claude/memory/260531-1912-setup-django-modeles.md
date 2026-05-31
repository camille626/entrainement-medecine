# Setup Django + Modèles de données (Issue #1)

## Contexte

Mise en place de la fondation technique pour la plateforme de QCMs médicaux. Le projet s'appuie sur un export PostgreSQL de MoodleCloud contenant 6 493 QCMs répartis sur 13 cours P2 (médecine). L'objectif est de créer un site Django indépendant avec statistiques personnalisées et mode révision.

## Ce qui a été fait

### Structure Django créée

- `manage.py` — point d'entrée Django à la racine
- `config/settings.py` — configuration Django avec SQLite en dev, PostgreSQL en prod via variable d'env `DATABASE_URL`
- `config/urls.py` — routing de base avec admin activé
- `config/wsgi.py` — WSGI pour déploiement prod
- `qcm/models.py` — 6 modèles de données
- `qcm/admin.py` — tous les modèles enregistrés dans l'interface admin
- `qcm/apps.py` — configuration de l'app `QcmConfig`
- `qcm/migrations/0001_initial.py` — migration initiale générée et appliquée
- `tests/test_models.py` — 18 tests (TDD : RED puis GREEN)

### Modèles de données (`qcm/models.py`)

| Modèle | Champs clés | Relations |
|--------|-------------|-----------|
| `Course` | `name`, `short_name` | — |
| `Category` | `name`, `moodle_id` (unique) | FK → Course |
| `Question` | `text` (HTML), `qtype`, `moodle_id` (unique) | FK → Category |
| `Answer` | `text` (HTML), `fraction` (float), `is_correct` (bool) | FK → Question |
| `QuizSession` | `mode` (training/review), `started_at`, `completed_at` | FK → User, FK → Course |
| `UserAnswer` | `is_correct`, `answered_at` | FK → QuizSession, FK → Question, FK → Answer |

### Dépendances ajoutées dans `pyproject.toml`

- `django>=5.0` — framework web
- `psycopg2-binary` — driver PostgreSQL
- `whitenoise` — servir les fichiers statiques
- `pytest-django` — intégration pytest + Django
- `django-stubs[compatible-mypy]` — types Django pour mypy

### Configuration ruff migrée

Les options `extend-select` et `ignore` ont été déplacées de `[tool.ruff]` vers `[tool.ruff.lint]` (dépréciation ruff).

### Configuration mypy pour Django

- `plugins = ["mypy_django_plugin.main"]` ajouté dans `[tool.mypy]`
- Section `[tool.django-stubs]` avec `django_settings_module = "config.settings"`
- Override `qcm.migrations.*` avec `ignore_errors = true`

### Décisions techniques importantes

- **Django à la racine** (pas dans `src/`) pour éviter le conflit avec le packaging setuptools existant
- **SQLite par défaut** en dev (simple, sans serveur), PostgreSQL via `DATABASE_URL` en prod
- **`moodle_id` unique** sur Category et Question pour permettre l'import idempotent depuis le dump Moodle
- **`UserAnswer.question` et `.answer`** protégés avec `on_delete=PROTECT` (on ne supprime pas une question si des réponses utilisateurs existent)
- **`QuizSession.course`** nullable (possible futur mode cross-cours)

## Tests (18/18 passent)

Couvrent : création de chaque modèle, contraintes d'unicité (`IntegrityError`), validations (`ValidationError`), cascades de suppression, relations FK.

## Commandes utiles

```bash
# Lancer les tests
uv run --active pytest tests/ -v

# Lancer le serveur de dev
uv run --active python manage.py runserver

# Créer un superuser pour l'admin
uv run --active python manage.py createsuperuser

# Admin Django : http://127.0.0.1:8000/admin/
```

## Prochaine étape

Issue #2 : script d'import depuis le dump Moodle (`data/raw/plateforme-medecine_moodlecloud.sql`) vers les modèles Django. Exclure les cours "embryo PASS" et "annale BDR 2024".
