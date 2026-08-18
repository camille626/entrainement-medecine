# Fusion/conversion de tags depuis l'admin web (Issue #115)

## Contexte

Suite à [[260817-1209-fusion-tags-merge-tags-command]] (issue #108, commande CLI
`manage.py merge_tags`), l'utilisateur a demandé de rendre les actions `merge` et
`convert-to-chapter` accessibles depuis `/admin-site/tags/` sans passer par un
accès shell au conteneur NAS. L'action `remove` reste CLI-only (hors scope, pas
demandée pour l'UI).

## Ce qui a été fait

### Service `qcm/tag_merging.py` (nouveau)

Extraction de la logique métier de `qcm/management/commands/merge_tags.py`
(`Command._merge`/`_convert_to_chapter`) vers un module de service réutilisable,
sur le modèle de `qcm/trophies.py`. Fonctions `merge_course_tags(course, from_tag,
to_tag, dry_run=False) -> MergeResult` et `convert_tag_to_chapter(course, tag,
parent_ec, dry_run=False) -> ConvertToChapterResult`, exception `TagMergeError`.

**Décision de conception** : le service opère sur des instances `Course`/`Tag`
déjà résolues, pas des noms. La résolution par nom/fragment (`_resolve_course`/
`_resolve_tag` dans `merge_tags.py`) reste **CLI-only** — la vue web résout les
objets par PK depuis des `<select>`, pas besoin de matching flou côté service.

`qcm/management/commands/merge_tags.py` a été refactoré pour appeler ce service
(`_merge`/`_convert_to_chapter` sont maintenant de fins wrappers qui formattent
la sortie CLI à partir du résultat retourné) ; `TagMergeError` est convertie en
`CommandError`. Comportement CLI inchangé — `tests/test_merge_tags_command.py`
reste vert sans aucune modification après le refactor (42/42 passent).

### Vue `AdminTagMergeView` (`qcm/views_admin.py`)

POST-only, `StaffRequiredMixin`. Un champ caché `action` (`merge` ou
`convert-to-chapter`) distingue les deux formulaires. Résolution par PK via
`get_object_or_404` (PK invalide = 404, pas une erreur métier). `TagMergeError`
→ `messages.error`, succès → `messages.success` avec le même résumé que les
messages CLI. Toujours `redirect("qcm:admin_tags")`.

Route : `admin-site/tags/fusionner/` → `admin_tag_merge` (`qcm/urls.py`).

### Template `qcm/templates/qcm/admin_site/tags.html`

Nouvelle carte "Fusionner / convertir des tags" (deux sous-formulaires), sous la
carte existante "Ajouter / modifier un tag". Réutilise les données de contexte
déjà présentes dans `AdminTagsView.get()` (`courses`, `ec_tags`) — aucun nouveau
contexte nécessaire côté vue GET. Confirmation JS (`onclick="return confirm(...)"`)
avant soumission, sur le modèle du bouton de suppression de tag existant.

### Affichage générique des messages Django (prérequis découvert en explorant)

Avant cette issue, **seul le tag `trophy` était rendu** dans
`qcm/templates/qcm/base.html` (toast trophée) — aucun bloc générique pour
`messages.success`/`messages.error`, alors que le framework `django.contrib.messages`
est installé depuis le début. Ajouts :

- `config/settings.py` : `MESSAGE_TAGS = {messages_constants.ERROR: "danger"}`
  (le tag par défaut "error" ne correspond à aucune classe Bootstrap valide,
  contrairement à "danger").
- `qcm/templates/qcm/base.html` : bloc `alert alert-{{ message.tags }}
  alert-dismissible` dans `.container.main-content`, pour tous les messages
  **hors tag `trophy`** (toast trophée inchangé). Réutilisable par toute future
  vue admin qui voudrait utiliser `django.contrib.messages`.

### Compléments demandés après la première itération : undo, aperçu, filtrage par cours

