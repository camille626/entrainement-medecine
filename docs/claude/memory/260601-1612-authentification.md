# Authentification — login/logout et protection des routes (Issue #13)

## Contexte

Mise en place de l'authentification Django sur la plateforme. Toutes les pages sont protégées par `LoginRequiredMixin`. L'utilisateur non connecté est redirigé vers `/login/`.

## Ce qui a été fait

### Settings (`config/settings.py`)
- `LOGIN_URL = "/login/"`
- `LOGIN_REDIRECT_URL = "/"`
- `LOGOUT_REDIRECT_URL = "/login/"`

### URLs (`config/urls.py`)
- `LoginView` → `/login/` avec template `registration/login.html`
- `LogoutView` → `/logout/` (POST)

### Vues (`qcm/views.py`)
- Toutes les vues héritent de `LoginRequiredMixin` : HomeView, ConfigurationView, QuestionView, CheckView, FinView, TagsView, ChaptersView
- `ConfigurationView.post()` : `session.user = request.user` (QuizSession.user était nullable, maintenant toujours renseigné)

### Template login (`qcm/templates/registration/login.html`)
- Page autonome (sans base.html) avec Bootstrap CDN
- Formulaire username/password + gestion du paramètre `next`
- Lien "Demander l'accès" (pointe vers `#` pour l'instant — issue #14)

### Navbar (`qcm/templates/qcm/base.html`)
- Dropdown Bootstrap : avatar + nom d'utilisateur → menu déroulant
- Dropdown : "Profil" (lien `#` pour l'instant — issue #17) + "Déconnexion" (form POST `/logout/`)

### Tests mis à jour
- `tests/test_auth.py` : 14 tests — protection routes, login/logout, QuizSession.user
- `tests/test_views.py` : ajout fixture `client` avec `force_login` (les vues nécessitent auth)
- `tests/test_tag_filtering.py` : idem

## Points d'attention

- Les tests existants (`test_views.py`, `test_tag_filtering.py`) nécessitent maintenant un `client` avec `force_login` — pattern : fixture `client(client, db)` qui crée un user et le connecte
- Le lien "Profil" dans le dropdown sera lié à issue #17
- Le lien "Demander l'accès" sur la page login sera lié à issue #14
