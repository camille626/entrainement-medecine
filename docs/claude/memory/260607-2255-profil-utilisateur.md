# Issue #17 — Profil utilisateur

## Résumé des travaux

Implémentation complète de la page profil utilisateur : informations personnelles modifiables, photo de profil uploadable, stats résumées cohérentes avec la page Statistiques, onglet Trophées (placeholder), changement de mot de passe.

---

## Nouveaux fichiers

- `qcm/templates/qcm/profile.html` — page profil avec 2 onglets Bootstrap (Informations / Trophées)
- `qcm/templates/registration/password_change.html` — formulaire Django natif de changement de mdp, intégré dans `base.html`
- `qcm/templates/registration/password_change_done.html` — page de confirmation (lien retour profil)
- `qcm/migrations/0023_add_userprofile.py` — migration pour le modèle `UserProfile`
- `tests/test_profile.py` — 21 tests couvrant routes, GET, POST, stats, photo

---

## Modifications

### `qcm/models.py`
Ajout du modèle `UserProfile` en fin de fichier :
- `user` : `OneToOneField(User, related_name="profile")`
- `photo` : `ImageField(upload_to="profile_photos/", blank=True, null=True)`
- Accessible depuis les templates via `user.profile.photo` — Django attrape silencieusement `RelatedObjectDoesNotExist` (hérite de `AttributeError`), donc `{% if user.profile.photo %}` fonctionne sans `get_or_create` dans le template.

### `qcm/forms.py`
Ajout de `ProfileForm` (après `InscriptionForm`) :
- Champs : `first_name`, `last_name`, `email`, `photo` (ImageField, optionnel)
- `clean_email()` : unicité email hors user courant
- `clean_photo()` : limite 2 Mo
- `save()` : met à jour `User` + crée/met à jour `UserProfile.photo` si une photo est fournie
- Import ajouté : `from django.contrib.auth.models import User` et `UserProfile` depuis `.models`
- Pattern sans type hints sur `__init__` (comme `SessionConfigForm` et `InscriptionForm`)

### `qcm/views.py`
Ajout de `ProfileView(LoginRequiredMixin, View)` en fin de fichier :
- `_build_context()` : calcul des stats **identique à StatsView** — groupement par `(session_id, question_id)`, somme des fractions clampée à `[0,1]`, puis moyenne × 20. Bug initial : comptait chaque `UserAnswer` séparément (une question multichoix à 4 réponses = 4 lignes → stats faussées).
- Récupération de l'année/parcours via `RegistrationRequest` (email match + `status=ACCEPTED`)
- `get_or_create(UserProfile)` dans `_build_context`
- `post()` : passe `request.FILES` au formulaire pour l'upload photo
- Indication de succès via query param `?saved=1` (pas de messages framework — évite dépendance non vérifiée)
- Import ajouté : `UserProfile` dans la liste des imports du module

### `qcm/urls.py`
Ajout : `path("profil/", views.ProfileView.as_view(), name="profile")`

### `config/urls.py`
Ajout des routes de changement de mot de passe Django builtin :
- `profil/mot-de-passe/` → `PasswordChangeView` avec `success_url="/profil/?saved=1"` (URL hardcodée — `reverse_lazy("qcm:profile") + "?saved=1"` échoue à l'import car l'opérateur `+` force l'évaluation immédiate de la `LazyString` avant que les URLs `qcm` soient chargées)
- `profil/mot-de-passe/confirme/` → `PasswordChangeDoneView`

### `qcm/templates/qcm/base.html`
- Lien Profil activé (était `disabled`) : `{% url 'qcm:profile' %}`
- Bouton navbar user : affiche la photo de profil (20×20 circulaire) si elle existe, sinon l'icône SVG générique

---

## Points techniques saillants

### Bug `reverse_lazy` + concaténation string dans `urls.py`
```python
# ❌ Échoue — force l'évaluation de LazyString avant que les URLs soient prêtes
success_url=reverse_lazy("qcm:profile") + "?saved=1"

# ✅ Solution : URL hardcodée
success_url="/profil/?saved=1"
```

### Calcul des stats — alignement avec StatsView
```python
# ❌ Bugué — compte les UserAnswer (une question multichoix = N lignes)
total = all_ua.count()
avg_fraction = sum(ua.effective_fraction for ua in all_ua) / total

# ✅ Correct — groupe par (session, question) comme StatsView
raw = list(UserAnswer.objects.filter(...).values("session_id", "question_id", "is_correct", "answer__fraction"))
pair_fracs = defaultdict(list)
for r in raw:
    pair_fracs[(r["session_id"], r["question_id"])].append(_ua_fraction(...))
q_scores = [max(0.0, min(1.0, sum(fracs))) for fracs in pair_fracs.values()]
total_questions = len(q_scores)
avg_score = round(sum(q_scores) / total_questions * 20, 1) if total_questions else None
```

### Photo — accès safe depuis base.html sans context processor
`user.profile.photo` dans les templates est safe même si aucun `UserProfile` n'existe, car `RelatedObjectDoesNotExist` hérite de `AttributeError` et Django templates l'intercepte silencieusement. Pas besoin de context processor ni de `get_or_create` pour l'affichage navbar.

### Templates password_change — extend base.html
Contrairement aux autres templates `registration/` (standalone, pas de navbar — utilisés sans auth), `password_change.html` étend `base.html` car l'utilisateur est forcément connecté.

---

## Tests (21 tests dans `tests/test_profile.py`)

- Protection des routes (2)
- GET profil : 200, pré-remplissage champs, bandeau succès, affichage année (6)
- POST profil : mise à jour nom/prénom/email, redirect `?saved=1`, unicité email, email vide (6)
- Changement de mot de passe : page 200, lien dans profil (2)
- Photo : upload sauvegarde vers `UserProfile`, fichier trop grand → erreur, avatar placeholder (3)

Photo test pattern : `PIL.Image.new("RGB", (10, 10))` → `io.BytesIO` avec `.name` pour simuler un fichier uploadé. Utilise `settings.MEDIA_ROOT = tmp_path` pour isoler les fichiers de test.
