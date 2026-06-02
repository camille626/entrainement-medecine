# Upload de questions Moodle XML — Issue #34

## Résumé

Workflow admin d'import de questions depuis un fichier XML Moodle (export standard Banque de questions → Format XML Moodle). Workflow en 3 étapes : upload → preview + édition inline → confirmer.

---

## Modèle : `Question.moodle_id` nullable

`qcm/models.py` ligne ~146 :
```python
# Avant :
moodle_id = models.IntegerField(unique=True)
# Après :
moodle_id = models.IntegerField(unique=True, null=True, blank=True)
```
`__str__` mis à jour : `f"Question #{self.moodle_id or 'N/A'} ({self.category})"`

Migration : `qcm/migrations/0018_question_moodle_id_nullable.py`

**Important** : SQLite autorise plusieurs `NULL` dans une colonne `UNIQUE` → plusieurs questions uploadées peuvent avoir `moodle_id=None` sans conflit.

---

## Parser : `qcm/question_upload.py`

### `parse_moodle_xml(content: bytes) -> list[dict]`
- Lève `ValueError` si XML invalide
- Ignore les types != `multichoice`
- Ignore questions sans texte ou avec < 2 réponses

### Format Moodle XML attendu
```xml
<question type="multichoice">
  <questiontext format="html"><text><![CDATA[<p>Texte</p>]]></text></questiontext>
  <generalfeedback format="html"><text>...</text></generalfeedback>
  <answer fraction="100"><text><![CDATA[<p>Correcte</p>]]></text></answer>
  <answer fraction="-100"><text><![CDATA[<p>Fausse</p>]]></text></answer>
  <tags><tag><text>annale 2024</text></tag><tag><text>hemato</text></tag></tags>
</question>
```

### Conversion fractions
Moodle stocke en % → DB : `fraction = round(pct / 100, 6)`
- Fraction snappée vers la plus proche valeur autorisée via `_snap_fraction(pct)`
- Retourne `(float, str)` → `fraction` (float pour les tests) + `fraction_str` (string matching `FRACTION_CHOICES` pour la pré-sélection template)

**Valeurs autorisées** : `1.0`, `0.5`, `0.333333` (1/3), `0.25`, `0.0`, `-1.0`

### Structure retournée par question
```python
{
    "text": str,            # HTML de l'énoncé
    "feedback": str,        # HTML du feedback
    "answers": [{"text": str, "fraction": float, "fraction_str": str}],
    "xml_tags": [str],      # Noms de tags depuis <tags> du XML
}
```

### Tags depuis XML
- `xml_tags` = liste de noms de tags extraits de `<tags><tag><text>...</text></tag></tags>`
- Matching case-insensitive en base dans `AdminQuestionsPreviewView` → `matched_tag_ids` (PKs) + `matched_xml_names` (noms lowercase matchés)

---

## Flux de vues

| URL | Vue | Action |
|-----|-----|--------|
| `GET /questions/upload/` | `AdminQuestionsUploadView` | Formulaire upload + bandeau succès `?success=N` |
| `POST /questions/upload/` | `AdminQuestionsUploadView` | Parse XML → `session["upload_questions"]` → redirect preview |
| `GET /questions/upload/preview/` | `AdminQuestionsPreviewView` | Lit session → rendu formulaire édition |
| `POST /questions/confirmer/` | `AdminQuestionsConfirmView` | Sauvegarde DB + clear session |

**Session vide sur preview** → redirect vers upload.

### `AdminQuestionsConfirmView` : champs de formulaire
- `category_id`, `q_count`
- `q_{n}_text`, `q_{n}_feedback` (hidden inputs synchés par Quill si accordéon ouvert)
- `q_{n}_a_count`, `q_{n}_a_{m}_text`, `q_{n}_a_{m}_fraction`
- `q_{n}_tag_ids` (liste, `request.POST.getlist(...)`)

**Piège** : les questions dont l'accordéon n'est pas ouvert (Quill non init) ont leur texte dans les hidden inputs pré-remplis à la valeur originale du XML — elles ne sont pas perdues.

---

## Templates

### `admin_questions_upload.html`
- `<input type="file" accept=".xml">`
- Pas de sélection de catégorie ici (elle est dans la preview)
- Bandeau `?success=N` avec `pluralize`

### `admin_questions_preview.html`
- Quill chargé via `{% block extra_head %}` (CDN 1.3.7) — même version que l'errata
- Quill **initialisé paresseusement** à `show.bs.collapse` pour éviter de créer des dizaines d'instances au chargement
- Hidden inputs `q_{n}_text` / `q_{n}_feedback` pré-remplis avec le texte brut (utilisés si l'accordéon n'est jamais ouvert)
- Au submit : sync Quill → hidden inputs pour les questions ayant été ouvertes
- Tags depuis XML : badges bleus (matchés en base) / orange+? (non trouvés), bouton "Changer les tags" toggle la div de sélection complète
- Tags précochés dans les checkboxes via `{% if tag.pk|stringformat:"s" in q.matched_tag_ids %}checked{% endif %}`

### Fractions pré-sélectionnées
Comparaison template : `{% if ans.fraction_str == val %}selected{% endif %}` (string == string, pas de problème de type)

---

## Constantes dans `qcm/views.py`

```python
FRACTION_CHOICES = [("1.0", "+1,00 (correcte)"), ...]
FRACTION_CHOICES_JSON = json.dumps([[val, label] for val, label in FRACTION_CHOICES])
```
Placées APRÈS les imports (éviter E402 ruff).

---

## Navbar

Onglet "Questions" ajouté dans `qcm/templates/qcm/base.html` (staff uniquement), avant l'onglet Erratas.

---

## Tests : `tests/test_admin_questions.py` — 21 tests

- Parser : 10 tests (multichoice seulement, fractions, tags, ValueError)
- Vues upload/preview/confirm : 11 tests
- Upload utilise `SimpleUploadedFile` (pas de tuple — le test client Django n'accepte pas les tuples pour les fichiers)
- Session obsolète (avant fix `xml_tags`) → tags absents ; l'utilisateur doit re-uploader

---

## Points d'attention

- `FRACTION_CHOICES` doit rester synchronisé avec `_FRACTION_MAP` dans `question_upload.py` — les `fraction_str` doivent matcher exactement les valeurs dans `FRACTION_CHOICES`
- Quill dans le preview : le `rebuildAnswerNames(container)` JS est appelé au load pour corriger les noms d'inputs (Django template génère des indices incorrects pour les réponses — le `forloop.counter0` de la réponse utilise l'index extérieur plutôt que l'interne)
