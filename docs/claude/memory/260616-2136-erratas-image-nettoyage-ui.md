# Erratas IMAGE : nettoyage de l'interface admin (issue #60)

## Contexte

Les erratas de type **IMAGE** (`Errata.IMAGE = "image"`) sont créés automatiquement par `seed_image_erratas` lorsqu'une question contient une référence `@@PLUGINFILE@@/...` non résolue. La description auto-générée contient le chemin brut Moodle, et le formulaire d'upload exposait un champ texte permettant de modifier le nom de fichier Moodle — deux éléments inutiles et déroutants pour l'admin.

## Modifications apportées

### Template principal : `qcm/templates/qcm/errata_list.html`

**Input `moodle_filename` → hidden** (ligne ~296) :
- L'input `type="text"` visible avec son label "Nom du fichier Moodle" et son texte d'aide (`@@PLUGINFILE@@/...`) est devenu un `<input type="hidden">`.
- La valeur reste auto-remplie via `{{ e.question.text|pluginfile_names|first }}`.
- Le backend `ErrataUploadImageView` lit `request.POST["moodle_filename"]` sans changement.

**Champ "Description" → masqué pour IMAGE** :
- Condition ajoutée : `{% if e.description and e.error_type != 'image' %}`.
- La description auto-générée (chemin `@@PLUGINFILE@@`) ne s'affiche plus.

### Template partiel : `qcm/templates/qcm/_errata_tags_and_meta.html`

**Champ "Description signalée" → masqué pour IMAGE** :
- Même condition : `{% if e.description and e.error_type != 'image' %}`.
- Ce partial est inclus dans les branches correction, points et qroc_answer aussi — la condition ne les affecte pas (leurs erratas ne sont pas de type `image`).

## Tests ajoutés

Nouveau fichier `tests/test_erratas.py` (5 tests, classe `TestErrataImageTemplate`) :

- `test_moodle_filename_label_not_visible` — "Nom du fichier Moodle" absent du HTML
- `test_moodle_filename_helper_text_not_visible` — `@@PLUGINFILE@@` absent du HTML rendu
- `test_moodle_filename_hidden_input_present` — `type="hidden" name="moodle_filename"` présent (fonctionnalité préservée)
- `test_description_signalee_not_shown_for_image` — "Description signal" absent pour IMAGE
- `test_description_not_shown_for_image` — texte de la description auto-générée absent

## Pattern à retenir

Pour les erratas IMAGE, toute information interne Moodle (noms de fichiers, chemins `@@PLUGINFILE@@`, descriptions auto-générées) doit être masquée de l'UI admin. Ces données sont utiles en backend mais sans valeur affichée.

Le filtre template `pluginfile_names` (dans `qcm/templatetags/qcm_extras.py`) extrait les noms de fichiers depuis le texte d'une question — il est utilisé pour pré-remplir le champ hidden.
