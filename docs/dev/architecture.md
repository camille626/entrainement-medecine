# Architecture

## Vue d'ensemble

La plateforme est une application Django connectée à une base de données SQLite (développement) ou PostgreSQL (production). Les données proviennent d'un export de QCMs médicaux organisés en cours et catégories.

## Structure des répertoires

```
config/                        # Configuration Django (settings, urls, wsgi)
qcm/                           # App Django principale
├── models.py                  # Modèles de données
├── views.py                   # Vues principales (entraînement, stats, erratas…)
├── views_admin.py             # Vues interface admin web (/admin-site/)
├── admin.py                   # Interface Django Admin (/admin/)
├── migrations/                # Migrations de base de données
└── management/commands/
    ├── moodle_parser.py       # Parser du dump SQL Moodle
    └── import_moodle.py       # Commande d'import
tests/                         # Tests pytest
```

## Interface admin web

Une section staff-only `/admin-site/` permet de gérer les données sans passer par le Django Admin technique. Elle est implémentée dans `qcm/views_admin.py` avec un `StaffRequiredMixin` qui redirige les non-staff vers l'accueil.

| URL | Fonctionnalité |
|-----|----------------|
| `/admin-site/` | Tableau de bord (compteurs) |
| `/admin-site/demandes/` | Accepter/refuser les inscriptions |
| `/admin-site/utilisateurs/` | Liste, activer/désactiver, supprimer, changer d'année |
| `/admin-site/questions/` | Liste paginée, modifier, supprimer |
| `/admin-site/cours/` | Ajouter un cours, assigner un semestre |
| `/admin-site/tags/` | Ajouter des tags EC/chapitre avec leur appartenance |

La logique d'acceptation d'inscription (`accept_registration`) est centralisée dans `views_admin.py` et réutilisée par `admin.py`.

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
  ├── UserProfile (photo de profil — OneToOne)
  ├── LoginEvent (logged_at — enregistré via signal user_logged_in)
  ├── UserTrophy (trophy, unlocked_at — unique_together user+trophy)
  └── QuizSession (mode: training | review, course optionnel)
        └── UserAnswer (question, answer choisie, is_correct, timestamp)
```

### Système de trophées

`Trophy` — définition d'un trophée : `name` (unique), `rarity` (bronze/silver/gold), `study_year` (ALL/P2/D1/blank), `hidden` (bool), `condition_type` (11 types), `condition_value` (seuil entier), `condition_tag` (FK → Tag, nullable).

`UserTrophy` — attribution à un utilisateur, idempotente via `get_or_create`.

`LoginEvent` — une ligne par connexion. Le signal `user_logged_in` dans `qcm/apps.py` crée l'entrée et appelle `award_login_trophies(request, user)`.

Le service `qcm/trophies.py` expose deux fonctions publiques :

- `check_and_award_trophies(request, session)` — appelé après chaque soumission de réponse, vérifie tous les types de conditions.
- `award_login_trophies(request, user)` — appelé au login, vérifie uniquement `login_count` et `consecutive_days`.

Les trophées débloqués génèrent un message Django `extra_tags="trophy"` consommé par le toast Bootstrap dans `base.html`.

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

**`Question`** — une question

| Champ | Type | Description |
|-------|------|-------------|
| `text` | TextField | Énoncé en HTML |
| `category` | FK → Category | Catégorie parente |
| `qtype` | CharField | `multichoice`, `shortanswer`, `ddimageortext`, `match` |
| `moodle_id` | IntegerField (unique) | ID d'origine Moodle |

**`Answer`** — une proposition de réponse

| Champ | Type | Description |
|-------|------|-------------|
| `text` | TextField | Texte en HTML |
| `question` | FK → Question | Question parente |
| `fraction` | FloatField [0.0–1.0] | 1.0 = correcte, 0.0 = incorrecte |
| `is_correct` | BooleanField | Raccourci booléen |

**`QuestionImage`** — une image associée à une question

| Champ | Type | Description |
|-------|------|-------------|
| `question` | FK → Question (CASCADE) | Question parente |
| `moodle_filename` | CharField(255) | Nom du fichier tel que référencé dans `@@PLUGINFILE@@/filename` |
| `file` | FileField | Fichier stocké sous `MEDIA_ROOT/question_images/` |

Contrainte `unique_together = (question, moodle_filename)`. La méthode `Question.render_text()` résout dynamiquement les `@@PLUGINFILE@@/filename` en URLs locales lors du rendu HTML.

**`UserProfile`** — profil étendu d'un utilisateur (OneToOne avec User)

| Champ | Type | Description |
|-------|------|-------------|
| `user` | OneToOneField → User (CASCADE) | Utilisateur Django (related_name `profile`) |
| `photo` | ImageField (nullable) | Photo de profil stockée sous `MEDIA_ROOT/profile_photos/` |

Créé à la demande via `get_or_create` dans `ProfileView`. Accessible depuis les templates via `user.profile.photo` — Django intercepte silencieusement `RelatedObjectDoesNotExist` (hérite de `AttributeError`), ce qui rend `{% if user.profile.photo %}` safe même sans profil existant.

**`QuizSession`** — une session d'entraînement d'un utilisateur

| Champ | Type | Description |
|-------|------|-------------|
| `user` | FK → User | Utilisateur Django |
| `course` | FK → Course (nullable) | Cours ciblé (null = multi-cours) |
| `mode` | CharField | `training` ou `review` |
| `started_at` | DateTimeField | Début de session |
| `completed_at` | DateTimeField (nullable) | Fin de session |
| `hidden_by_user` | BooleanField | Soft-delete : masque la session de l'historique sans toucher aux `UserAnswer`, qui restent comptabilisés dans les statistiques |

**`UserAnswer`** — la réponse d'un utilisateur à une question

| Champ | Type | Description |
|-------|------|-------------|
| `session` | FK → QuizSession (CASCADE) | Session parente |
| `question` | FK → Question (PROTECT) | Question répondue |
| `answer` | FK → Answer (PROTECT, **nullable**) | Réponse choisie — `None` pour QROC et ddimageortext |
| `is_correct` | BooleanField | Résultat |
| `qroc_text` | TextField (nullable) | Texte tapé (QROC) ou JSON des saisies par zone (ddimageortext) |
| `is_self_evaluated` | BooleanField | `True` si auto-évaluation QROC sans correspondance |
| `fraction_override` | FloatField (nullable) | Fraction partielle explicite — utilisé par ddimageortext (ex: 2/3 zones correctes) |
| `answered_at` | DateTimeField | Horodatage |

La propriété `effective_fraction` suit la priorité : `fraction_override` > `answer.fraction` > `is_correct` (1.0/0.0). Tous les calculs de score utilisent cette propriété.

**`ImageDragItem`** — étiquette d'une question ddimageortext

| Champ | Type | Description |
|-------|------|-------------|
| `question` | FK → Question (CASCADE) | Question parente |
| `no` | IntegerField | Numéro Moodle (1-indexé, unique par question) |
| `label` | CharField(500) | Texte de l'étiquette |
| `draggroup` | IntegerField | Groupe Moodle (ignoré à l'affichage) |

**`ImageDropZone`** — zone cible sur l'image d'une question ddimageortext

| Champ | Type | Description |
|-------|------|-------------|
| `question` | FK → Question (CASCADE) | Question parente |
| `no` | IntegerField | Numéro Moodle (1-indexé, unique par question) |
| `xleft` | IntegerField | Position X en pixels dans l'image naturelle |
| `ytop` | IntegerField | Position Y en pixels dans l'image naturelle |
| `correct_drag_no` | IntegerField | `no` du drag item correct pour cette zone |
| `correct_label` | CharField(500) | Label attendu (dénormalisé pour les comparaisons) |

## Questions QROC (shortanswer)

Les questions de type `shortanswer` utilisent un champ texte libre à la place des cases à cocher.

### Validation

La correspondance est insensible à la casse et aux accents via `normalize_qroc()` (unicodedata NFD). Le joker Moodle `*` est supporté via `fnmatch` : un pattern comme `myélome*` correspond à "myélome classique", "myélome multiple", etc.

### Flux de réponse

```
Étudiant tape → POST /check/
  ├─ Correspondance trouvée → UserAnswer(answer=matched_answer)
  └─ Pas de correspondance → template _qroc_ambiguous.html
        [J'avais bon] / [J'avais faux] → POST /check-qroc/
              → UserAnswer(answer=None, is_self_evaluated=True)
