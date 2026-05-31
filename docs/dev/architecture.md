# Architecture

## Vue d'ensemble

La plateforme est une application Django connectée à une base de données SQLite (développement) ou PostgreSQL (production). Les données proviennent d'un export de QCMs médicaux organisés en cours et catégories.

## Structure des répertoires

```
config/                        # Configuration Django (settings, urls, wsgi)
qcm/                           # App Django principale
├── models.py                  # Modèles de données
├── admin.py                   # Interface d'administration
├── migrations/                # Migrations de base de données
└── management/commands/
    ├── moodle_parser.py       # Parser du dump SQL Moodle
    └── import_moodle.py       # Commande d'import
tests/                         # Tests pytest
```

## Modèles de données

### Hiérarchie des contenus

```
StudyYear (P2, P3...)
  └── Semester (S1, S2)
        └── Course (moodle_id unique, nullable semester)
              └── Category (moodle_id unique)
                    └── Question (moodle_id unique, texte HTML)
                          ├── Answer (fraction 0.0–1.0, is_correct)
                          └── Tag (M2M — annale 2024, immuno, semio...)
```

### Suivi des réponses utilisateurs

```
User
  └── QuizSession (mode: training | review, course optionnel)
        └── UserAnswer (question, answer choisie, is_correct, timestamp)
```

### Détail des modèles

**`Course`** — un cours P2 (ex: "P2 - La cellule")

| Champ | Type | Description |
|-------|------|-------------|
| `name` | CharField(255) | Nom complet du cours |
| `short_name` | CharField(50) | Identifiant court (ex: "cell") |

**`Category`** — une thématique à l'intérieur d'un cours

| Champ | Type | Description |
|-------|------|-------------|
| `name` | CharField(255) | Nom de la catégorie |
| `course` | FK → Course | Cours parent |
| `moodle_id` | IntegerField (unique) | ID d'origine Moodle (import idempotent) |

**`Question`** — une question QCM

| Champ | Type | Description |
|-------|------|-------------|
| `text` | TextField | Énoncé en HTML |
| `category` | FK → Category | Catégorie parente |
| `qtype` | CharField | `multichoice`, `shortanswer`, `match` |
| `moodle_id` | IntegerField (unique) | ID d'origine Moodle |

**`Answer`** — une proposition de réponse

| Champ | Type | Description |
|-------|------|-------------|
| `text` | TextField | Texte en HTML |
| `question` | FK → Question | Question parente |
| `fraction` | FloatField [0.0–1.0] | 1.0 = correcte, 0.0 = incorrecte |
| `is_correct` | BooleanField | Raccourci booléen |

**`QuizSession`** — une session d'entraînement d'un utilisateur

| Champ | Type | Description |
|-------|------|-------------|
| `user` | FK → User | Utilisateur Django |
| `course` | FK → Course (nullable) | Cours ciblé (null = multi-cours) |
| `mode` | CharField | `training` ou `review` |
| `started_at` | DateTimeField | Début de session |
| `completed_at` | DateTimeField (nullable) | Fin de session |

**`UserAnswer`** — la réponse d'un utilisateur à une question

| Champ | Type | Description |
|-------|------|-------------|
| `session` | FK → QuizSession (CASCADE) | Session parente |
| `question` | FK → Question (PROTECT) | Question répondue |
| `answer` | FK → Answer (PROTECT) | Réponse choisie |
| `is_correct` | BooleanField | Résultat |
| `answered_at` | DateTimeField | Horodatage |

## Configuration de la base de données

La base de données est sélectionnée via la variable d'environnement `DATABASE_URL` :

```bash
# Développement (SQLite par défaut, aucune config nécessaire)
uv run --active python manage.py runserver

# Production (PostgreSQL)
DATABASE_URL=postgresql://user:pass@host:5432/dbname python manage.py runserver  # pragma: allowlist secret
```

## Lancer les tests

```bash
uv run --active pytest tests/ -v
```

Les tests utilisent `pytest-django` avec `DJANGO_SETTINGS_MODULE = "config.settings"` configuré dans `pyproject.toml`. La base de données de test est créée et détruite automatiquement pour chaque session.

## Import des données Moodle

### Prérequis

Le dump source `data/raw/plateforme-medecine_moodlecloud.sql` doit être présent (format binaire PostgreSQL 17, non versionné). PostgreSQL 17 doit être installé pour la conversion du dump binaire.

### Commande

```bash
uv run --active python manage.py import_moodle --dump data/raw/plateforme-medecine_moodlecloud.sql
```

La commande est **idempotente** : elle peut être relancée sans créer de doublons. Les réponses existantes sont mises à jour via `update_or_create`.

### Résultat attendu

```
13 cours, 139 catégories, 6 454 questions, 32 131 réponses
```

### Règles de mapping

| Champ | Règle |
|-------|-------|
| `Course.moodle_id` | `m_course.id` (filtré sur ids 11–23) |
| `Category` | `m_question_categories` excluant les catégories `top` |
| `Question` | `m_question` avec `qtype = multichoice` uniquement |
| `Answer.is_correct` | `fraction > 0.0` (toute fraction positive est correcte, y compris 0.33, 0.5...) |

### Chaîne de liaison cours → catégories

La liaison cours → catégories passe par trois tables intermédiaires :

```
m_course → m_course_modules → m_context (contextlevel=70) → m_question_categories.contextid
```

La liaison catégorie → question passe par :

```
m_question_versions.questionid → m_question_bank_entries.questioncategoryid
```