Trois demandes utilisateur après un premier test de l'UI : (1) pouvoir annuler
une fusion déjà exécutée, (2) prévisualiser les questions concernées et leurs
nouveaux tags avant de confirmer, (3) filtrer les `<select>` de tags pour ne
montrer que les tags utilisés dans le cours choisi.

**Historique + undo** : nouveau modèle `TagMergeLog` (`qcm/models.py`, migration
`0038_tagmergelog.py`) — `action`, `course`, `summary`, `snapshot` (JSONField),
`performed_by`, `created_at`, `undone_at`. `merge_course_tags`/
`convert_tag_to_chapter` (`qcm/tag_merging.py`) créent ce log dans la même
`transaction.atomic()` que la mutation (sauf en `dry_run`), avec tout le
nécessaire pour annuler dans `snapshot` : `question_ids` migrées, et surtout
`already_had_to_tag_ids`/`already_had_parent_ec_ids` — l'ensemble des questions
qui possédaient **déjà** le tag cible/parent avant l'opération, calculé **avant**
mutation. C'est l'edge case critique de l'undo : une question qui avait déjà les
deux tags avant la fusion ne doit **pas** perdre le tag cible à l'annulation
(vérifié en conditions réelles, cf. plus bas). Nouvelle fonction
`undo_tag_merge_log(log)` : lève `TagMergeError` si déjà annulé ou si un tag/une
question référencé(e) n'existe plus (`DoesNotExist` capturé). Vue
`AdminTagMergeUndoView` (POST, pk) + route `admin-site/tags/fusions/<pk>/annuler/`.
Carte "Historique des fusions" dans `tags.html` (20 dernières entrées globales,
badge "Annulée" ou bouton "Annuler").

**Aperçu avant confirmation** : d'abord un aperçu texte minimal (liste tronquée),
jugé insuffisant par l'utilisateur — refait sur le modèle exact de
`qcm/templates/qcm/errata_list.html` (énoncé via `question.render_text|safe`
qui résout les images `@@PLUGINFILE@@`, propositions en lecture seule avec
icône check/x/cercle selon `answer.is_correct`/`fraction`, voir
`errata_list.html:280-299` pour le pattern source). Nouveau partial
`_tag_merge_preview_question.html` (une carte par question, tags "actuels"/
"après" en badges) inclus par `_tag_merge_preview.html` depuis
`AdminTagMergePreviewView` (POST, dry-run + échantillon de questions
`prefetch_related("tags", "answers", "images")`). Questions `ddimageortext` :
pas d'adaptation du pattern zones interactives (`_ddi_zones_readonly.html`,
qui attend un objet errata `e.pk`/`e.question`, pas directement réutilisable
ici) — juste l'énoncé + une note, scope volontairement limité.

Itérations UX après premiers retours utilisateur :
- **Placement** : la zone d'aperçu était en bas de page après le tableau des
  tags (potentiellement long) → invisible sans scroller alors que la requête
  HTMX aboutissait bien (confirmé par les logs serveur, 200 avec contenu réel).
  Déplacée en haut de page + `htmx:afterSwap` déclenchant un `scrollIntoView`.
- **Pagination** : capé à 10 questions (`PREVIEW_LIMIT`) avec un bouton
  "Voir les N question(s) restante(s)" (`show_all=1` en POST, re-rendu complet
  de la même zone via HTMX, plafond de sécurité `SHOW_ALL_LIMIT=500`) plutôt
  qu'un simple texte "... et N autres" non actionnable.
- **Annulation de l'aperçu** (avant confirmation, distinct de l'undo post-hoc) :
  bouton "Annuler" à côté de "Confirmer la fusion", vide simplement la zone en
  JS (`onclick="document.getElementById(...).innerHTML=''"`), pattern déjà
  utilisé dans `_errata_form.html`.

