# Filtrage dynamique et hiérarchie des tags (Issue #10)

## Contexte

Amélioration de la page de configuration de session : filtrage dynamique des tags selon les cours sélectionnés (HTMX), catégorisation des tags en annale/EC/chapitre, et cascade cours → EC → chapitres.

## Modèles ajoutés/modifiés

### `TagCategory` (nouveau, `qcm/models.py`)
- `name`, `tag_type` (annee/souscategorie/chapitre), `course FK nullable`, `order`
- Configurable via admin pour assigner les 159 tags à leurs catégories

### `Tag` modifié
- `category FK → TagCategory` (null=True)
- `parent_ec FK → self` (null=True) — pour les tags chapitres, indique l'EC parente
- `course FK → Course` (null=True) — pour les tags chapitres, restreint au cours

## Migrations
- `0008_add_tagcategory` — TagCategory + Tag.category
- `0009_add_tag_parent_ec` — Tag.parent_ec
- `0010_add_tag_course` — Tag.course

## Architecture HTMX

### Flux de filtrage
1. Sélection cours → `GET /entrainement/tags/` → `_tags_partial.html` (annale + EC filtrés)
2. Sélection EC → `GET /entrainement/chapters/` → `_chapters_partial.html` (chapitres)

### `TagsView` (`/entrainement/tags/`)
- Annale et EC globales (course=NULL) : toujours affichées si cours sélectionné
- EC globales (souscategorie, course=NULL) : filtrées par questions existant dans les cours sélectionnés (évite d'afficher des ECs sans questions)
- EC cours-spécifiques (course=X) : affichées seulement si ce cours est sélectionné
- Chapitres directs (course=X, parent_ec=NULL) : affichés directement après sélection du cours, sans passer par une EC
- Tags non catégorisés : **jamais affichés**
- Stocke `course_ids` dans `request.session["selected_course_ids"]` pour `ChaptersView`

### `ChaptersView` (`/entrainement/chapters/`)
- Lit `selected_course_ids` depuis la session Django (fiable vs. HTMX)
- Filtre : `Tag.parent_ec__in=selected_ec_tags AND (course__in=selected_courses OR course=NULL)`
- Groupés par `tag.category`

### Problème HTMX résolu
`hx-include` depuis un partial HTMX remplacé ne transmet pas fiablement les params externes. Solution : stocker les cours sélectionnés en session Django dans `TagsView`, lus par `ChaptersView`.

## Logique de sélection des questions (`ConfigurationView.post`)

Tags séparés par type :
- **Annale + EC** → filtre strict (`qs.filter(tags__in=non_chapter_tags)`)
- **Chapitre** → souple :
  - Questions avec le tag chapitre sélectionné **OU**
  - Questions sans aucun tag chapitre (non classifiées — incluses pour ne pas perdre de questions)

Ceci permet qu'une question non classifiée (pas de tag chapitre) figure quand même dans une session filtrée par chapitre.

## Config admin pour les tags

Chaque tag chapitre se configure dans `/admin/qcm/tag/` avec :
- `parent_ec` → EC parente (ex: `histologie/embryologie`)
- `course` → cours d'appartenance (ex: `P2 - tissu sanguin et système immunitaire`)

Tags chapitres sans `parent_ec` mais avec `course` → affichés directement après sélection du cours (cours sans EC).

## Opérations de nettoyage des données effectuées

- Merger de doublons : hémostase, hématopoïèse généralités, mégacaryopoïèse, sémio néphrologique, thérapie cellulaire, érythropoïèse, histologie/embryologie
- Retrait de `physio` et `radio` des questions cardiovasculaire (ECs incorrectes)
- Merge cours-spécifiques : semio neuro → semio (196 q. neuro), semio respi → semio (25 q. respi), semio cardio → semio (92 q. cardio)
- Renommage : `histologie` → `histologie/embryologie`

## Tests

`tests/test_tag_filtering.py` : 17 tests couvrant TagCategory, TagsView, ChaptersView avec les trois types de filtrage.
