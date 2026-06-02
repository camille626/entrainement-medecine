---
date: 2026-06-02
issue: "#31"
branch: 31-nouveau-type-de-question-qroc-réponse-ouverte-courte
status: implémenté, testé, validé utilisateur — PR à créer
---

# QROC — Questions à Réponse Ouverte Courte (issue #31)

## Vue d'ensemble

Nouveau type de question `shortanswer` (existait dans le modèle mais inutilisé). L'étudiant tape sa réponse librement au lieu de cocher des cases. 61 questions importées depuis le dump Moodle.

---

## Modèles modifiés

### `UserAnswer` (`qcm/models.py`)
- `answer` : FK **nullable** (`null=True, blank=True`) — `None` pour les auto-évaluations QROC
- `qroc_text = TextField(null=True, blank=True)` — texte tapé par l'étudiant
- `is_self_evaluated = BooleanField(default=False)` — True si l'étudiant s'est auto-évalué
- Propriété `effective_fraction` : retourne `answer.fraction` si answer non-null, sinon `1.0` si `is_correct` else `0.0`
- **Important** : tous les calculs de score dans les vues utilisent maintenant `ua.effective_fraction` au lieu de `ua.answer.fraction` (qui planterait sur None)

### `Errata` (`qcm/models.py`)
- Nouveau type `QROC_ANSWER = "qroc_answer"` : "Ma réponse est correcte (QROC)"
- `qroc_suggested_text = TextField(blank=True)` — réponse suggérée par l'étudiant
- `qroc_suggested_fraction = FloatField(null=True, blank=True)` — fraction assignée par l'admin

Migration : `qcm/migrations/0019_qroc_useranswer_errata.py`

---

## Logique de validation (`qcm/views.py`)

### `normalize_qroc(text)`
Minuscules + strip + suppression des accents via `unicodedata.NFD`. Ex : "Éléphant" → "elephant".

### `match_qroc_answer(question, user_text)`
Cherche une correspondance dans les `Answer` de la question. Deux modes :
- **Exact** (après normalisation) : `"sept"` correspond à `"sept"`, `"SEPT"`, `"sèpt"`
- **Joker Moodle** (`*`) : si le pattern de la réponse acceptée contient `*`, utilise `fnmatch.fnmatch`. Ex : `"myélome*"` correspond à `"myélome classique"`, `"myélome multiple"`. Le `*` est normalisé AVANT le match.

---

## Flux UX session

### Configuration
- Checkbox "Inclure les QROC" dans `qcm/templates/qcm/configuration.html`
- `SessionConfigForm.include_qroc = BooleanField(required=False, initial=False)` dans `qcm/forms.py`
- `ConfigurationView` filtre `qtype__in=["multichoice", "shortanswer"]` si coché

### Affichage question (`qcm/templates/qcm/question.html`)
- Condition `{% elif question.qtype == "shortanswer" %}` pour afficher le champ texte au lieu des checkboxes
- Les deux formulaires (QROC et multichoix) envoient un champ `question_id` caché pour éviter le bug "mauvaise question traitée" lors de la navigation

### Soumission

**Route 1 — correspondance automatique** → `CheckView._handle_qroc()` → crée `UserAnswer(answer=matched_answer)` → retourne `_correction.html` (branche QROC)

**Route 2 — pas de correspondance** → retourne `_qroc_ambiguous.html` avec :
- La réponse tapée
- Les variantes acceptées
- Boutons "J'avais bon" / "J'avais faux" → POST vers `CheckQROCSelfView`

**Route 3 — auto-évaluation** → `CheckQROCSelfView` → crée `UserAnswer(answer=None, is_self_evaluated=True)` → retourne `_correction.html`

**Bug critique résolu** : `CheckView` et `CheckQROCSelfView` utilisent `question_id` du POST (pas "première question non répondue") pour gérer la navigation entre questions.

### Correction QROC (`qcm/templates/qcm/_correction.html`)
Branche `{% if question.qtype == "shortanswer" %}` :
- Affiche la réponse tapée et le statut (✓/✗)
- Liste les variantes acceptées avec leurs fractions
- Si question QROC avec `qroc_text`, le bouton "Signaler une erreur" pré-remplit le formulaire errata avec `prefill_type=qroc_answer`

