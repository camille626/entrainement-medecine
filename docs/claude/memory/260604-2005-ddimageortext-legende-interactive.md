# Légendes interactives (ddimageortext) — Issue #30

## Résumé

Implémentation complète du type de question `ddimageortext` : l'utilisateur saisit le nom de chaque structure anatomique directement sur l'image, zone par zone, comme un QROC.

## Modèles ajoutés (`qcm/models.py`)

- `Question.DDIMAGEORTEXT = "ddimageortext"` — nouveau qtype dans les choix
- `ImageDragItem` — étiquettes possibles pour la question (FK → Question, `no`, `label`, `draggroup`)
  - `unique_together = [("question", "no")]`
  - related_name : `drag_items`
- `ImageDropZone` — zones cibles sur l'image (FK → Question, `no`, `xleft`, `ytop`, `correct_drag_no`, `correct_label`)
  - `unique_together = [("question", "no")]`
  - related_name : `drop_zones`
- `UserAnswer.fraction_override` — FloatField nullable pour stocker une fraction partielle (ex. 2/3 zones correctes)
  - `UserAnswer.effective_fraction` utilise ce champ en priorité sur `answer.fraction`

## Migration

`qcm/migrations/0022_ddimageortext.py` — ajoute les 2 modèles + `fraction_override`

## Import Moodle (`qcm/management/commands/import_moodle.py`)

- `ddimageortext` ajouté à `supported_qtypes`
- `_import_ddimageortext_data(data)` — importe drag items et drop zones depuis les tables Moodle :
  - `m_qtype_ddimageortext_drags` → `ImageDragItem`
  - `m_qtype_ddimageortext_drops` → `ImageDropZone` (avec `correct_label` dénormalisé depuis les drags)
- `_import_ddimageortext_images(data, moodledata_dir)` — copie les images de fond depuis `moodledata/filedir/{hash[:2]}/{hash[2:4]}/{hash}` vers Django media via `QuestionImage`
  - Auto-détecte `moodledata/` voisin du dump si `--moodledata` non fourni
  - Les 129 questions du dump ont toutes leurs images disponibles
- Idempotent (update_or_create)

## Structure des données Moodle

- `m_files` : `component='qtype_ddimageortext'`, `filearea='bgimage'`, `itemid = m_question.id` directement
- `m_qtype_ddimageortext_drags` : colonnes `questionid, no, draggroup, infinite, label`
- `m_qtype_ddimageortext_drops` : colonnes `questionid, no, xleft, ytop, choice, label`
  - `choice` = le `no` du drag correct pour cette zone

## Vues (`qcm/views.py`)

### Helpers
- `_build_zone_results(question, qroc_text)` — reconstruit les résultats par zone depuis le JSON stocké en `qroc_text`. Compare avec `normalize_qroc()` (insensible casse/accents)
- `_max_score_for_question(question)` — retourne 1.0 pour ddimageortext et shortanswer, sinon somme des fractions positives

### ConfigurationView
- Nouveau champ `include_ddimageortext` → ajoute `"ddimageortext"` aux qtypes filtrés

### QuestionView
- Passe `drag_items` et `drop_zones` dans le contexte pour les questions ddimageortext

### CheckView._handle_ddimageortext
- Lit les POST `zone_{no}` comme texte libre (QROC style)
- Compare avec `normalize_qroc(zone.correct_label)` — insensible casse/accents
- Stocke dans `UserAnswer.qroc_text` le JSON `{"1": "sclérotique", "2": "choroide", ...}`
- `UserAnswer.fraction_override = correct_zones / total_zones`

### FinView / SessionDetailView
- Appellent `_build_zone_results` pour reconstituer les résultats par zone dans la page récapitulatif

## Templates

- `qcm/templates/qcm/_ddimageortext_question.html` — nouveau template :
  - Image de fond avec zones positionnées en `position:absolute`
  - Inputs texte **compacts (1.6rem)** qui s'élargissent à 9rem au focus ou si remplis (transition CSS)
  - JS `ddiScaleZones()` pour adapter les positions pixel aux dimensions réelles de l'image affichée (responsive)
  - Fallback liste sans image
- `qcm/templates/qcm/_correction.html` — branche ddimageortext : affiche vert/rouge par zone avec la réponse saisie vs le label attendu
- `qcm/templates/qcm/fin.html` — affiche les zones dans la page résultats (accordion)
- `qcm/templates/qcm/configuration.html` — checkbox "Inclure les légendes interactives"
- `qcm/templates/qcm/question.html` — branche `{% elif question.qtype == "ddimageortext" %}`

## Formulaire (`qcm/forms.py`)

- `include_ddimageortext = BooleanField(required=False)` dans `SessionConfigForm`

## Tests (`tests/test_ddimageortext.py`)

- 25 tests couvrant : modèles, fraction_override, CheckView (tout correct / partiel / tout faux / insensible casse), import idempotent, contexte QuestionView

## Comportements importants

- La saisie est **insensible à la casse et aux accents** (ex. "SCLEROTIQUE" = "sclérotique")
- Les distracteurs (drag items sans zone associée) ne jouent aucun rôle dans la notation — ils n'étaient utilisés que pour les menus déroulants, qui ont été remplacés par la saisie libre
- `UserAnswer.answer` reste `null` pour ddimageortext (comme QROC auto-évalué)
- Les stats (`nb_available`) n'incluent pas encore ddimageortext — déféré

## Issues liées

- Issue #30 (cette PR)
- Issue #54 — erratas pour ddimageortext (à implémenter)
- Issue #55 — création/modification de questions ddimageortext depuis l'admin web (à implémenter)
