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

### Tests

- `tests/test_tag_merging.py` (nouveau, 13 tests) : tests directs des fonctions
  du service (migration M2M, non-impact autres cours, reparenting, `dry_run`,
  `TagMergeError` sur tags identiques/parent non-EC/catégorie chapitre absente,
  idempotence).
- `tests/test_admin_site.py::TestAdminTagMerge` (nouveau, 5 tests) : accès
  staff-only (redirect), succès merge (M2M + message affiché), succès
  convert-to-chapter, erreur métier → `alert-danger` sans 500, PK inconnu → 404.
- Suite complète : 610 tests passent (592 pré-existants + 13 + 5).

### Vérification manuelle (serveur de dev réel, pas seulement le client de test Django)

`chromium-cli`/Playwright/node absents du conteneur → tests via `curl` contre le
vrai serveur `runserver` avec un utilisateur staff jetable et des données de test
dédiées (cours "QA TEST fusion tags", tags `qa-test-tag-a/b/c`), nettoyées après
coup. Confirmé en conditions réelles : fusion réussie + message succès (et
idempotence sur un second run : "0 question(s) migrée(s)"), conversion EC→chapitre
réussie (`category`/`parent_ec`/`course` corrects en DB), erreur "tags identiques"
→ `alert-danger` affiché, statut 200 (pas de 500).

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