**Filtrage des tags par cours** : `AdminTagsView.get()` calcule un mapping
`course_ec_tags` (tags EC réellement utilisés par au moins une question de
chaque cours, via `Tag.objects.filter(category__tag_type=SOUSCATEGORIE,
questions__course_id=...).distinct()`), sérialisé en JSON dans un
`<script type="application/json">`. JS vanilla dans `tags.html`
(`filterTagOptions`), sur le modèle de `updateTagFields()` déjà présent dans ce
template — **décision volontaire de ne pas utiliser HTMX + `hx-swap-oob`** (non
utilisé ailleurs dans le projet) pour ce besoin : volume de données petit
(~30 tags/13 cours), tout se fait côté client sans aller-retour serveur.

### Tests

- `tests/test_tag_merging.py` (25 tests) : service de base + création de log
  (présent seulement si `dry_run=False`) + undo (merge, reparenting, edge case
  "avait déjà le tag", convert-to-chapter, double-undo, tag supprimé entretemps).
- `tests/test_admin_site.py::TestAdminTagMerge` (15 tests) : accès staff-only,
  succès merge/convert (+ `performed_by`), erreur sans 500, 404 sur PK inconnu,
  historique affiché, aperçu sans mutation DB (merge et convert-to-chapter),
  undo via la vue + double-undo, pagination `show_all`, scoping JSON par cours.
- Suite complète : 632 tests passent.

### Vérification manuelle (serveur de dev réel, pas seulement le client de test Django)

`chromium-cli`/Playwright/node absents du conteneur → tests via `curl` contre le
vrai serveur `runserver` avec un utilisateur staff jetable et des données de test
dédiées, nettoyées après coup. Confirmé en conditions réelles à deux reprises
(fonctionnalité initiale, puis compléments) : fusion réussie + message succès
(idempotence sur un second run), conversion EC→chapitre réussie, erreur "tags
identiques" → `alert-danger`, **undo avec l'edge case critique validé en base**
(question ayant déjà les deux tags avant fusion → garde les deux après
annulation, l'autre question perd bien le tag cible), badge "Annulée" affiché
après usage. Puis, après retour utilisateur sur l'UX de l'aperçu, re-vérifié
avec le nouveau design (énoncé/propositions/tags avant-après) directement par
l'utilisateur dans son navigateur.

**Point d'attention pour de futurs tests manuels via `curl`** : le token CSRF
Django est un double-submit masqué qui change à **chaque** rendu de page — il faut
récupérer le `csrfmiddlewaretoken` depuis le **corps HTML d'un GET fraîchement
récupéré juste avant le POST** (pas depuis la cookie `csrftoken` brute, ni depuis
une page HTML mise en cache d'un appel précédent), sinon Django répond 403 "CSRF
token missing" même avec un cookie de session valide.

## Décisions techniques

- Logique métier dans un service Django-agnostique des noms (objets, pas
  strings) → réutilisable par CLI (résolution par nom) et UI (résolution par PK)
  sans dupliquer les règles de validation.
- Ajout du bloc de messages génériques dans `base.html` justifié par le besoin
  explicite de l'issue ("erreurs remontées via `messages.error`"), pas un ajout
  hors scope — c'est un prérequis direct.
- `remove` volontairement non exposé en UI (scope explicitement limité par
  l'utilisateur à `merge` + `convert-to-chapter`).
- `TagMergeLog.snapshot` en JSONField plutôt que des FK dédiées par cas d'usage :
  un seul modèle sert aux deux actions (`merge`/`convert_to_chapter`), le contenu
  du JSON diffère selon `action`. Compromis assumé entre simplicité de schéma et
  validation faible (pas de contrainte DB sur la forme du JSON).
- Toujours vérifier l'UI réellement rendue après un changement (le placement de
  la zone d'aperçu "fonctionnait" côté serveur — logs 200 avec contenu — mais
  était invisible pour l'utilisateur ; les tests automatisés ne l'auraient pas
  détecté puisqu'ils vérifient le contenu de la réponse, pas sa position visuelle
  sur la page rendue).
