# UX légendes interactives : compact label au blur + overlay correction — Issue #84

## Résumé

Deux améliorations UX pour les questions `ddimageortext` (légendes interactives), purement frontend — aucune modification des vues Python ni des modèles.

---

## Feature 1 — Compact label au blur (`qcm/templates/qcm/_ddimageortext_question.html`)

### Comportement

Quand l'utilisateur remplit un champ et quitte (blur), l'`<input>` disparaît et est remplacé par un `<span class="ddi-compact-label">` affichant la réponse saisie. En recliquant sur ce span, l'input réapparaît prêt à être modifié (`.focus()` + `.select()`).

L'`<input>` n'est **jamais retiré du DOM** — il est seulement caché via `style.display = 'none'`. Cela garantit que sa valeur est bien soumise au POST du formulaire.

### Implémentation

Dans le `<script>` inline, pour chaque `.ddi-input` :
- Création dynamique d'un `<span class="ddi-compact-label">` inséré **avant** l'input via `insertBefore`.
- Listener `blur` : si valeur non vide → remplir le span, cacher l'input, afficher le span.
- Listener `click` sur le span : cacher le span, afficher l'input, focus + select.
- Listener `input` : maintien de la classe `.filled` (pour la transition de largeur CSS quand l'input est réaffiché avant blur).

### CSS ajouté

`.ddi-compact-label` : pill bleue (`rgba(13,110,253,0.85)`), `border-radius:1rem`, `max-width:5rem`, `text-overflow:ellipsis`, `cursor:pointer`.

---

## Feature 2 — Image overlay dans la correction (`qcm/templates/qcm/_correction.html`)

### Comportement

Après soumission, le schéma reste affiché avec les réponses **positionnées sur l'image** (mêmes coordonnées xleft/ytop que les zones de saisie). Chaque réponse est affichée comme un label coloré :
- Fond vert (`rgba(25,135,84,0.85)`) pour les bonnes réponses → classe `.correct`
- Fond rouge (`rgba(220,53,69,0.85)`) pour les mauvaises → classe `.incorrect`
- Hover sur une mauvaise réponse → tooltip Bootstrap 5 avec `"Attendu : {correct_label}"` + `"— Alternatives : {accepted_labels_text}"` si des alternatives existent

Si aucune image de fond n'est attachée à la question, le bloc overlay n'est pas rendu (le `{% if bg_image %}` garde le code HTML propre).

### Implémentation

Dans `_correction.html`, dans le bloc `{% if question.qtype == "ddimageortext" %}` :
- `{% with bg_image=question.images.first %}` — accès direct via la relation ORM, pas de changement de contexte de vue.
- Structure `.ddi-result-container` / `.ddi-result-zone` / `.ddi-result-label` analogue à celle de la question, mais en lecture seule.
- Scaling JS `ddiResultScale(img)` identique à `ddiScaleZones()` de la question — **redéfini dans `_correction.html`** car le contenu HTMX remplace `#answers-zone` et le script de la question n'est plus dans le DOM après soumission. Fonction nommée différemment pour éviter les collisions.
- Les tooltips Bootstrap 5 sont initialisés via `new bootstrap.Tooltip(el)` à l'intérieur de `ddiResultScale()` (après scaling), donc ils fonctionnent même si l'image charge depuis le cache (le `var _rImg = ...; if (_rImg.complete)` au bas du script gère ce cas).
- La liste textuelle existante (zones numérotées avec ✓/✗) est **conservée en dessous** comme résumé accessible.

### Piège tooltip vs test

Le JavaScript contient la chaîne `'[data-bs-toggle="tooltip"]'` dans son sélecteur. Les tests qui cherchent `b'data-bs-toggle="tooltip"'` dans le HTML doivent donc distinguer la présence d'un attribut HTML d'une occurrence dans du code JS. Solution retenue : tester la présence de `b"Attendu"` (chaîne qui n'apparaît que dans les attributs `title` des mauvaises réponses, jamais dans du JS) pour le test négatif (aucune mauvaise réponse → aucun `"Attendu"` dans la réponse HTTP).

---

## Tests (`tests/test_ddimageortext.py`)

Nouvelle fixture `bg_image(ddi_question)` : crée un `QuestionImage` avec `moodle_filename="background"` et un faux fichier PNG via `ContentFile(b"\x89PNG\r\n\x1a\n")`. Fonctionne avec le `media_root_tmp` autouse de `conftest.py` — Django crée automatiquement le dossier `question_images/` dans le MEDIA_ROOT temporaire.

Nouvelle classe `TestCorrectionDDIImageOverlay` (8 tests) :
- Présence de `ddi-result-container` avec image de fond
- Classes `.correct` et `.incorrect` selon la justesse
- Attribut `data-bs-toggle="tooltip"` sur les mauvaises réponses
- Contenu du tooltip : `correct_label` + alternatives `accepted_labels_text`
- Absence de `b"Attendu"` quand toutes les réponses sont correctes
- Absence de `ddi-result-container` sans image de fond

Aucune modification des vues Python → aucun nouveau test de vue Python nécessaire pour le comportement serveur.

---

## Ce qui ne change PAS

- `qcm/views.py` : `_handle_ddimageortext`, `_build_zone_results`, `match_zone_label` — inchangés
- Modèles : aucun changement
- La liste textuelle (✓/✗ par zone) dans `_correction.html` : conservée comme affichage de secours/résumé
- Le fallback "liste sans image" de `_ddimageortext_question.html` : inchangé

## Issues liées

- Issue #84 (cette session)
- Mémoire précédente sur ddimageortext : `260620-0151-ddimageortext-admin-crud-multilabel.md`
- Mémoire sur l'isolation MEDIA_ROOT en test : `260630-2320-isolation-media-root-tests.md`
