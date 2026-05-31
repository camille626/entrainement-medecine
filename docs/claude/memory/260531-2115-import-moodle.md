# Import des données Moodle vers Django (Issue #3)

## Contexte

Commande Django `import_moodle` qui importe 6 454 questions médicales depuis le dump PostgreSQL MoodleCloud (`data/raw/plateforme-medecine_moodlecloud.sql`, format binaire PG17, 12 MB) vers les modèles Django en préservant l'arborescence cours → catégories → questions.

## Ce qui a été fait

### Modification du modèle `Course`

Ajout de `moodle_id = IntegerField(unique=True, null=True, blank=True)` dans `qcm/models.py` pour permettre l'import idempotent par identifiant Moodle.

Migration générée : `qcm/migrations/0002_add_course_moodle_id.py`

### Structure créée

- `qcm/management/__init__.py` — package Django management
- `qcm/management/commands/__init__.py`
- `qcm/management/commands/moodle_parser.py` — parser du dump SQL
- `qcm/management/commands/import_moodle.py` — commande Django
- `tests/test_import_moodle.py` — 12 tests TDD avec mini-dump synthétique

### Parser (`moodle_parser.py`)

Deux fonctions principales :

**`parse_sql_dump(path)`** → `dict[str, list[dict]]`
- Détecte si le dump est binaire (commence par `PGDMP`) → convertit via `/usr/lib/postgresql/17/bin/pg_restore -f /tmp/... <path>`
- Sinon parse directement (pour les tests avec fixtures texte)
- Extrait les blocs `COPY "public"."<table>" (...) FROM stdin;` → dicts par table

**`build_context_to_course(data)`** → `dict[int, int]`
- Reconstruit la chaîne `m_course_modules → m_context(contextlevel=70) → context_id`
- Retourne `{context_id: course_moodle_id}`

### Chaîne de liaison Moodle (vérifiée sur le dump)

```
m_course.id (ids 11-23)
  → m_course_modules.course       (module appartenant au cours)
  → m_context.instanceid (level=70) (contexte du module quiz)
  → m_question_categories.contextid (catégories)
  → m_question_bank_entries.questioncategoryid (via m_question_versions.questionid)
  → m_question.id
  → m_question_answers.question
```

### Cours à importer (`COURSE_IDS` dans `import_moodle.py`)

IDs Moodle : `{11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}` (tous les cours P2).
Exclus : ids 1, 8, 9, 10 (site course, Starting with Moodle, BDR annales, embryo PASS).

### Règles d'import

- **Catégories "top"** : exclues (catégories fantômes Moodle sans contenu réel)
- **Questions** : seulement `qtype == "multichoice"`
- **`is_correct`** : `fraction > 0.0` (toute fraction positive = réponse correcte, incluant 0.33, 0.5, 0.25...)
- **Idempotence** : `get_or_create` sur `moodle_id` pour Course/Category/Question, `update_or_create` sur (question, text) pour Answer

### Résultats sur le vrai dump

```
13 cours, 139 catégories, 6 454 questions, 32 131 réponses
dont 16 504 is_correct=True (1 321 à fraction=1.0, 15 183 à fraction partielle)
```

### Décision clé : fraction > 0 = is_correct

En médecine (format EDN), une réponse à fraction positive (0.33, 0.5, 0.25...) est une réponse partiellement correcte et compte dans le score. Elle doit donc être marquée `is_correct=True`. Seule `fraction=0.0` est incorrecte.

### Tests (12 passent)

Mini-dump texte synthétique en fixture `tmp_path` (pas le vrai dump, trop lourd pour la CI). Couvre : import correct, exclusions (cours bloqués + catégories "top"), liaisons FK, fractions partielles, idempotence.

## Commandes utiles

```bash
# Importer depuis le dump
uv run --active python manage.py import_moodle --dump data/raw/plateforme-medecine_moodlecloud.sql

# Relancer est safe (idempotent) — met à jour is_correct via update_or_create
```
