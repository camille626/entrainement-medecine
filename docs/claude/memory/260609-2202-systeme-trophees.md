# Système de trophées (issue #23)

## Vue d'ensemble

Implémentation complète d'un système de trophées de type PlayStation (bronze/argent/or) dans `qcm/models.py`, `qcm/trophies.py`, `qcm/apps.py`. Les trophées se débloquent automatiquement selon l'activité de l'utilisateur, apparaissent dans l'onglet "Trophées" du profil, et déclenchent un toast Bootstrap 3 secondes en haut à gauche lors du déblocage.

---

## Modèles (`qcm/models.py`)

### `Trophy`
Champs : `name` (unique), `description`, `icon_emoji`, `rarity`, `study_year`, `hidden`, `condition_type`, `condition_value`, `condition_tag` (FK → Tag, nullable).

**Rareté** : `BRONZE`, `SILVER`, `GOLD`

**Année** : `YEAR_ALL = "ALL"` (Transversal), `YEAR_P2 = "P2"`, `YEAR_D1 = "D1"`, blank = Non classé.
- Ordre d'affichage profil : Transversal (0) → P2 (1) → D1 (2) → Non classé (3) via `Case/When`.

**`hidden = BooleanField`** : si True et non obtenu → affiche "???", "Trophée masqué", sans le % d'étudiants.

**11 types de conditions** (`condition_type`) :
- `questions_count` — nb de (session, question) distincts répondus
- `correct_count` — nb de (session, question) corrects
- `questions_count_tag` — idem filtré par tag
- `correct_count_tag` — idem filtré par tag
- `perfect_session` — au moins une session complète à 1.0 de score (utilise `effective_fraction`, PAS `is_correct` pour éviter le crédit partiel)
- `sessions_count` — sessions complètes **avec ≥ 10 questions** (filtre `total < 10` dans `_count_completed_sessions`)
- `erratas_accepted` — erratas acceptés par l'admin
- `zero_score_count` — (session, question) avec score effectif = 0.0 (Python loop, utilise `effective_fraction`)
- `zero_score_count_tag` — idem filtré par tag
- `login_count` — nb de `LoginEvent` enregistrés
- `consecutive_days` — plus longue série de jours de connexion consécutifs (dates distinctes)

### `UserTrophy`
`unique_together = [("user", "trophy")]`, `auto_now_add=True` → idempotent via `get_or_create`.

### `LoginEvent`
`user` (FK), `logged_at` (auto_now_add), index sur `(user, logged_at)`.
Créé automatiquement à chaque connexion via le signal `user_logged_in` dans `qcm/apps.py`.

---

## Service (`qcm/trophies.py`)

### `check_and_award_trophies(request, session)`
Appelé après chaque soumission de réponse (multichoice, QROC, ddimageortext, auto-éval QROC). Vérifie tous les trophées non encore gagnés, crée les `UserTrophy` manquants, ajoute un message Django `extra_tags="trophy"` par nouveau trophée.

### `award_login_trophies(request, user)`
Appelé uniquement depuis le signal de login. Vérifie uniquement les trophées `login_count` et `consecutive_days`. Permet l'affichage du toast immédiatement à la connexion.

### Point critique : `_has_perfect_session`
Utilise `sum(ua.effective_fraction for ua in q_answers)` par question, pas `is_correct=True`. Bug initial détecté : une question avec fraction=0.5 a `is_correct=True` mais score < 1.0 → ne doit pas compter comme parfaite.

### `_count_zero_score_questions` et `_count_zero_score_questions_tag`
Iteration Python avec `defaultdict` sur (session_id, question_id), calcul via `effective_fraction`. Approche Python nécessaire car `effective_fraction` est une propriété Python (pas stockée en DB).

---

## Signal (`qcm/apps.py`)

```python
def ready(self):
    from django.contrib.auth.signals import user_logged_in
    def on_user_logged_in(sender, request, user, **kwargs):
        from qcm.models import LoginEvent
        from qcm.trophies import award_login_trophies
        LoginEvent.objects.create(user=user)
        if request is not None:
            award_login_trophies(request, user)
    user_logged_in.connect(on_user_logged_in)
```

---

## Frontend

### Toast (`qcm/templates/qcm/base.html`)
Container `position-fixed top-0 start-0 p-3 z-index:1100`. Itère `messages` Django filtrés par `'trophy' in message.tags`. Bootstrap Toast avec `data-bs-delay="3000"` + auto-show JS.

### Onglet Trophées (`qcm/templates/qcm/profile.html`)
- `{% regroup trophy_data by year_label as year_groups %}` → en-têtes de section (Transversal / P2 / D1 / Non classé)
- Icône SVG trophée Bootstrap Icons (56×56) avec `fill="{{ entry.icon_color }}"` : or=#FFD700, argent=#B0B0B0, bronze=#CD7F32, non obtenu=#2a2a2a
- Trophée masqué non obtenu : rareté "???", nom "???", description "Trophée masqué", pas de % étudiants
- Barre de progression globale : `earned_count / total_trophies`

---

## Admin (`qcm/admin.py`)

`TrophyAdmin` avec `list_display_links = ["icon_emoji"]` et `list_editable` : `name`, `description`, `rarity`, `study_year`, `hidden`, `condition_type`, `condition_value`. Filtres par rareté, année, masqué, type de condition.

`LoginEventAdmin` avec `date_hierarchy = "logged_at"`.

---

## Commande de seed (`qcm/management/commands/seed_trophies.py`)

Idempotente via `get_or_create(name=...)`. 15 trophées définis au total, dont :
- **ST+** : Bronze, P2, masqué, `zero_score_count_tag`, seuil 10, tag "ECG"
- **Dazed and Confused** : Bronze, `zero_score_count`, seuil 50
- **Vision d'Aigle** : Argent, `erratas_accepted`, seuil 5

Si un tag nommé est introuvable → trophée créé sans tag (warning dans stdout).

---

## Migrations

- `0024_add_trophy` — modèles Trophy + UserTrophy
- `0025_trophy_erratas_accepted_condition` — ajout ERRATAS_ACCEPTED, suppression Meta.ordering
- `0026_trophy_study_year_and_zero_score` — champ study_year, condition ZERO_SCORE_COUNT
- `0027_trophy_hidden_and_year_all` — champ hidden, valeur YEAR_ALL
- `0028_trophy_zero_score_count_tag` — condition ZERO_SCORE_COUNT_TAG
- `0029_add_login_event_and_login_trophies` — modèle LoginEvent, conditions LOGIN_COUNT + CONSECUTIVE_DAYS

---

## Tests (`tests/test_trophies.py`)

27 tests couvrant : création Trophy/UserTrophy, idempotence, 11 types de conditions, trophée masqué, série de jours consécutifs (avec et sans rupture), anti-doublon login.

Point important : pour `consecutive_days` dans les tests, utiliser `timezone.now()` puis `.update(logged_at=...)` car `auto_now_add` ne permet pas de passer une date passée directement à `create()`.

---

## Décisions de conception

- **`sessions_count` filtre ≥ 10 questions** : les sessions courtes (révision rapide) ne comptent pas pour les trophées de sessions complètes.
- **Trophées login vérifiés à deux moments** : au login (signal → `award_login_trophies`) ET après chaque réponse (via `check_and_award_trophies` qui couvre tous les types). Idempotent.
- **Pas de tri par couleur** dans l'affichage profil (demande explicite de l'utilisateur).
- **Trophées transversaux en premier** dans le profil (ordre Transversal → P2 → D1 → Non classé).
