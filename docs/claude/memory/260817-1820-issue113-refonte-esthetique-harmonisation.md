# Issue #113 — Revue esthétique globale et harmonisation UI

## Contexte

Passe de polish/harmonisation demandée sur l'ensemble du site (pas une refonte). Travail réalisé sur la branche `113-revue-esthétique-globale-du-site-harmonisation-uiux`, en aller-retour itératif avec l'utilisateur (chaque ajustement validé visuellement via des captures Playwright avant de passer au suivant). Aucun commit n'a encore été créé à ce stade — tout est dans l'arbre de travail, prêt à committer/PR.

## Système d'icônes : sprite SVG inline, pas de police d'icônes CDN

Tous les emojis du site (~150 occurrences sur 34 templates) ont été remplacés par des icônes vectorielles. Deux approches ont été essayées :

1. **Rejetée** : police Bootstrap Icons via CDN (`<link>` vers `bootstrap-icons.min.css`). Fonctionnait mais ajoutait ~216 Ko (CSS + `.woff2`) en render-blocking à *chaque* navigation complète de page, pour seulement 33 icônes réellement utilisées sur les 2000+ du set. Cause probable de la lenteur perçue par l'utilisateur.
2. **Retenue** : sprite SVG inline (`qcm/templates/qcm/_icon_sprite.html`), un seul `<svg style="display:none"><symbol id="bi-xxx">…</symbol>…</svg>` contenant uniquement les icônes utilisées, inclus une fois via `{% include %}` juste après `<body>` dans `qcm/templates/qcm/base.html`. Utilisation : `<svg class="bi"><use href="#bi-xxx"></use></svg>`. Poids total ~14 Ko, zéro requête réseau.

Les 7 pages standalone qui n'étendent pas `base.html` (`registration/login.html`, `inscription.html`, `inscription_done.html`, `password_reset_*.html`) ont leur propre mini-sprite (4 icônes seulement : heart-pulse, check-circle-fill, envelope-fill, lock-fill) inliné directement dans chaque fichier, car elles ne peuvent pas hériter du sprite de `base.html`.

**Piège** : Bootstrap Icons n'a **aucune icône "anchor"** dans son catalogue (vérifié sur toutes les versions récentes). L'icône `bi-anchor` du sprite est un dessin SVG maison (anneau + tige + crochets en `stroke`, pas `fill`).

**Piège emoji** : le premier balayage regex (`\x{1F300}-\x{1FAFF}` + `\x{2600}-\x{27BF}`) a raté des caractères hors de ces plages : `▶` (U+25B6, bloc *Geometric Shapes*) et `⏸` (U+23F8) utilisés en texte brut dans `qcm/templates/qcm/history.html` (bouton Reprendre) et `qcm/templates/qcm/admin_site/users.html` (bouton activer/désactiver un utilisateur). Un futur audit devrait chercher plus large (tout non-ASCII hors lettres accentuées françaises).

## Performance : vendoring local de tout le JS/CSS externe

La vraie cause de la lenteur ressentie n'était pas (seulement) les icônes : `bootstrap.min.css` (232 Ko), `bootstrap.bundle.min.js` (80 Ko), `htmx.org` (48 Ko) et `chart.js` (205 Ko) étaient chargés depuis des CDN externes (jsdelivr/unpkg) à *chaque* navigation, le site n'étant pas une SPA. Vérifié empiriquement : le rendu serveur Django lui-même prend 10-90 ms par page (mesuré avec `django.test.Client` + `CaptureQueriesContext`), donc le ressenti de lenteur venait bien du réseau/CDN, pas du backend.

Solution : tout rapatrié en local sous `qcm/static/qcm/vendor/{bootstrap,htmx,chartjs}/`, et chaque `<link href="https://cdn...">` / `<script src="https://cdn...">` remplacé par `{% static 'qcm/vendor/.../....' %}`. Zéro requête externe désormais (vérifié via l'event `request` de Playwright sur les pages clés).

**Piège Django** : `{% load static %}` doit être présent dans **chaque fichier de template** qui utilise `{% static %}`, même s'il `{% extends %}` un parent qui le charge déjà — les tags chargés ne sont **pas hérités** à travers `{% extends %}`. A fait échouer `qcm/templates/qcm/stats.html` et `stats_course.html` au premier essai (`{% static %}` utilisé pour le nouveau `<script src>` de Chart.js sans `{% load static %}` local).

## Couleur violette maison

Bootstrap 5.3 n'a **pas** de classes utilitaires violettes générées (`.text-purple`/`.bg-purple`/`.btn-outline-purple` n'existent pas dans le CSS compilé, alors que `$purple` est bien une variable Sass du framework). Ajout dans `qcm/templates/qcm/base.html` :
- `--qcm-purple` (variable CSS, valeur différente en clair `#9c4f6e` bordeaux/lie-de-vin et en sombre `#d99cb3`, plus clair pour le contraste)
- `.text-qcm-purple`, `.border-qcm-purple`, `.bg-qcm-purple`, `.btn-outline-qcm-purple` (+ variante `.qcm-cta-btn.btn-outline-qcm-purple` en sombre, pastel, même mécanisme que les boutons `btn-outline-primary`/`-warning`/`-secondary` déjà en place)

