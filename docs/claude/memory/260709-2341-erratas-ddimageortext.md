# Erratas pour les questions ddimageortext (issue #54)

## Contexte

Le système d'erratas (issue #19) était conçu autour des `Answer` (CORRECTION, POINTS, QROC_ANSWER opèrent tous sur `question.answers.all()`). Les questions `ddimageortext` (légende interactive, issue #30) n'ont pas de `Answer` — la correction porte sur `ImageDropZone`/`ImageDropZoneLabel`. Le formulaire de signalement affichait donc des sections vides/inutilisables pour ces questions, et la liste admin ne les affichait pas correctement.

Spec validée avec l'utilisateur (voir commentaire sur l'issue #54) : pour ddimageortext, seuls 4 types d'erreur sont proposés : **Image manquante**, **Erreur de tag**, **Autre**, et un nouveau type **« Une de mes réponses est correcte »** où l'utilisateur clique directement sur la zone contestée dans l'image de correction (au lieu de taper du texte libre comme pour QROC). CORRECTION et POINTS restent hors périmètre pour ddimageortext — l'admin dispose déjà de l'éditeur complet de zones via `qcm/templates/qcm/admin_site/question_form.html`.

## Modifications apportées

### Modèle : `qcm/models.py`

- Nouveau type `Errata.DDI_ANSWER = "ddi_answer"` dans `TYPE_CHOICES`, inséré entre `QROC_ANSWER` et `OTHER`.
- Nouveau champ `Errata.concerned_zone` (FK vers `ImageDropZone`, `on_delete=SET_NULL`, nullable) — référencé en chaîne `"ImageDropZone"` car cette classe est définie plus bas dans le fichier.
- Le champ `qroc_suggested_text` est réutilisé tel quel pour DDI_ANSWER (texte de légende suggéré) — pas de nouveau champ, juste un commentaire/verbose_name mis à jour pour refléter l'usage double.
- Migration `qcm/migrations/0035_errata_concerned_zone_alter_errata_error_type_and_more.py`.

### Vues : `qcm/views.py`

