# Issue #111 — Préservation des retours à la ligne (questions & erratas)

## Contexte

Demande initiale : garder la mise en forme (retours à la ligne) des textes de
question telle qu'elle apparaît côté utilisateur, y compris lors de leur
création/modification. L'investigation a révélé **trois bugs distincts**, dont
un bien plus grave et plus large que prévu initialement.

## Bug 1 — Admin Django natif divergent (`qcm/admin.py`)

`QuestionAdmin` exposait `text`/`feedback` via un `<textarea>` brut dans
`/admin/qcm/question/<pk>/change/`, alors que ces champs stockent du HTML
produit par l'éditeur Quill custom (`/admin-site/questions/...`). Un `\n` tapé
là restait un `\n` brut, jamais converti en `<br>`/`<p>`, donc invisible à
l'affichage entraînement (`|safe` sans `linebreaksbr`).

**Fix** : `readonly_fields = ["text", "feedback"]` sur `QuestionAdmin`
(`qcm/admin.py`), pour forcer l'édition via l'éditeur Quill. Cohérent avec un
précédent déjà en place : `AnswerInlineForErrata.readonly_fields = ["text"]`
et la politique déjà actée dans `tests/test_erratas.py::TestErrataModifyQuestionLink`
(aucun lien admin natif proposé pour éditer une question).

`AnswerAdmin` volontairement laissé inchangé : `Answer.text` est saisi via un
`<input type="text">` mono-ligne dans le formulaire custom, la saisie
multi-ligne y est physiquement impossible.

## Bug 2 — Affichage errata sans conversion des retours à la ligne

`Errata.description`/`Errata.admin_note` sont du texte brut saisi via
`<textarea>`/`<input>`, affichés sans aucun filtre (`{{ e.description }}`)
dans `qcm/templates/qcm/_errata_tags_and_meta.html`,
`qcm/templates/qcm/errata_list.html` (×2 emplacements) et
`qcm/templates/qcm/_errata_form.html`. Aucun `linebreaksbr` ni
`white-space:pre-wrap` n'existait nulle part dans le repo.

**Fix** : ajout du filtre `linebreaksbr` (Django, échappe le HTML avant
conversion, pas de risque XSS) aux 4 emplacements concernés.

## Bug 3 — Perte de mise en forme dans l'éditeur Quill lui-même (le plus grave)

Découvert après une capture d'écran utilisateur montrant une correction
générale totalement illisible : `"Correction : A. VRAIB. FAUXC. FAUXD. VRAIE. VRAI"`.

**Cause racine** : `quill.root.innerHTML = tpl.innerHTML`
(`qcm/templates/qcm/admin_site/question_form.html:739` avant fix) charge le
HTML existant en assignation DOM directe. Or **Quill 1.3.7, par défaut, ne
préserve pas visuellement un `<br>` interne à un `<p>`** — sa représentation
native du texte multi-ligne est un `<p>` par ligne, pas un `<br>` en milieu de
bloc. Tout contenu stocké au format `<p>A. VRAI<br>B. FAUX<br>...</p>`
(format très répandu, utilisé par les admins pour lister les corrections par
proposition A/B/C/D/E) s'affichait donc collé sur une seule ligne dans
l'éditeur.

**Gravité** : vérifié sur les données réelles via `manage.py shell` —
**2264 questions** ont un `feedback` touché par ce motif, **253** ont un
`text` touché. Risque de **perte de données définitive** : si un admin ouvre
une de ces questions (même sans y toucher) et sauvegarde, Quill réécrit le
contenu sans les séparateurs. Même risque à la prévisualisation d'import
(`/questions/upload/preview/`) dès qu'un accordéon est ouvert avant
confirmation.

**Fix** : nouveau filtre de template `quillify`
(`qcm/templatetags/qcm_extras.py`) — scinde chaque `<p>` contenant un `<br>`
interne en plusieurs `<p>` (un par ligne), via une regex ciblée
(`_P_WITH_BR_RE`/`_BR_RE`) qui ne touche que le contenu strictement à
l'intérieur d'un `<p>...</p>`, sans toucher aux `<br>` situés en dehors (motif
« paragraphe séparé par un `<br>` isolé », lui déjà correctement affiché par
Quill, laissé intact).

Filtre purement d'affichage, appliqué uniquement à la population des
`<template>` chargés dans Quill — **la donnée en base n'est jamais modifiée
directement**. Dès qu'un admin resauvegarde via Quill, le format se
« répare » de lui-même (Quill produit nativement un `<p>` par ligne).

Appliqué à 3 emplacements (mêmes 3 endroits où `quill.root.innerHTML =
tpl.innerHTML` est utilisé) :
- `qcm/templates/qcm/admin_site/question_form.html` (édition question)
- `qcm/templates/qcm/admin_questions_preview.html` (prévisualisation import)
- `qcm/templates/qcm/errata_list.html` (correction générale éditée depuis un errata)

Voir aussi `[[260616-2315-quill-editeur-question-form]]` pour l'introduction
initiale de ce pattern Quill (issue #68) — le bug des `<br>` internes existait
dès l'origine, non détecté car les tests de l'époque ne vérifiaient que la
présence du HTML brut dans la page (`assert "<br>" in content`), pas son rendu
visuel réel dans l'éditeur.

## Tests ajoutés

- `tests/test_question_native_admin.py` (nouveau) — `text`/`feedback` en
  lecture seule dans l'admin natif, `course`/`tags` restent éditables.
- `tests/test_errata.py::TestErrataDescriptionLineBreaks` — `linebreaksbr`
  appliqué à `description`/`admin_note`.
- `tests/test_errata.py::TestErrataFeedbackQuillLineBreaks` — `<br>` interne
  scindé dans la correction générale affichée depuis `/errata/`.
- `tests/test_qcm_extras.py` (nouveau) — 7 tests unitaires purs sur le filtre
  `quillify` (attributs préservés, variantes `<br/>`/`<br />`, `<p>` non
  affectés inchangés, `<br>` hors `<p>` ignoré, entrée vide/`None`).
- `tests/test_question_form_quill.py::TestQuestionFormQuillLineBreaks` —
  scission appliquée à `text` et `feedback` dans le formulaire d'édition.
- `tests/test_admin_questions.py::TestAdminQuestionsPreviewView::test_inline_br_split_for_editing`
  — même vérification côté prévisualisation d'import.

## Piste écartée : normaliser les données en base

Une alternative envisagée était de migrer les 2517 questions affectées en
base pour remplacer `<br>` interne par des `<p>` séparés. Écartée au profit
du filtre d'affichage : plus sûr (aucune migration destructive sur des
milliers de lignes), auto-réparateur (le format se corrige à la prochaine
sauvegarde via Quill), et suffisant puisque l'affichage étudiant (`|safe`
simple, sans passer par Quill) rendait déjà `<br>` correctement — seul
l'éditeur Quill était en cause.
