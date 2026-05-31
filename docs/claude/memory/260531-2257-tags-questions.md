# Tags sur les questions — import et filtrage (Issue #8)

## Contexte

Import des tags Moodle sur les questions pour permettre le filtrage par tag dans l'interface d'entraînement (annales par année, chapitres, etc.). Le tag `le chat` (questions générées par IA sans annale) est exclu de l'import.

## Ce qui a été fait

### Nouveau modèle `Tag` dans `qcm/models.py`

- `name` (CharField max 100, unique)
- `moodle_id` (IntegerField, unique)
- `Meta.ordering = ["name"]`

### Modification de `Question`

- Ajout de `tags = ManyToManyField(Tag, blank=True, related_name="questions")`
- Migration : `qcm/migrations/0005_add_tag_model.py`

### Import dans `import_moodle`

Deux nouvelles méthodes dans `qcm/management/commands/import_moodle.py` :

**`_compute_ai_only_question_ids(data)`** — calcule les moodle_ids à exclure de l'import (questions taguées `le chat` sans `annale`)

**`_import_tags(data)`** — importe les tags et leurs liaisons :
- Parcourt `m_tag`, exclut les tags dans `EXCLUDED_TAGS = {'le chat'}`
- Parcourt `m_tag_instance` (filtre `itemtype='question'`)
- Assigne les tags via `question.tags.set(tags)` (idempotent)

### Constante `EXCLUDED_TAGS`

```python
EXCLUDED_TAGS = {'le chat'}
```

Tags listés ici ne sont jamais importés ni liés aux questions.

### Questions exclues de l'import

`_compute_ai_only_question_ids` retourne les moodle_ids des questions taguées `le chat` sans `annale`. Ces questions sont ignorées dans `_import_questions`. Elles ne sont donc jamais importées même si on relance l'import.

## État de la base après import

- **4 516 questions** (1 938 questions IA-only exclues définitivement)
- **159 tags** (sans `le chat`)
- **16 020 liaisons** question↔tag
- Top tags : `annale` (4 058), `annale 2023` (1 188), `annale 2024` (1 103), `semio` (1 090)

## Admin

`qcm/admin.py` : `TagAdmin` (list_display name/moodle_id, search) + `QuestionAdmin` mise à jour (filter_horizontal tags, list_filter par tag).

## Tests (58 passent)

`tests/test_tags.py` : création Tag, unicité, M2M avec Question, reverse queryset.
`tests/test_import_moodle.py::TestImportTags` : import tags, exclusion le chat, liaisons, idempotence.

## Décisions techniques

- `question.tags.set(tags)` remplace les liaisons existantes à chaque import → idempotent
- Les questions IA-only sont exclues en amont (avant `_import_questions`), pas en post-traitement
- `EXCLUDED_TAGS` est extensible pour exclure d'autres tags indésirables à l'avenir
