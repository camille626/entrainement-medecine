# Erratas : bouton "Modifier la question" → éditeur custom (issue #62)

## Contexte

Le bouton "Modifier la question" dans `errata_list.html` pointait vers l'admin Django
(`/admin/qcm/question/<pk>/change/`). Cet admin ne permet pas de voir ni modifier
facilement les propositions de réponse. L'éditeur custom
`/admin-site/questions/<pk>/modifier/` offre une interface complète (propositions,
tags, images).

Par ailleurs, le formulaire de l'éditeur custom affichait inutilement le label
"Nom du fichier Moodle" lors de l'upload d'image.

## Modifications

### `qcm/templates/qcm/errata_list.html`

4 occurrences de liens vers l'admin Django remplacées par l'éditeur custom :

```
/admin/qcm/question/{{ e.question_id }}/change/
→ /admin-site/questions/{{ e.question_id }}/modifier/?back=/errata/
```

Le paramètre `?back=/errata/` est lu par `AdminQuestionEditView.get()` via
`request.GET.get('back', '/admin-site/questions/')` pour afficher le bon bouton retour.

### `qcm/templates/qcm/admin_site/question_form.html`

Champ "Nom du fichier Moodle" (label + input text + texte d'aide) remplacé par
`<input type="hidden" name="new_image_filename" value="...">`. La valeur est
auto-remplie via `{{ question.text|pluginfile_names|first }}`. Le backend
`AdminQuestionEditView.post()` lit `request.POST.get('new_image_filename')` sans
changement.

## Pattern à retenir

La vue `AdminQuestionEditView` accepte `?back=<url>` en GET pour contrôler l'URL
du bouton retour. Utiliser ce paramètre depuis tous les points d'entrée extérieurs
(erratas, sessions, etc.).

## Limite connue / issue future

Les textarea `text` et `feedback` dans l'éditeur custom affichent le HTML brut
(`|striptags` dans le template). Une future issue devra ajouter Quill à ces deux
champs pour un éditeur riche (formatage, retours à la ligne visibles).
