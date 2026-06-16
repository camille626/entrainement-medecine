# Quill éditeur riche dans le formulaire de question (issue #68)

## Contexte

Le formulaire d'édition de question (`/admin-site/questions/<pk>/modifier/`) affichait
les champs "Énoncé" et "Correction générale" dans des `<textarea>` bruts avec `|striptags`,
ce qui détruisait le HTML Moodle (gras, retours à la ligne, listes, etc.). L'objectif
était d'intégrer l'éditeur riche Quill 1.3.7 (déjà utilisé dans `errata_list.html`) pour
ces deux champs.

## Modifications

### `qcm/templates/qcm/admin_site/question_form.html`

**Ajout de `{% block extra_head %}`** (avant `{% block content %}`) :
```html
<link href="https://cdn.quilljs.com/1.3.7/quill.snow.css" rel="stylesheet">
```

**Remplacement des deux `<textarea>` par le pattern Quill** :
- Suppression de `<textarea name="text" ...>{{ question.text|striptags }}</textarea>`
- Remplacement par :
  ```html
  <template id="text-tpl">{% if question %}{{ question.text|safe }}{% endif %}</template>
  <div id="quill-text" class="bg-white border rounded" style="min-height:100px;"></div>
  <input type="hidden" name="text" id="quill-text-input">
  ```
- Même pattern pour `feedback` (id `feedback-tpl`, `quill-feedback`, `quill-feedback-input`)

**Ajout de `{% block extra_scripts %}`** (après `{% endblock content %}`) :
```html
<script src="https://cdn.quilljs.com/1.3.7/quill.min.js"></script>
<script>
(function () {
  function initQuill(editorId, inputId, tplId) {
    const tpl = document.getElementById(tplId);
    const quill = new Quill('#' + editorId, { theme: 'snow' });
    if (tpl) quill.root.innerHTML = tpl.innerHTML;
    const input = document.getElementById(inputId);
    input.value = quill.root.innerHTML;
    quill.on('text-change', function () { input.value = quill.root.innerHTML; });
  }
  initQuill('quill-text', 'quill-text-input', 'text-tpl');
  initQuill('quill-feedback', 'quill-feedback-input', 'feedback-tpl');
})();
</script>
```

### `tests/test_question_form_quill.py` (nouveau fichier)

8 tests dans `TestQuestionFormQuill` :
- `test_quill_css_loaded` — `quill.snow.css` dans le HTML
- `test_quill_js_loaded` — `quill.min.js` dans le HTML
- `test_no_textarea_for_text` — pas de `<textarea name="text"`
- `test_no_textarea_for_feedback` — pas de `<textarea name="feedback"`
- `test_hidden_input_for_text` — `type="hidden" name="text"` présent
- `test_hidden_input_for_feedback` — `type="hidden" name="feedback"` présent
- `test_html_content_preserved_in_text` — `<strong>` dans le HTML de la page
- `test_html_content_preserved_in_feedback` — `<br>` dans le HTML de la page

## Pattern à retenir

**Pattern Quill dans les templates Django** :
1. `<template id="xxx-tpl">{{ valeur|safe }}</template>` pour injecter le HTML sans auto-escape
2. `<div id="quill-xxx">` comme conteneur de l'éditeur
3. `<input type="hidden" name="xxx" id="quill-xxx-input">` pour la soumission du formulaire
4. Init JS : `quill.root.innerHTML = tpl.innerHTML` + sync sur `text-change`
5. Sync immédiat après init pour les soumissions sans modification

Ce pattern est identique à celui de `errata_list.html` (template element → Quill → hidden input).

## Backend inchangé

`AdminQuestionEditView.post()` dans `qcm/views_admin.py` lit `request.POST.get("text")`
et `request.POST.get("feedback")` et les stocke tels quels — aucune modification nécessaire.
Le HTML produit par Quill est directement compatible.

## Limitation : champ required

Le `required` HTML5 ne fonctionne pas sur les inputs `type="hidden"`. La validation
est assurée côté backend : si `text` est vide, `question.text` n'est pas mis à jour
(comportement conservatif). Une validation JS pourrait être ajoutée en bloquant la
soumission si `quill.getText().trim()` est vide.
