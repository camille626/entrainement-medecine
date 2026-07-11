# Mode sombre / dark mode (issue #97)

## Contexte

Ajout d'un mode sombre complet basé sur l'attribut natif Bootstrap 5.3
`data-bs-theme`, avec toggle manuel dans la navbar, détection système
(`prefers-color-scheme`) pour les utilisateurs sans préférence enregistrée, et
persistance du choix explicite en base sur `UserProfile`.

## Architecture retenue

### Modèle + persistance

`UserProfile.theme` (`qcm/models.py:554`) : `CharField(max_length=5, choices=[("light",...),("dark",...)], blank=True, default="")`.
`""` signifie "pas de préférence explicite" → le client détecte `prefers-color-scheme`.
Migration `qcm/migrations/0036_userprofile_theme.py` (simple `AddField`, style identique
aux migrations précédentes de ce projet).

### Endpoint de sauvegarde

`ThemeToggleView` (`qcm/views.py`, à côté de `NotificationMarkReadView`/`NotificationMarkAllReadView`) :
même pattern HTMX que les notifications (`hx-post` + `hx-swap="none"` +
`HttpResponse(status=204)`), pas de `ProfileForm`. Route `POST /profil/theme/`
(`qcm:theme_toggle`), 400 si valeur invalide.

### `base.html` — attribut + anti-FOUC + toggle

- `<html lang="fr" data-bs-theme="{{ user.profile.theme }}">` : rendu serveur correct
  immédiatement si préférence déjà enregistrée (zéro flash). `user.profile.theme`
  échoue silencieusement si le profil n'existe pas (pattern Django
  `ObjectDoesNotExist.silent_variable_failure`, déjà utilisé ailleurs dans ce template
  pour `user.profile.photo`).
- Script inline **avant tout le `<head>`**, y compris avant le `<link>` Bootstrap : si
  l'attribut est vide, détecte `matchMedia('(prefers-color-scheme: dark)')` et le pose
  avant le premier paint. C'est le point le plus fragile à préserver si `base.html` est
  retouché : le script doit rester la toute première chose du `<head>`.
- Deux boutons toggle (🌙/☀️) dans le bloc utilisateur toujours visible de la navbar
  (celui du hamburger responsive, cf `[[260711-1104-navbar-responsive-hamburger]]`) :
  `onclick` bascule l'attribut instantanément, `hx-post` persiste en tâche de fond.
  Affichage conditionnel géré en CSS pur via `[data-bs-theme="dark"] .theme-btn-to-dark { display:none; }`
  (et inverse), aucun JS de calcul d'état nécessaire.

### Point critique découvert en implémentant : `navbar-light bg-white`

La navbar utilisait `navbar-light bg-white` (couleurs Bootstrap **fixes**, pas
theme-aware) — sans le retirer, toute la page bascule en sombre sauf la navbar qui
reste blanche. Remplacé par `bg-body` (theme-aware). **Leçon générale** : toute classe
Bootstrap de la forme `bg-white`, `bg-light`, `table-light`, `table-secondary` est une
couleur **fixe**, pas adaptative — contrairement à `bg-body`, `bg-body-secondary`,
`bg-body-tertiary` ou aux classes `*-subtle`/`*-emphasis` qui suivent `data-bs-theme`
via des variables CSS. Repéré et corrigé aux mêmes endroits : `home.html` (cartes de
cours, `bg-white` → `bg-body-tertiary`), `stats.html` et `history.html` (`thead.table-light`,
`tr.table-secondary` → `bg-body-secondary`). D'autres templates non touchés dans cette
issue ont probablement le même défaut (admin_site/*, errata_list.html, _tags_partial.html,
_chapters_partial.html) — non corrigés car non signalés par l'utilisateur, scope
volontairement limité aux pages testées.

### Couleurs custom dupliquées → variables CSS

Extraction en variables CSS + classes réutilisables dans `base.html`
(`--qcm-info-bg`, `--qcm-warning-bg`/`-border`, `--qcm-error-bg`/`-border`/`-text`,
avec override sous `[data-bs-theme="dark"]`), remplaçant les styles inline dupliqués
dans `fin.html`, `_correction.html`, `session_detail.html`, `question.html`
(classes `.qcm-alert-info`/`.qcm-alert-warning`/`.qcm-alert-error`).

### Boutons pastel uniquement en dark (itération suite retour utilisateur)

Premier jet : remplacé les 3 boutons CTA de l'accueil (`btn-outline-primary` etc.) par
des classes Bootstrap `*-subtle`/`*-emphasis` fixes → mais ces classes sont
theme-aware et donc **changeaient aussi le rendu en mode clair** (résultat non voulu :
l'utilisateur voulait zéro changement visuel en light). Correction : classes
`btn-outline-*` d'origine **conservées** dans le HTML (identique en clair), + une classe
marqueur `qcm-cta-btn` ajoutée, avec l'override pastel écrit en CSS scopé uniquement à
`[data-bs-theme="dark"] .qcm-cta-btn.btn-outline-primary { ... }` (utilisant les
variables Bootstrap `--bs-primary-bg-subtle`/`--bs-primary-text-emphasis`/
`--bs-primary-border-subtle`, theme-aware nativement). **Leçon** : pour un changement
"dark uniquement, zéro impact en light", préférer une classe marqueur + CSS scopé
`[data-bs-theme="dark"]` plutôt que remplacer les classes Bootstrap sémantiques
(`*-subtle` etc.) qui s'appliquent dans les deux thèmes.

## Incident mineur pendant le débogage

En diagnostiquant pourquoi un test ne passait pas au RED (le tableau "Par cours" ne se
rendait pas sans données réelles, à cause de `{% if total_checks == 0 %}` dans
`stats.html`), une commande `manage.py shell -c` a été lancée par erreur contre la
**vraie base de dev** (au lieu de la base de test pytest), créant une `StudyYear`
"P2dbg", un `Course` "Cours debug" et un `User` "dbgtest". Repéré par l'utilisateur au
test manuel suivant et nettoyé immédiatement. **Leçon** : toujours utiliser un script
pytest jetable (ou `pytest --no-header -s` sur un test temporaire) pour ce type
d'investigation, jamais `manage.py shell -c` en écriture — même pour du debug rapide,
le risque de polluer la base de dev réelle est trop élevé.

## Tests

`tests/test_theme.py` (nouveau, 16 tests) : champ modèle, endpoint (persistance,
validation, auth, création de profil à la volée), rendu `data-bs-theme` sur `/`,
présence et ciblage des boutons toggle, absence de `bg-white`/`table-light`/
`table-secondary` sur accueil/stats/historique, présence des classes outline +
marqueur `qcm-cta-btn` sur les boutons CTA de l'accueil.

## État au moment de l'écriture

Travail non commité sur la branche `97-feattheme-implémenter-un-mode-sombre-dark-mode`.
520 tests passent, ruff lint/format et pre-commit OK. Utilisateur a validé
visuellement (mobile + desktop, clair + sombre) après 3 itérations de retouches CSS.
