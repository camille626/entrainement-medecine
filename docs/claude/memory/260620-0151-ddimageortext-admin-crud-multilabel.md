# Admin CRUD ddimageortext + réponses multiples par zone — Issue #55

## Résumé

Implémentation complète de la création/modification des questions `ddimageortext` (légende interactive) depuis `/admin-site/questions/`, sans passer par l'import Moodle. Ajout, en complément de l'issue GitHub, du support de plusieurs réponses acceptables par zone (`ImageDropZone`), par analogie avec le pattern QROC existant. Travail effectué sur la branche `55-admin-ajout-et-modification-des-questions-légendes-interactives-ddimageortext`, aucun commit encore créé au moment de la rédaction de cette mémoire (étape doc du workflow `/fix-issue`, commit à suivre).

## Modèle (`qcm/models.py`)

- Nouveau modèle `ImageDropZoneLabel` (après `ImageDropZone`) : FK `zone` → `ImageDropZone` (`related_name="accepted_labels"`, `on_delete=CASCADE`), `text` CharField. `correct_label` sur `ImageDropZone` reste le label principal (rétro-compatible avec les données Moodle déjà importées) ; `accepted_labels` ajoute des alternatives.
- Propriété `ImageDropZone.accepted_labels_text` (`qcm/models.py`) — `"; ".join(...)` des alternatives, utilisée pour pré-remplir le champ texte du formulaire admin.
- Migration `qcm/migrations/0031_imagedropzonelabel.py`.

## Correction (`qcm/views.py`)