Teinte ajustée deux fois sur retour utilisateur : d'abord un violet vif façon Bootstrap (`#6f42c1`), jugé trop intense → viré vers un bordeaux/lie-de-vin plus doux et plus rouge (`#9c4f6e`).

**Bug rencontré et corrigé** : `.bg-qcm-purple` fixe `background-color` avec `!important` (couleur pleine, texte blanc, pour les badges pleins). Combiné à l'utilitaire natif `.bg-opacity-10` de Bootstrap (censé donner un fond pâle), le `!important` gagne et **annule complètement l'effet d'opacité** — rendu en violet plein alors qu'on voulait un fond pâle. Corrigé en ajoutant une classe dédiée `.bg-qcm-purple-subtle` (fond pâle fixe, sans mécanisme d'opacité, texte hérité par défaut — pas de blanc forcé), sur le modèle des classes `*-subtle` natives de Bootstrap. **Leçon** : toute future couleur custom nécessitant une variante pâle devrait suivre le pattern natif de Bootstrap (`background-color: rgba(var(--x-rgb), var(--bs-bg-opacity))`) dès le départ plutôt qu'un `!important` solide.

## Convention de couleur harmonisée (remplace vert/jaune/rouge)

Sur tout le site, pour les états correct/partiel/incorrect (navigateur de questions, correction en direct, page de résultats et relecture d'historique, page statistiques) :
- **correct** = bleu (`text-primary`/`bg-primary`/`border-primary`, déjà la couleur d'accent du site)
- **partiel** = gris (`text-secondary`/`bg-secondary`/`border-secondary`)
- **incorrect** = bordeaux (`text-qcm-purple`/`bg-qcm-purple`/`bg-qcm-purple-subtle`/`border-qcm-purple`)

Fichiers concernés : `qcm/templates/qcm/question.html` (`.nav-q-*` CSS + `#status-label`), `qcm/templates/qcm/_correction.html`, `qcm/templates/qcm/fin.html`, `qcm/templates/qcm/session_detail.html`, `qcm/templates/qcm/history.html` (colonne Note), `qcm/templates/qcm/stats.html`, `qcm/templates/qcm/stats_course.html` (y compris les couleurs JS des graphiques Chart.js, variables renommées `BLUE`/`PURPLE` pour rester lisibles).

**Exception volontaire** : le bloc "Correction" (feedback Moodle affiché après une réponse, classe `qcm-alert-warning`, fond ambre) n'a **pas** été recoloré — ce n'est pas un indicateur de statut correct/partiel/incorrect, c'est un encart d'explication à part, partagé avec d'autres contextes (erratas...).

Sur la page d'accueil (`qcm/templates/qcm/home.html`), la tuile "Ma progression" (bordure/icône/bouton) est passée du jaune au même bordeaux, et les icônes des 3 tuiles d'action prennent maintenant la couleur de leur bordure (bleu/bordeaux/gris) alors que l'icône des cours dans "Mes cours" reste neutre (`text-body`, ni bleu ni bordeaux).

## Autres correctifs notables de cette passe

- **Bug navbar** : `navbar-expand-lg` provoquait un débordement horizontal de toute la page entre ~992px et ~1200px de large (liens + zone utilisateur ne tenaient pas sur une ligne juste avant le point de bascule vers le hamburger). Corrigé en passant à `navbar-expand-xl` dans `base.html:170`. `tests/test_navbar.py` a dû être mis à jour (assertion sur le nom littéral de la classe).
- **Bug HTMX** : dans `question.html`, les boutons de navigation précédente/suivante affichés `{% if not is_answered %}` vivaient **en dehors** de `#answers-zone` (la zone remplacée par le swap HTMX au moment de la correction). Résultat : après avoir répondu, ces boutons pré-réponse restaient affichés en même temps que ceux de `_correction.html` (doublon visible de CTA "suivante"). Corrigé en déplaçant ce bloc à l'intérieur de `#answers-zone`.
- Ajout de marge horizontale (`padding-left/right: 1rem`) sur `.main-content` dans `base.html`, pour éviter que les boutons ne semblent "collés" au bord de l'écran sur les pages denses (ex : formulaire de modification de question).
- Favicon (`qcm/static/qcm/img/favicon.svg`) remis à jour pour matcher le nouveau logo (icône `heart-pulse`, plus l'ancien emoji 🩺 en `<text>` SVG).
- Avatar par défaut harmonisé : même cercle coloré avec initiale dans la navbar et sur la page profil (au lieu de l'icône SVG générique `person-circle` d'un côté, cercle+initiale de l'autre).

## Méthodologie de revue visuelle

Playwright installé dans un venv jetable du scratchpad (`uv venv .venv-review` puis `uv pip install --python .venv-review/bin/python "playwright==1.40.0"`) — **important** : épingler `1.40.0`, les versions plus récentes de Playwright refusent d'installer Chromium sur Debian 11 (l'OS de base de ce devcontainer). Un utilisateur staff temporaire (`_design_review_tmp`) est créé/supprimé à chaque passe de captures d'écran — toujours penser à le supprimer en fin de session.