```

### Errata QROC

Le type `Errata.QROC_ANSWER` permet à un étudiant de suggérer une nouvelle variante acceptée. L'admin fixe une fraction (1.0 par défaut) et accepte → un nouvel `Answer` est créé pour la question.

## Questions légendes interactives (ddimageortext)

Les questions de type `ddimageortext` affichent une image anatomique sur laquelle l'étudiant saisit le nom de chaque structure zone par zone, comme un QROC.

### Modèles spécifiques

- `ImageDragItem` — les étiquettes possibles (incluant des distracteurs)
- `ImageDropZone` — les zones cibles positionnées en pixels sur l'image (`xleft`, `ytop`)
- `QuestionImage` — l'image de fond (même modèle que les images dans les énoncés multichoix)

### Flux de réponse

```
Étudiant saisit texte par zone → POST /check/
  └─ _handle_ddimageortext()
       → normalize_qroc(user_text) == normalize_qroc(zone.correct_label) par zone
       → fraction = zones_correctes / total_zones
       → UserAnswer(answer=None, fraction_override=fraction, qroc_text=JSON)
```

Le JSON stocké dans `qroc_text` a la forme `{"1": "sclérotique", "2": "choroide", ...}` (clé = `zone.no` en string).

### Import depuis Moodle

La commande `import_moodle` importe automatiquement :

- Les questions `ddimageortext` depuis `m_question`
- Les drag items depuis `m_qtype_ddimageortext_drags`
- Les drop zones depuis `m_qtype_ddimageortext_drops`
- Les images de fond depuis `moodledata/filedir/{hash[:2]}/{hash[2:4]}/{hash}`

Le répertoire `moodledata/` est détecté automatiquement s'il est voisin du fichier dump.

### Positionnement responsive

Les coordonnées `xleft`/`ytop` sont en pixels dans l'image à sa taille naturelle. Un JS minimal (`ddiScaleZones`) recalcule les positions après chargement de l'image pour s'adapter à la taille affichée (responsive).

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
13 cours, 139 catégories, ~6 515 questions (6 454 multichoix + 61 shortanswer), ~32 333 réponses
```

### Règles de mapping

| Champ | Règle |
|-------|-------|
| `Course.moodle_id` | `m_course.id` (filtré sur ids 11–23) |
| `Category` | `m_question_categories` excluant les catégories `top` |
| `Question` | `m_question` avec `qtype` dans `{multichoice, shortanswer}` |
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