- `match_zone_label(zone, user_text) -> bool` ajoutée juste après `match_qroc_answer` — même logique que pour les QROC : `normalize_qroc`, vérifie `zone.correct_label` PUIS chaque `zone.accepted_labels`, support du joker `*` via `fnmatch.fnmatch`.
- `_build_zone_results` et `_handle_ddimageortext` (`qcm/views.py`) utilisent désormais `match_zone_label` au lieu d'une comparaison stricte sur `correct_label` seul.
- `ImageDropZone` ajouté aux imports de `qcm/views.py` (n'était pas importé directement avant, seulement utilisé via les relations).

## Admin (`qcm/views_admin.py`)

- `ImageDragItemFormSet` et `ImageDropZoneFormSet` (`inlineformset_factory`), définis juste après `AnswerFormSet`. Champs exposés : `["label"]` pour les drag items, `["xleft", "ytop", "correct_label"]` pour les zones (le champ `no` est exclu et auto-assigné côté serveur).
- **Piège important** : le préfixe par défaut d'un `inlineformset_factory` n'est PAS `"form"` mais dérivé du `related_name` de la FK (`drag_items` / `drop_zones`). Il faut passer `prefix="dragform"` / `prefix="zoneform"` **explicitement et de façon identique** à l'instanciation GET (dans `_ctx()`) ET POST (dans les helpers `_save_ddi_*`), sinon le formulaire réel ne soumet jamais correctement les données — alors que des tests pytest avec payload manuel construit à la main passent quand même (angle mort classique des tests qui contournent le template). Bug réel introduit puis corrigé pendant la vérification navigateur de cette session.
- `_save_ddi_drag_items` / `_save_ddi_drop_zones` : itèrent `formset.forms` (pas `formset.save()` global, qui échouerait sur les champs `no`/`correct_drag_no` non-nullables et non exposés) ; auto-assignent `no = max(existant) + compteur local incrémenté` un par un (pas de bulk, pour éviter les collisions `unique_together`) ; suppression via `form in formset.deleted_forms` + `form.instance.delete()` (et non `formset.deleted_objects`, qui n'existe comme attribut qu'**après** un appel à `formset.save()` dans cette version de Django — `AttributeError` sinon).
- `_save_ddi_drop_zones` parse un champ hors-formset `request.POST.get(f"{form.prefix}-alts", "")`, séparateur `;` (pas `,`, car des labels composés peuvent contenir une virgule) ; remplacement complet : `obj.accepted_labels.all().delete()` puis recréation.
- `_save_ddi_background_image` : une question ddimageortext n'a qu'une seule image conceptuelle. **Supprime systématiquement TOUTES les images existantes** (`question.images.all()`, fichier + ligne DB) avant d'en créer une nouvelle avec `moodle_filename="background"` — ne pas filtrer par `moodle_filename="background"` pour trouver l'ancienne image à supprimer, car les 122 questions déjà importées de Moodle gardent leur nom de fichier d'origine (ex. `"oeil 150815.png"`), pas un nom sentinel. Bug réel trouvé en vérification navigateur sur une vraie question (#6516), corrigé.
- `AdminQuestionAddView`/`AdminQuestionEditView` : nouveau contexte `selected_qtype` (utilisé pour présélectionner le `<select qtype>`, y compris via `?qtype=ddimageortext` en query param sur la page d'ajout) ; `existing_bg_image = question.images.first()` (édition) ; branchement `if qtype == Question.DDIMAGEORTEXT:` dans les deux `.post()` pour appeler les 3 helpers `_save_ddi_*` au lieu du formset `Answer`.
- `AdminQuestionsView.get` : nouveau filtre `qtype` (`qs.filter(qtype=qtype)`), contexte `qtype_choices = Question.QTYPE_CHOICES` / `selected_qtype`.
- `AdminQuestionDeleteView.post` : lit `back_url` depuis le POST (`request.POST.get("back_url", "/admin-site/questions/")`) au lieu de toujours rediriger vers `qcm:admin_questions` — permet de préserver les filtres de la liste après suppression, et de supprimer depuis la page d'édition en réutilisant son `back_url` existant.

## Templates

- `qcm/templates/qcm/admin_site/question_form.html` :
  - `<select name="qtype">` étendu avec l'option `ddimageortext`, toutes les options pilotées par `selected_qtype` (au lieu de la logique ad-hoc précédente basée sur `question.qtype`).
  - Nouvelle card `#card-ddi` (masquée par défaut), visible/masquée via `toggleQtypeCards()` au changement du select — masque aussi `#card-answers` (formset Answer) et `#card-generic-images` (card image générique pluginfile, qui n'a pas de sens pour ddimageortext et dont la case "Supprimer" n'a aucun effet pour ce qtype — bug UX trouvé et corrigé en vérification).
  - Contenu de `#card-ddi` : upload image de fond (`new_bg_image_file`) avec preview ; canvas `#ddi-canvas` avec image `#ddi-edit-img` ; clic sur l'image → nouvelle zone + marqueur (`ddiAddZoneRow`/`ddiAddMarker`) ; marqueurs existants déplaçables au drag (`ddiMakeMarkerDraggable`, met à jour les inputs X/Y en direct) ; saisie manuelle X/Y synchronisée vers le marqueur via délégation d'événement sur `#ddi-zones-container` ; champ alternatives `name="{prefix}-alts"` hors-formset ; suppression de ligne : ligne existante (a un input `-id`) → coche la checkbox `DELETE` rendue par Django et masque la ligne (NE PAS retirer du DOM, sinon Django ne reçoit plus ses données) ; ligne neuve (JS, pas de `-id`) → retrait du DOM + réindexation (`ddiReindexZoneForms`/`ddiReindexDragForms`, ne renomme que les lignes neuves après `INITIAL_FORMS`, ne touche jamais aux lignes existantes).
  - Bouton « 🗑 Supprimer la question » (uniquement si `action == 'edit'`) + modal de confirmation dédiée (id `deleteQModal`, différent de celui de `questions.html`), POST vers `/admin-site/questions/<pk>/supprimer/` avec `back_url` = celui de la page (préservé depuis `?back=`).
- `qcm/templates/qcm/admin_site/questions.html` :
  - Bouton « + Nouvelle question légende » → `/admin-site/questions/ajouter/?qtype=ddimageortext`.
  - Select `qtype` dans les filtres (soumission auto au changement), combinable avec cours/recherche/pagination.
  - Formulaire de suppression (modal) : `<input type="hidden" name="back_url" value="{{ request.get_full_path }}">` — préserve les filtres actuels après suppression depuis la liste.

## Tests

- `tests/test_ddimageortext.py` : `TestImageDropZoneLabel`, `TestMatchZoneLabel` (label principal, insensible casse/accents, alternative seule, alternative avec joker, aucune correspondance, texte vide), test bout-en-bout `test_correct_via_accepted_alternative_label` dans `TestCheckViewDDIImageOrText`.
- `tests/test_admin_site.py` : nouvelle classe `TestAdminQuestionsDDImageOrText` (création complète avec image/zones/alternatives/drag items, auto-assignation `no`, ajout/suppression de zone, mise à jour des alternatives, remplacement d'image — y compris le cas image importée de Moodle avec nom de fichier arbitraire) ; tests filtre qtype et préservation `back_url` à la suppression dans `TestAdminQuestions`.
- Suite complète : 430 tests passent, ruff + mypy propres.

## Vérification navigateur réelle (important — a trouvé plusieurs bugs invisibles aux tests pytest à payload manuel)

Playwright + Chromium installés **à la volée**, sans dépendance permanente ajoutée au projet :
```
uv run --with playwright python -m playwright install --with-deps chromium
uv run --with playwright python script.py
```
A permis de piloter le flux complet (login staff, création avec clic-pour-placer + upload image + drag-to-reposition, édition, réponse étudiante avec une alternative) dans un vrai navigateur contre le `runserver` local, et de trouver concrètement :
1. Le préfixe de formset désynchronisé GET/POST (cf. ci-dessus).
2. La card image générique non masquée pour ddimageortext.
3. L'image de fond absente en édition pour les questions déjà importées de Moodle (filtre `moodle_filename="background"` trop strict).

Toujours nettoyer les utilisateurs/questions/sessions temporaires créés pour la vérification (la base locale contient de vraies données réelles importées de Moodle, pas une base jetable).

## Hors scope — décisions explicites de l'utilisateur

- **Issue #72** ouverte séparément : suppression du modèle `Category` (vestige Moodle, ~129 catégories type `"Default for X"`, ex. jusqu'à 22 par cours). Vérifié : **indépendant du système de tags** EC/chapitre/année qui repose sur `TagCategory` (modèle distinct), pas sur `Category` — donc le tag hierarchy n'a pas besoin d'être touché si cette issue est reprise. Touche par contre `Question.category`, `import_moodle.py`, ~23 usages dans `qcm/views.py`/`qcm/views_admin.py`, plusieurs templates, et une vingtaine de fichiers de tests (fixtures `category`).
- `normalize_qroc` (`qcm/views.py:59-62`) ne normalise pas les ligatures `œ`/`æ` (NFD ne les décompose pas, ce ne sont pas des caractères accentués composés) — `"cœur"` ne matche pas `"coeur"`. Bug réel identifié, affecte aussi bien les QROC existants que les nouvelles zones ddimageortext, mais **volontairement laissé hors scope** sur demande explicite de l'utilisateur. À corriger dans `normalize_qroc` (remplacement `œ→oe`, `æ→ae` avant/après la décomposition NFD) si redemandé séparément.

## Issues liées

- Issue #55 (cette session)
- Issue #72 — suppression du modèle Category (ouverte pendant cette session, à traiter séparément)
