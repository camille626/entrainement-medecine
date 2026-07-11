# Navbar responsive avec menu hamburger (issue #78)

## Contexte

La navbar de `qcm/templates/qcm/base.html` utilisait `navbar-expand` sans breakpoint,
ce que Bootstrap 5 interprète comme "toujours étendue" : sur mobile tous les liens
s'affichaient en colonne pleine largeur, sans hamburger fonctionnel ni cassé (aucun
`.navbar-toggler`/`.navbar-collapse` n'existait dans le template).

## Solution retenue

Modification de `qcm/templates/qcm/base.html` (navbar unique de l'app, ligne ~64) :

1. `navbar-expand` → `navbar-expand-lg` (repli sous 992px).
2. Bouton `.navbar-toggler` standard Bootstrap 5 ajouté, avec
   `data-bs-toggle="collapse"` + `data-bs-target="#mainNavCollapse"`.
3. La liste de liens `<ul id="mainNav">` est enveloppée dans
   `<div class="collapse navbar-collapse" id="mainNavCollapse">`.
4. Classe `navbar-nav` ajoutée sur le `<ul id="mainNav">` (en plus de `nav nav-tabs`) :
   c'est cette classe native Bootstrap qui fait passer les liens en
   `flex-direction: column` sous le breakpoint (empilés verticalement) et en
   `flex-direction: row` au-dessus — la simple présence de `.collapse.navbar-collapse`
   ne suffit pas, `nav-tabs` seul reste toujours en ligne.
5. `align-items-center` ajouté sur le même `<ul>` pour centrer chaque lien
   horizontalement une fois empilé en colonne sur mobile (sans casser l'alignement
   vertical en mode ligne sur desktop, où `align-items` contrôle l'axe croisé).

### Bloc notifications/profil : itération suite à retour utilisateur

Le premier jet avait placé le bloc "cloche de notifications + dropdown utilisateur"
à l'intérieur du `.collapse.navbar-collapse`, comme suggéré par le checklist initial
de l'issue. L'utilisateur a demandé une correction lors du test manuel : ces éléments
ne sont pas des liens de navigation et doivent rester **toujours visibles**, juste à
gauche du hamburger, indépendamment de l'état replié/déplié du menu.

Solution : sortir ce bloc du conteneur `.collapse` et le repositionner dans le DOM
entre le `.navbar-brand` et le `.navbar-toggler` (ordre source = ordre visuel sur
mobile, où toutes les classes `order-*` sont neutres par défaut). Pour préserver
l'ordre desktop d'origine (liens de nav avant le bloc utilisateur, à droite), deux
classes d'ordre flexbox responsive sont utilisées :
- `.collapse.navbar-collapse` (liens) : `order-lg-2`
- bloc utilisateur : `order-lg-3`

`ms-auto` sur le bloc utilisateur pousse le groupe [bloc utilisateur + toggler] vers
la droite sur mobile (absorbe l'espace libre malgré le `justify-content: space-between`
natif de `.navbar`). Suite à un second retour, `me-3 me-lg-0` a été ajouté pour créer
un espacement visuel entre ce bloc et le bouton toggler sur mobile (sans affecter le
rendu desktop où `flex-grow-1` sur le `<ul>` gère déjà l'espacement).

## Apprentissage clé

Pour du responsive Bootstrap 5 navbar avec des éléments "toujours visibles" hors du
menu repliable (avatar, notifications, etc.), le pattern est : sortir l'élément du
`.navbar-collapse`, le positionner dans le DOM à l'endroit voulu pour le mobile
(ordre source = ordre visuel par défaut), puis utiliser les classes `order-lg-*`
(ou `order-md-*` selon le breakpoint choisi) pour ré-agencer visuellement au-dessus
du breakpoint sans dupliquer le HTML. `ms-auto`/`me-*` combinés à `order-*` donnent un
contrôle fin de l'espacement sans CSS custom.

## Tests

`tests/test_navbar.py::TestNavbarResponsive` (nouvelle classe, 7 tests) vérifie
structurellement (regex sur le HTML rendu, sans navigateur headless disponible dans
ce container) :
- présence de `navbar-expand-lg` et absence de `navbar-expand` nu
- présence du bouton `.navbar-toggler` avec `data-bs-toggle="collapse"`
- correspondance `data-bs-target` ↔ `id` du conteneur `.collapse.navbar-collapse`
- présence de `navbar-nav` et `align-items-center` sur `<ul id="mainNav">`
- ordre DOM : bloc notifications (`notif-bell-zone`) avant le toggler, lui-même avant
  le conteneur collapse
- présence d'une marge `me-*` sur le bloc utilisateur

## État au moment de l'écriture

Travail encore non commité sur la branche
`78-responsive-mobile-remplacer-la-navbar-par-un-menu-hamburger` (2 fichiers modifiés :
`qcm/templates/qcm/base.html`, `tests/test_navbar.py`). Suite complète de tests (503+18
au total après ajout), ruff lint/format et pre-commit passent tous.