- Nouvelle fonction `_errata_form_context(question, **overrides)` — factorise la construction du contexte partagé entre `ErrataSubmitView.get()` et les réaffichages d'erreur dans `post()` (corrige au passage un bug préexistant où le réaffichage après erreur de validation perdait `error_types`/`ec_tags`/`chapter_tags`, faisant disparaître les radios).
- `ErrataSubmitView.get()` filtre `error_types` à `{IMAGE, TAG, DDI_ANSWER, OTHER}` uniquement quand `question.qtype == Question.DDIMAGEORTEXT` — comportement inchangé pour les autres qtypes.
- `ErrataSubmitView.post()` : pour `error_type == DDI_ANSWER`, lit `ddi_zone_id` du POST, résout via `question.drop_zones.filter(pk=ddi_zone_id).first()` (le scope à `question.drop_zones` rejette naturellement une zone d'une autre question). Erreur si zone introuvable ou texte vide.
- `ErrataAcceptView.post()` : nouvelle branche `elif errata.error_type == Errata.DDI_ANSWER` qui fait `ImageDropZoneLabel.objects.get_or_create(zone=errata.concerned_zone, text=errata.qroc_suggested_text.strip())` — idempotent, no-op silencieux si `concerned_zone` est `None` (cas `SET_NULL` si la zone a été supprimée entre-temps).
- `ErrataUploadImageView` : **aucun changement Python**, déjà générique via `update_or_create`.

### Templates

- `qcm/templates/qcm/_correction.html` : les `.ddi-result-zone` portent désormais `data-zone-pk` et `data-selected-label`. Deux fonctions JS globales ajoutées : `ddiEnableZonePicking(qpk, enabled)` (idempotente via `dataset.ddiBound`) et `ddiSelectZone(qpk, zoneEl)` qui remplit le hidden `ddi_zone_id_<qpk>` et pré-remplit `qroc_text_<qpk>` avec la réponse soumise par l'utilisateur pour cette zone.
- `qcm/templates/qcm/_errata_form.html` : le bloc `#qroc-zone-` (texte suggéré) est réutilisé pour `qroc_answer` ET `ddi_answer`. Nouveau bloc `#ddi-zone-hint-` avec le hidden `ddi_zone_id`. `toggleErrataFields()` appelle `ddiEnableZonePicking` à chaque changement de type. Un script de fin de fragment réarme le zone-picking si le fragment est réaffiché avec `prefill_type == 'ddi_answer'` (le radio `checked` seul ne déclenche pas `onchange`).
- `qcm/templates/qcm/_ddi_zones_readonly.html` (nouveau partial) : affiche l'image de fond + toutes les zones en lecture seule (labels = `correct_label`), avec mise à l'échelle + `ResizeObserver` namespacés par `e.pk` (pas `question.pk`, pour éviter les collisions entre plusieurs erratas d'une même question dans l'accordéon). Inclus deux fois dans `errata_list.html` : génériquement pour tout errata ddi non-`ddi_answer` (contexte), et avec `highlight_zone=e.concerned_zone` dans la nouvelle branche.
- `qcm/templates/qcm/errata_list.html` : nouvelle **BRANCHE 3b** (`e.error_type == 'ddi_answer'`) entre la branche QROC et le `{% else %}` final — image avec zone mise en évidence, texte suggéré, bouton accepter (POST simple, pas de fraction contrairement à QROC). La boucle `e.question.answers.all` de la branche standard (tag/image/autre) est gardée par `{% if e.question.qtype != 'ddimageortext' %}` (toujours vide pour ddi). Le hidden `moodle_filename` du bloc IMAGE utilise `e.question.images.first.moodle_filename|default:'background'` pour ddimageortext au lieu de `pluginfile_names` (qui ne trouve jamais rien, l'image de fond n'étant jamais référencée en `@@PLUGINFILE@@` dans `question.text` — elle vient de `m_files`/`_import_ddimageortext_images` dans `import_moodle.py`).

## Tests ajoutés

- `tests/test_errata.py` : `DDI_ANSWER` dans `TYPE_CHOICES`, `concerned_zone` nullable, `SET_NULL` à la suppression de la zone.
- `tests/test_ddimageortext.py` : nouvelles classes `TestDDIErrataSubmission` (filtrage des types, validation zone/texte, rejet zone d'une autre question), `TestDDIErrataAccept` (création `ImageDropZoneLabel`, idempotence, no-op sur zone orpheline, garde staff), `TestDDIErrataZonePickingUI` (présence `data-zone-pk`, `ddiEnableZonePicking`, hidden input), `TestDDIErrataListDisplay` (branche ddi_answer, zone supprimée, contexte générique), `TestDDIErrataImageUpload` (fallback `"background"`, filename existant, upload réel).

## Vérification manuelle

Pas de navigateur/Chromium disponible dans le conteneur de dev — vérification faite via `requests` en Python contre le serveur `runserver` réel (pas seulement `pytest`) : formulaire filtré, soumission + validation, page admin avec la nouvelle branche, acceptation créant bien un `ImageDropZoneLabel` en base. L'utilisateur a ensuite confirmé le test visuel dans son navigateur sur les questions réelles du cours "P2 - système neurosensoriel et psychiatrie".

## Pattern à retenir

Quand un type de contenu (ici ddimageortext) n'a pas d'équivalent direct à un concept existant (`Answer`), éviter de forcer les branches existantes (CORRECTION/POINTS) à s'y adapter — préférer un nouveau type d'errata dédié qui réutilise les champs génériques déjà présents (`qroc_suggested_text`) plutôt que d'ajouter des champs redondants. Le filtrage des `error_types` proposés doit se faire côté vue (`_errata_form_context`), pas seulement côté template, pour que la validation serveur reste cohérente avec ce qui est affiché.
