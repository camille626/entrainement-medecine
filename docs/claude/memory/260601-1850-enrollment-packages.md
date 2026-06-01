# Inscriptions aux cours + menus (Issues #28, #41)

## Contexte

Système d'inscriptions aux cours par utilisateur avec menus prédéfinis (CoursePackage) et assignation automatique lors de l'acceptation d'une demande.

## Modèles ajoutés

### `UserEnrollment`
- `user FK`, `course FK`, `enrolled_at`, `enrolled_by FK(User, null)`
- `unique_together: (user, course)`
- Les utilisateurs ne voient que leurs cours inscrits (`is_staff` = tous les cours)

### `CoursePackage`
- `name`, `description`, `year` (P2/D1), `parcours` (PASS/LAS1/LAS2, blank)
- `courses M2M(Course)`
- Matching automatique: lors de l'acceptation d'une demande → cherche le package avec `year=req.year + parcours=req.parcours`

## `RegistrationRequest` étendu
- `year` (P2/D1) — obligatoire
- `parcours` (PASS/LAS1/LAS2) — obligatoire si P2, vide sinon
- `message` — désormais optionnel

## Formulaire d'inscription
- Cascade JS : sélectionner P2 → affiche le champ parcours
- `certificate` reste obligatoire (PDF)
- Message devient optionnel

## Admin Django

### `UserEnrollmentAdmin`
- list_display: user/course/enrolled_at/enrolled_by
- `fk_name = "user"` sur l'inline (évite l'ambiguïté des 2 FK vers User)

### `UserAdminWithEnrollments`
- Remplace le UserAdmin Django natif
- Inline `UserEnrollmentInline` (fk_name="user") pour gérer les inscriptions depuis la fiche utilisateur
- Action "Appliquer un menu" (via URL /admin/qcm/coursepackage/<id>/apply/<user_id>/)

### `CoursePackageAdmin`
- filter_horizontal pour les cours
- URL custom pour appliquer un package à un user

## Impact sur les vues

- `HomeView` : filtre par `UserEnrollment.objects.filter(user=user)` — staff voit tout
- `ConfigurationView` : formulaire `SessionConfigForm(user=request.user)` — staff voit tout
- `SessionConfigForm(user=)` : filtre `Course.objects.filter(enrollments__user=user)` si non-staff

## Données créées

- Package "Ancien PASS" : P2 + PASS, 13 cours P2
- `camille.ramelet` : inscrit aux 13 cours P2 via ce package

## Note

Le `UserAdminWithEnrollments` hérite de `admin.ModelAdmin` (pas `UserAdmin` Django natif). Le changement de mot de passe se fait via `/password_reset/` ou le shell.
