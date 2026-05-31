# Interface d'entraînement — Session de QCMs (Issue #5)

## Contexte

Création de l'interface web complète permettant à un utilisateur de lancer et réaliser une session de QCMs. Aucune authentification (QuizSession.user nullable). Bootstrap 5 + HTMX via CDN.

## Modifications de modèles (migrations 0006 et 0007)

### `Question.feedback`
- `feedback = TextField(blank=True)` — correspond à `generalfeedback` dans Moodle
- Import mis à jour : `update_or_create` (au lieu de `get_or_create`) pour permettre la mise à jour du feedback sur les questions existantes
- Nettoyage des séquences d'échappement COPY PostgreSQL : `.replace("\\r\\n", "<br>").replace("\\n", "<br>").replace("\\r", "")` — les `\r\n` littéraux venaient du format COPY PostgreSQL et apparaissaient comme texte visible dans le browser

### `QuizSession` modifié
- `user` rendu nullable (pas d'auth pour l'instant)
- `shuffle_answers = BooleanField(default=True)` — option de mélange des propositions
- `questions = ManyToManyField(through=QuizSessionQuestion)` — ordre des questions de la session

### `QuizSessionQuestion` (nouveau through model)
- `session` FK, `question` FK, `order IntegerField`
- unique_together (session, question)
- ordering par order

## Nouveaux fichiers

### `qcm/urls.py`
```
/                                   → home
/entrainement/                      → configuration
/entrainement/session/<id>/         → question courante
/entrainement/session/<id>/check/   → HTMX check (POST)
/entrainement/session/<id>/fin/     → résultats
```

### `qcm/forms.py` — `SessionConfigForm`
- `courses` (ModelMultipleChoiceField avec checkboxes)
- `mode` (radio: training/deferred)
- `nb_questions` (IntegerField 1-100, défaut 10)
- `tags` (ModelMultipleChoiceField optionnel)
- `shuffle_answers` (BooleanField, défaut True)

### `qcm/views.py`

**`get_answers(question, shuffle=True)`** — helper : ordre déterministe basé sur `question.pk` (même ordre question/correction/relecture). `shuffle=False` → ordre alphabétique d'origine.

**`HomeView`** — cours groupés par StudyYear/Semester

**`ConfigurationView`** — formulaire POST → crée QuizSession + QuizSessionQuestion (sélection aléatoire des questions)

**`QuestionView`** — question courante = première QuizSessionQuestion sans UserAnswer correspondant

**`CheckView`** — HTMX POST : enregistre UserAnswer pour chaque réponse cochée, retourne `_correction.html` partiel qui remplace toute la zone réponses

**`FinView`** — agrège UserAnswers, calcule note /20, note brute, compteurs correct/partial/incorrect

### Templates `qcm/templates/qcm/`
- `base.html` — Bootstrap 5 CDN + HTMX 1.9.12 CDN
- `home.html` — cours par semestre
- `configuration.html` — formulaire avec cases cours, mode, tags, shuffle
- `question.html` — HTMX target = `#answers-zone` (remplacé par correction)
- `_correction.html` — affichage post-Check : ✓/✗/○ par proposition avec fraction, panneau feedback jaune, bouton suivant/fin
- `fin.html` — note /20, compteurs, accordion "Relecture" avec toutes les questions détaillées

## Logique de scoring

- Score par question = somme des fractions des réponses cochées, clampé à [0,1]
- `max_score` = somme des fractions positives des réponses de la question
- `ratio = score / max_score` → correct (≥1), partial (>0), incorrect (=0)
- Note sur 20 = `(total_score / total_questions) * 20`

## Ordre des propositions

`get_answers(question, shuffle)` :
- `shuffle=True` : `random.Random(question.pk).shuffle(answers)` — déterministe, cohérent entre question/check/relecture
- `shuffle=False` : ordre DB (alphabétique Moodle)
- Contrôlé par `QuizSession.shuffle_answers` (option cochée par défaut dans le formulaire)

## Affichage de la correction (pendant la tentative et en relecture)

Code couleur identique pour les deux contextes :
- Fond vert + ✓ : coché ET correct
- Fond rouge + ✗ : coché ET incorrect
- Bordure verte + ○ : correct mais non coché
- Neutre : incorrect non coché
- Fraction affichée à droite de chaque proposition

## Import Moodle mis à jour

`_import_questions` passe de `get_or_create` à `update_or_create` pour mettre à jour `feedback` des questions existantes. Nettoyage COPY sequences dans le feedback.

## Commandes utiles

```bash
# Lancer le serveur
uv run --active python manage.py runserver

# Re-importer pour mettre à jour les feedbacks
uv run --active python manage.py import_moodle --dump data/raw/plateforme-medecine_moodlecloud.sql

# Toujours utiliser --active pour ne pas créer de .venv parasite
```

## Issues futures liées
- **#10** : Filtrage dynamique tags par cours (HTMX) + hiérarchie TagCategory (annee/souscategorie/chapitre)
- **Auth** : QuizSession.user nullable → à remplir quand auth implémentée
