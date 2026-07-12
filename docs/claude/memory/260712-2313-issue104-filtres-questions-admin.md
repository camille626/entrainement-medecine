# Issue #104 — Filtres tag/chapitre/EC + date de dernière modification dans "Gérer les questions"

## Contexte

L'onglet admin "Gérer les questions" (`/admin-site/questions/`, `AdminQuestionsView` dans `qcm/views_admin.py`) ne permettait de filtrer que par cours, type de question et texte de l'énoncé. Impossible de filtrer par tag, de repérer les questions sans tag chapitre/EC, ou de voir/trier par date de dernière modification. Deux boucles d'implémentation ont eu lieu : une v1 (filtre tag texte libre + datalist) livrée puis affinée suite au retour utilisateur en v2 (filtres à sélection multiple avec exclusion).

## Modifications apportées

### Modèle

- `qcm/models.py:145` — ajout de `updated_at = models.DateTimeField(auto_now=True)` sur `Question`.
- Migration `qcm/migrations/0037_question_updated_at.py` : pas de prompt interactif pour une valeur par défaut ponctuelle malgré la colonne `NOT NULL` sur une table existante — Django gère ça automatiquement pour les champs `auto_now=True`/`auto_now_add=True` car `Field.get_default()` renvoie `timezone.now()` nativement pour ces champs.

### Vue — `AdminQuestionsView.get()` (`qcm/views_admin.py:371-450` environ)

Paramètres GET finaux (v2) :
- `tags` (multi, `request.GET.getlist`) : inclusion, logique **OR** — `qs.filter(tags__id__in=tag_ids).distinct()`.
- `exclude_tags` (multi) : exclusion — `qs.exclude(tags__id__in=exclude_tag_ids)`.
- `exclude_courses` (multi) : exclusion de cours entiers — `qs.exclude(course_id__in=exclude_course_ids)`.
- `no_chapitre` / `no_ec` (booléens, inchangés depuis v1) : `qs.exclude(tags__category__tag_type=TagCategory.CHAPITRE/SOUSCATEGORIE).distinct()`.
- `sort` (`updated_at`/`-updated_at`, whitelist `SORT_FIELDS`).

`available_tags` (queryset passé au template pour peupler les widgets de tags) est **scopé au cours sélectionné** : si `course_id` est présent, `Tag.objects.filter(questions__course_id=course_id).distinct()` au lieu de tous les tags de la base.

**Apprentissage Django important** : `.exclude()` sur une relation M2M multi-valuée (ex. `tags__id__in=[...]`) n'a **pas besoin** de `.distinct()` — Django traduit ça en sous-requête (NOT IN/NOT EXISTS), contrairement à `.filter()` sur M2M qui fait un JOIN et duplique les lignes si plusieurs tags matchent (`.distinct()` obligatoire dans ce cas). Le code exclut donc `.distinct()` après les `.exclude(...)` mais le garde après les `.filter(tags__id__in=...)`.

### Template — `qcm/templates/qcm/admin_site/questions.html`

- 3 widgets identiques (tags à inclure, tags à exclure, cours à exclure) : menu déroulant Bootstrap 5.3 (`data-bs-auto-close="outside"`) avec un champ de recherche en haut (filtrage JS pur côté client sur le texte des `<label>`, fonction `filterDropdownOptions()`) et une liste scrollable de checkboxes en dessous (`max-height` + `overflow-y:auto`).
- **Les checkboxes de ces 3 widgets ne font PAS d'auto-submit** (`onchange="this.form.submit()"` aurait cassé l'UX de sélection multiple — soumission à chaque clic) : un bouton **"Filtrer"** explicite valide le formulaire une fois toutes les cases cochées. Les `<select>` cours/qtype simples et les checkboxes `no_chapitre`/`no_ec` gardent l'auto-submit (sélection unique, pas de gêne).
- Colonne "Dernière modification" triable (en-tête cliquable, affichage `d/m/Y H:i`).
- **Pagination et lien de tri utilisent `{% querystring %}`** (tag de template Django 5.1+, dispo car le projet est en Django 5.2.14) au lieu de reconstruire la querystring à la main : `{% querystring page=page_obj.next_page_number %}`, `{% querystring sort='updated_at' page=None %}`. Ce tag préserve automatiquement tous les paramètres GET actuels, **y compris les paramètres multi-valués répétés** (`tags=1&tags=2&...`), ce qui aurait été fastidieux à reconstruire manuellement comme le faisait la v1 (chaîne de caractères codée en dur pour chaque paramètre). Nécessite `django.template.context_processors.request` dans `TEMPLATES.context_processors` (déjà présent dans `config/settings.py`).

### Tests

- `tests/test_models.py` — `TestQuestion.test_updated_at_set_on_create`, `test_updated_at_changes_on_save`.
- `tests/test_admin_site.py::TestAdminQuestions` — nouveaux tests : `test_list_filtered_by_tags_include`, `test_list_filtered_by_tags_include_is_ored`, `test_list_filtered_by_exclude_tags`, `test_list_filtered_by_exclude_courses`, `test_tags_dropdown_scoped_to_selected_course`, `test_list_filtered_no_chapitre`, `test_list_filtered_no_ec`, `test_list_shows_last_modified_column`, `test_list_sortable_by_last_modified`.

## Méthode de vérification (pas de navigateur disponible en session)

Vérifié via `manage.py runserver` réel + `curl` avec session authentifiée (login form + cookie jar), données de test seedées/nettoyées via `manage.py shell`, plutôt que le test client Django — pour observer le vrai HTML rendu (JS, `{% querystring %}`, structure des dropdowns) comme un utilisateur le verrait. Deux passes de vérification (une par boucle d'implémentation), toutes deux PASS, données de test nettoyées après coup.

## Fichiers modifiés

`qcm/models.py`, `qcm/migrations/0037_question_updated_at.py`, `qcm/views_admin.py`, `qcm/templates/qcm/admin_site/questions.html`, `tests/test_models.py`, `tests/test_admin_site.py`.
