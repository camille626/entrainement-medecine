---
date: 2026-06-03
issue: "#15"
branch: 15-onglet-admin-gestion-questionscours-et-utilisateurs-dans-le-site
status: implémenté, testé, validé utilisateur — PR à créer
---

# Interface admin web (/admin-site/) — issue #15

## Vue d'ensemble

Nouvelle section staff-only accessible depuis la navbar (lien "Admin" → `/admin-site/`). Remplace le lien direct vers le Django Admin pour les opérations courantes.

---

## Architecture

**Nouveau fichier** : `qcm/views_admin.py` — toutes les vues admin web (séparé de `views.py` qui dépassait 2000 lignes)

**Mixin** : `StaffRequiredMixin(LoginRequiredMixin)` — redirige les non-staff vers home au lieu de 403/404

**Fonction partagée** : `accept_registration(req, accepted_by)` — extraite de `admin.py` pour éviter la duplication ; crée le compte, inscrit aux cours, envoie l'email. `admin.py` appelle désormais cette fonction.

**Nouveau template base** : `qcm/templates/qcm/admin_site/base.html` — sidebar avec navigation interne (Tableau de bord, Demandes, Utilisateurs, Cours, Tags)

---

## URLs ajoutées (`qcm/urls.py`)

```
/admin-site/                               → AdminDashboardView
/admin-site/demandes/                      → AdminRegistrationsView
/admin-site/demandes/<pk>/accepter/        → AdminAcceptRegistrationView
/admin-site/demandes/<pk>/refuser/         → AdminRejectRegistrationView
/admin-site/utilisateurs/                  → AdminUsersView
/admin-site/utilisateurs/<pk>/toggle/      → AdminToggleUserView
/admin-site/utilisateurs/<pk>/supprimer/   → AdminDeleteUserView
/admin-site/utilisateurs/<pk>/changer-annee/ → AdminChangeUserYearView
/admin-site/questions/                     → AdminQuestionsView (étend base.html, PAS admin_site/base.html)
/admin-site/questions/ajouter/             → AdminQuestionAddView
/admin-site/questions/<pk>/modifier/       → AdminQuestionEditView
/admin-site/questions/<pk>/supprimer/      → AdminQuestionDeleteView
/admin-site/cours/                         → AdminCoursesView (GET liste + POST ajout)
/admin-site/cours/<pk>/                    → AdminCourseEditView (POST change semestre)
/admin-site/tags/                          → AdminTagsView (GET liste + POST ajout)
/admin-site/tags/<pk>/supprimer/           → AdminTagDeleteView
```

---

## Fonctionnalités par section

### Tableau de bord
Compteurs : demandes en attente, utilisateurs, questions, cours. Accès rapide aux autres sections.

### Demandes d'inscription
- Liste filtrée par statut (pending/accepted/rejected)
- Accepter → crée compte + inscrit au `CoursePackage` matching (year+parcours) + envoie email
- Refuser → statut REJECTED

### Utilisateurs
- Liste avec recherche
- Colonne "Année" : lit `RegistrationRequest.year` + `parcours` par correspondance email (P2/D1 affichés en badge)
- Dropdown "Changer les inscriptions" : sélectionne un `CoursePackage` (format "P2 — PASS") → efface les `UserEnrollment` et recrée depuis le package
- Bouton ⏸/▶ activer/désactiver (impossible de se désactiver soi-même)
- Bouton 🗑 + modal de confirmation → `user.delete()` cascade

### Questions
- **Important** : étend `qcm/base.html` (pas `admin_site/base.html`) → aucun sidebar admin, onglet "Questions" navbar actif
- Accessible depuis le dropdown navbar "Questions" → "Gérer les questions"
- Filtre par cours + catégorie (guard `.isdigit()` contre le bug `course=None`)
- Pagination 50 par page
- Bouton ✏️ avec `?back=<url_encodée>` → retour à la liste filtrée après modification
- Bouton 🗑 + modal de confirmation

#### Formulaire question (add/edit)
- Textes affichés sans HTML (`|striptags`) pour édition plain text
- Champ "Correction générale" (feedback)
- Tags filtrés par cours de la question :
  - **Annales** : toujours visibles
  - **EC** : toujours visibles, avec toggle
  - **Chapitres** : masqués, révélés quand l'EC parente est cochée (JS `toggleChapters`)
  - **Si le cours n'a pas d'EC** : chapitres affichés directement (`direct_chapters`)
  - Tags sans catégorie : exclus

### Cours
- Liste + formulaire d'ajout (nom, code court, semestre)
- Changer le semestre d'un cours existant

### Tags
- `Tag.moodle_id` rendu nullable (migration `0020_tag_moodle_id_nullable.py`) pour créer des tags manuellement
- Formulaire d'ajout : nom, TagCategory, cours associé, EC parente
- Champs cours/EC affichés dynamiquement selon le type (JS `updateTagFields`)
- Tags Moodle (avec `moodle_id`) non supprimables (🔒)
- Tags manuels supprimables

---

## Navbar

- Lien "Admin" → `/admin-site/` (actif sauf sur `/admin-site/questions/`)
- Lien "Questions" → dropdown : Importer (XML), Gérer, Ajouter
- `admin_pending_registrations` badge sur le lien Admin

## Tests

`tests/test_admin_site.py` — 26 tests couvrant :
- Protection staff (accès refusé aux non-staff)
- Tableau de bord (compteurs)
- Demandes : liste, accepter (user créé, statut, enrollments), refuser
- Utilisateurs : liste, toggle, auto-désactivation impossible
- Questions : liste, ajout, modification, formulaire accessible
- Cours : liste, assignation semestre
