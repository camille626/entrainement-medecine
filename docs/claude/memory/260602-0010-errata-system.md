# Système Errata — Issue #19

## Résumé

Système complet de signalement d'erreurs sur les questions, avec interface admin de traitement et notifications in-app.

---

## Modèles ajoutés (`qcm/models.py`)

### `Notification`
- `user` (FK User), `message` (TextField), `link` (CharField), `read` (BooleanField), `created_at`
- Utilisée pour les notifications in-app (cloche dans la navbar)

### `Errata`
Types : `points` · `correction` · `image` · `tag` · `autre`
Statuts : `pending` · `accepted` · `rejected`
Champs clés :
- `question` (FK), `reported_by` (FK User)
- `error_type`, `description`
- `concerned_answers` (M2M Answer) — pour type `correction`
- `suggested_tags` (M2M Tag) — pour type `tag`
- `admin_note`, `status`, `resolved_at`, `resolved_by`

---

## Vues ajoutées (`qcm/views.py`)

| Vue | URL | Rôle |
|-----|-----|------|
| `ErrataSubmitView` | `GET/POST /errata/question/<id>/` | Formulaire HTMX de signalement |
| `ErrataListView` | `GET /errata/` | Liste admin filtrable (cours, statut) |
| `ErrataAcceptView` | `POST /errata/<pk>/accept/` | Accepter + appliquer selon le type |
| `ErrataRejectView` | `POST /errata/<pk>/reject/` | Refuser avec note optionnelle |
| `ErrataFeedbackView` | `POST /errata/<pk>/feedback/` | Sauvegarder le feedback Quill |
| `NotificationMarkReadView` | `POST /notifications/<pk>/mark-read/` | Marquer notif lue (HTMX, 204) |

### Logique de `ErrataAcceptView` par type
- **`tag`** + `suggested_tags` : applique les tags suggérés via `question.tags.set()`
- **`correction`** : bascule `is_correct` + recalcule `fraction = 1/n_correct` (correctes) ou `-1.0` (fausses) via `Answer.objects.bulk_update()`; sauvegarde aussi `question.feedback`
- **`points`** : fractions manuelles saisies par l'admin, clampées [-1, 1], `is_correct = fraction > 0`, `bulk_update`; sauvegarde `question.feedback`
- **`image` / `autre` / `tag` sans suggestion** : simple accept + notif
- Tous les types : crée une `Notification` avec message `✅ Votre signalement «...» a été accepté — merci pour votre contribution !`

**Important** : `Answer.fraction` a `MinValueValidator(0.0)` dans le modèle mais les données Moodle contiennent des valeurs négatives (-1.0). Le validateur n'est pas appliqué par `.save()` ni `bulk_update()` → on peut écrire -1.0 en base sans problème.

---

## Templates

### `_errata_form.html` (partial HTMX)
- Déclenché par bouton "⚠&#xFE0E; Signaler une erreur" dans `_correction.html`
- `hx-get="/errata/question/<pk>/"` → `hx-target="#errata-form-<pk>"`
- Description optionnelle pour `points` / `tag` / `image`, obligatoire pour `correction` / `autre`
- Zone "Réponses concernées" (type=correction) et "Tags suggérés" (type=tag) avec Bootstrap popovers
- Cancel : vide `#errata-form-<pk>` uniquement (le bouton déclencheur reste intact)
- JS `toggleErrataFields()` affiche/masque les zones et ajuste l'indicateur `*` requis

### `errata_list.html` — 3 branches selon le type (staff, pending uniquement)

**Branche 1 — `correction`** : toggle ✓/✗ par proposition, JS recalcule les fractions en temps réel, form POST vers `/accept/`

**Branche 2 — `points`** : `<input type="number" step="0.01" min="-1" max="1">` par proposition, affiche `actuel : +0.33 →` pour garder la valeur d'origine visible

**Branche 3 — standard** (`tag` / `image` / `autre`) :
- `tag` avec suggestions → "Accepter la suggestion"
- Tous les autres → "Accepter le signalement"
- `image` : info-box avec lien issue #29 (image upload non encore implémenté)

**Section "Correction générale" (Quill)** — visible pour le staff sur **tous** les types :
- Éditeur Quill 1.3.7 (CDN), initialisé **paresseusement** à l'ouverture de l'accordéon Bootstrap (`show.bs.collapse`)
- Contenu initial stocké dans `<template id="feedback-tpl-<pk>">{{ e.question.feedback|safe }}</template>` — le `|safe` est **obligatoire** sinon le HTML est échappé et Quill affiche du texte brut
- Hidden inputs `.quill-sync-input[data-errata-id]` syncés au `submit` de leur form respectif
- Form séparé `#feedback-form-<pk>` → `POST /errata/<pk>/feedback/`
- Pour types `correction` et `points` : le form de correction a aussi un `quill-sync-input` → "Appliquer" sauvegarde answers + feedback en une fois

### `_errata_tags_and_meta.html`
Sous-template factorisé : tags actuels + type d'errata + description signalée. Inclus dans les branches 1 et 2.

---

## Accordéon Bootstrap (errata_list)
- Chaque errata = un `accordion-item` avec `accordion-button collapsed` (tout fermé par défaut)
- Header visible : titre tronqué 10 mots + cours/reporter/date + badge statut coloré (warning/success/danger)
- Couleur de bordure de la card : warning (pending) / success (accepted) / danger (rejected)

---

## Notifications in-app
- Context processor `qcm.context_processors.notifications` injecte `unread_notifications` et `unread_notif_count` dans tous les templates
- Ajouté dans `config/settings.py` → `TEMPLATES[0]['OPTIONS']['context_processors']`
- Cloche 🔔 dans `base.html` avec badge rouge, dropdown Bootstrap listant les 10 dernières non-lues
- HTMX `hx-post="/notifications/<pk>/mark-read/"` au clic (204, swap=none)

---

## Tests (`tests/test_errata.py`)
11 tests : création modèle, soumission, vue liste, accept (crée Notification), reject.

---

## Points d'attention futurs
- Image upload (issue #29) : commenter dans l'issue pour lier à l'errata type `image`
- Comptabilisation des contributions utilisateur : à implémenter (champ `contribution_count` ou table dédiée)
- `Answer.fraction` MinValueValidator(0.0) est incorrect (données Moodle ont -1.0) → à corriger dans le modèle