---

## URL ajoutée

`/entrainement/session/<pk>/check-qroc/` → `CheckQROCSelfView` (dans `qcm/urls.py`)

---

## Errata QROC

### Formulaire signalement (`qcm/templates/qcm/_errata_form.html`)
- Option "Ma réponse est correcte (QROC)" dans les types
- Zone `#qroc-zone-{pk}` avec champ texte pré-rempli via `prefill_qroc_text` et `prefill_type`
- Depuis `_qroc_ambiguous.html` : le bouton "Suggérer" passe `?qroc_text=...&prefill_type=qroc_answer` → auto-sélectionne le radio et pré-remplit le champ

### Page admin erratas (`qcm/templates/qcm/errata_list.html`)
Nouvelle branche dédiée `qroc_answer` (entre "points" et "else") :
- Affiche les variantes actuellement acceptées
- Affiche la suggestion de l'utilisateur en évidence
- Champ numérique pour la fraction (défaut 1.00, modifiable)
- Bouton "Accepter — ajouter « X » aux réponses"

### `ErrataAcceptView` (`qcm/views.py`)
Branche `elif errata.error_type == Errata.QROC_ANSWER` :
- Lit `qroc_fraction` du POST (défaut 1.0, clampé [0,1])
- `Answer.objects.get_or_create(question=..., text=suggested_text, defaults={fraction, is_correct})`

### `ErrataSubmitView` (`qcm/views.py`)
Stocke `qroc_suggested_text` du POST dans l'errata créé.

---

## Import Moodle

### Changements dans `qcm/management/commands/import_moodle.py`
- `_import_questions` : accepte `{"multichoice", "shortanswer"}` au lieu de `"multichoice"` uniquement
- Fonction `_decode_pg_copy(text)` centralisée : décode les séquences d'échappement PostgreSQL COPY (`\r\n` → `<br>`, `\n` → `<br>`, `\r` → `""`) pour les textes de questions ET de réponses (les réponses n'étaient pas décodées avant)
- 61 questions `shortanswer` + 202 réponses importées depuis le dump Moodle

### `moodle_parser.py`
- `_find_pg_restore()` : cherche `pg_restore` dans plusieurs chemins (`/usr/bin/`, `/usr/lib/postgresql/17/`, etc.) au lieu du chemin PG17 en dur
- Le devcontainer (`Dockerfile`) installe maintenant `postgresql-client-17` depuis le dépôt PGDG

---

## Calculs de score — impact transversal

Partout où les scores utilisaient `ua.answer.fraction` (planterait avec `answer=None`), remplacé par :
- En Python loop : `ua.effective_fraction`
- En `.values()` query : `_ua_fraction(r["answer__fraction"], r["is_correct"])` (retourne la fraction ou 1.0/0.0 selon `is_correct`)

Fichiers impactés : `QuestionView`, `CheckView`, `FinView`, `StatsView`, `HistoryView`, `SessionDetailView`, `CourseStatsView`, `_compute_course_block`.

Les filtres `qtype="multichoice"` dans les comptages de questions disponibles (`nb_available`) ont aussi été élargis à `qtype__in=["multichoice", "shortanswer"]`.

---

## Tests

Fichier `tests/test_qroc.py` (39 tests) couvre :
- `normalize_qroc` : casse, accents, strip, chiffres romains
- `match_qroc_answer` : exact, insensible casse/accents, joker `*`, vide, pas de match
- `UserAnswer` avec `answer=None` : création, `effective_fraction` correct/incorrect/avec answer
- `Errata.QROC_ANSWER` : création, fraction nulle
- `CheckView` QROC : auto-match, insensible casse, ambiguous template, réponse vide
- `CheckQROCSelfView` : bon, faux, correction renvoyée
- `SessionConfigForm` : champ `include_qroc`, défaut False
- `ConfigurationView` : session avec/sans QROC selon checkbox
- Import Moodle : test structurel

`tests/test_import_moodle.py` mis à jour : `test_imports_multichoice_and_shortanswer_questions` (Q202 shortanswer maintenant importée), `test_idempotent` (count=2).
