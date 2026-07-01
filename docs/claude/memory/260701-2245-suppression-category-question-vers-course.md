# Suppression du modèle Category — Question pointe directement vers Course

**Issue #87 / branche** : `72-supprimer-le-vestige-category-relier-les-questions-directement-au-cours`
**Date** : 2026-07-01

## Contexte

Le modèle `Category` était un vestige de l'import Moodle : ~129 catégories sans valeur
fonctionnelle, servant uniquement d'intermédiaire entre `Question` et `Course`. Chaque
traversée `question.category.course` était remplacée par `question.course`.

**Attention importante** : `TagCategory` (modèle distinct, utilisé pour organiser les `Tag`)
n'a PAS été touché — seul le modèle `Category` (lié aux questions) a été supprimé.

## Stratégie de migration (3 étapes)

Pour supprimer une FK sans perte de données ni interactivité :

1. **`0032_question_add_course_nullable.py`** — généré par `makemigrations` : ajoute
   `Question.course` nullable avec `related_name="questions"`
2. **`0033_migrate_question_course_data.py`** — écrit manuellement avec `RunPython` :
   copie `q.category.course_id → q.course_id` via `select_related("category__course").iterator()`
3. **`0034_remove_category.py`** — écrit manuellement : `AlterField` course NOT NULL,
   `RemoveField` category, `DeleteModel` Category

**Pourquoi écrire 0033 et 0034 manuellement** : `makemigrations` demanderait interactivement
une valeur par défaut pour le passage NOT NULL, et ne peut pas générer la data migration.

## Piège Django à retenir

Quand on lance `makemigrations` après avoir modifié `models.py`, Django charge
**tout le code** (admin, views, urls) via `autodiscover_modules`. Si un de ces fichiers
importe encore l'ancien modèle (`Category`), la commande échoue avec une `ImportError`
avant même de générer les migrations. L'ordre de correction est donc :
1. Mettre à jour `models.py`
2. Mettre à jour `admin.py`, `views.py`, `views_admin.py` (supprimer imports)
3. Ensuite seulement lancer `makemigrations`

## Fichiers modifiés

**Modèles et migrations :**
- `qcm/models.py` : suppression de la classe `Category`, `Question.category` → `Question.course`
- `qcm/migrations/0032_question_add_course_nullable.py`
- `qcm/migrations/0033_migrate_question_course_data.py`
- `qcm/migrations/0034_remove_category.py`

**Application :**
- `qcm/admin.py` : suppression `CategoryAdmin`, `QuestionAdmin` liste/filtre par `course`
- `qcm/views.py` : toutes les traversées `category__course__in` → `course__in`, etc.
- `qcm/views_admin.py` : suppression filtres `category_id`, select_related, contexte
- `qcm/management/commands/import_moodle.py` : suppression `_import_categories()`,
  mapping `cat_to_course: dict[int, Course]` construit inline sans créer d'objets DB,
  `_find_category_for_question` renommé `_find_course_for_question`
- `qcm/management/commands/find_missing_images.py`
- `qcm/management/commands/seed_image_erratas.py`

**Templates (4 fichiers) :**
- `qcm/templates/qcm/errata_list.html`
- `qcm/templates/qcm/admin_site/questions.html` : suppression sélecteur catégorie
- `qcm/templates/qcm/admin_site/question_form.html` : suppression select catégorie + JS `filterCategories()`
- `qcm/templates/qcm/admin_questions_preview.html` : sélecteur `category_id` → `course_id`

**Tests (32 fichiers) :** suppression du fixture `category`, `question(category)` → `question(course)`,
`category=category` → `course=course` partout. Dans `test_import_moodle.py`, suppression
des 3 tests Category (`test_excludes_top_categories`, `test_imports_real_categories`,
`test_categories_linked_to_course`), renommage `test_questions_linked_to_category` →
`test_questions_linked_to_course` avec assertion sur `course=course`.

## Résultat

- 471 tests GREEN
- `ruff check . && ruff format --check .` : propre
- `mkdocs build --strict` : OK
- CI GitHub : success
