# Project: entrainement medecine

## Description
Plateforme web de QCMs interactifs pour l'apprentissage des cours de médecine (P2). Basée sur un export de 6 493 questions depuis MoodleCloud, réparties sur 13 cours P2.

## La Stack Technique
- **Langage**: Python 3.11
- **Framework web**: Django 5+
- **Base de données**: SQLite (dev) / PostgreSQL (prod via `DATABASE_URL`)
- **Gestionnaire de dépendances**: uv & pyproject.toml
- **Environnement de développement**: VS Code Dev Container
- **Qualité de Code**: pre-commit hooks avec ruff, mypy (avec django-stubs)
- **Tests**: pytest + pytest-django
- **Frontend**: Bootstrap 5 + HTMX (CDN, pas de build step)
- **Documentation**: MkDocs & mkdocs-material

## Structure du Projet

```
.
├── .claude/                # Configuration Claude Code
│   └── commands/          # Commandes slash personnalisées
├── .devcontainer/          # Configuration du dev container
├── .github/workflows/      # CI/CD GitHub Actions
├── config/                 # Configuration Django
│   ├── settings.py        # Paramètres (SQLite dev / PostgreSQL prod)
│   ├── urls.py            # Routing principal
│   └── wsgi.py            # Point d'entrée WSGI
├── data/
│   ├── raw/               # Données brutes (export Moodle, non versionnées)
│   └── processed/         # Données traitées
├── docs/                   # Documentation MkDocs
│   ├── index.md           # Page d'accueil de la documentation
│   ├── user/              # Documentation utilisateur
│   ├── dev/               # Documentation développeur
│   └── claude/
│       └── memory/        # Mémoire projet (décisions, apprentissages)
├── notebooks/             # Notebooks Jupyter pour l'exploration
├── qcm/                   # App Django principale
│   ├── migrations/        # Migrations de base de données
│   ├── admin.py           # Interface d'administration
│   ├── apps.py
│   └── models.py          # Course, Category, Question, Answer, QuizSession, UserAnswer, ImageDragItem, ImageDropZone
├── src/                   # Code source Python (utilitaires, scripts)
├── tests/                 # Tests unitaires et d'intégration
│   └── test_models.py     # Tests des modèles Django (18 tests)
├── manage.py              # Point d'entrée Django
├── .gitignore
├── .pre-commit-config.yaml
├── CLAUDE.md              # Ce fichier - Documentation pour Claude Code
└── pyproject.toml         # Configuration du projet et dépendances
```

## Environnement de Développement

### Prérequis
- Docker
- VS Code avec extensions:
  - Dev Containers
  - Python (ms-python.python)
  - Jupyter (ms-toolsai.jupyter)
  - Copilot Chat
  - Ruff formatter

### Installation
1. Ouvrir le projet dans VS Code
2. Accepter la proposition d'ouvrir dans un Dev Container
3. Le container se construit automatiquement avec toutes les dépendances

### Gestion des Dépendances
Les dépendances sont gérées via `uv` et définies dans `pyproject.toml`:

```bash
# Sync des dépendances
uv sync --active --all-extras

# Tests
uv run --active pytest

# Documentation
uv run --active mkdocs build --strict

# Precommit
pre-commit run --all-files
```

### Commandes Django

```bash
# Lancer le serveur de développement
uv run --active python manage.py runserver

# Appliquer les migrations
uv run --active python manage.py migrate

# Créer un superuser
uv run --active python manage.py createsuperuser

# Générer de nouvelles migrations après modification des modèles
uv run --active python manage.py makemigrations

# Importer les données depuis le dump Moodle (idempotent, relançable)
# Importe multichoice, shortanswer (QROC) ET ddimageortext (légendes interactives).
# Détecte automatiquement moodledata/ voisin du dump pour les images de fond ddimageortext.
# Nécessite postgresql-client-17 (installé dans le devcontainer).
uv run --active python manage.py import_moodle --dump data/raw/plateforme-medecine_moodlecloud.sql
# Optionnel : spécifier le répertoire moodledata manuellement
# uv run --active python manage.py import_moodle --dump ... --moodledata data/raw/moodledata

# Lister les questions avec des images @@PLUGINFILE@@ non encore uploadées
uv run --active python manage.py find_missing_images

# Créer les erratas IMAGE pour toutes les questions avec des <img> cassés (idempotent)
# --dry-run pour prévisualiser, --reporter <username> pour choisir le reporter
uv run --active python manage.py seed_image_erratas [--dry-run] [--reporter <username>]

# URLs de l'application
# /                          → accueil (cours par semestre)
# /entrainement/             → configuration d'une session
# /entrainement/session/<id>/ → question courante (QCM + QROC mixtes si option cochée)
# /entrainement/session/<id>/check/ → soumission réponse (multichoix ou QROC)
# /entrainement/session/<id>/check-qroc/ → auto-évaluation QROC (j'avais bon/faux)
# /entrainement/session/<id>/fin/ → résultats
# /admin-site/               → tableau de bord admin web (staff uniquement)
# /admin-site/demandes/      → gestion des demandes d'inscription
# /admin-site/utilisateurs/  → gestion des utilisateurs
# /admin-site/questions/     → liste/modification/suppression des questions
# /admin-site/cours/         → gestion des cours et semestres
# /admin-site/tags/          → gestion des tags
# /errata/<pk>/upload-image/ → upload image pour un errata type IMAGE (POST, staff)
```

**Important** : toujours utiliser `uv run --active` pour éviter de créer un environnement `.venv` parasite.

## Qualité du Code

### Pre-commit Hooks
Des hooks pre-commit sont configurés pour maintenir la qualité du code:

```bash
# Installer les hooks
pre-commit install

# Lancer manuellement sur tous les fichiers
pre-commit run --all-files
```

### Linting et Formatage
Le projet utilise `ruff` pour le linting et le formatage.

**Configuration**: Toute la configuration de ruff se trouve dans `pyproject.toml` sous les sections `[tool.ruff]` et `[tool.ruff.lint]`.

```bash
# Vérifier le code
ruff check .

# Formater le code
ruff format .

# Voir la configuration actuelle
ruff check --show-settings
```

## Tests

```bash
# Lancer tous les tests
pytest

# Lancer avec coverage
pytest --cov=src --cov-report=html
```

## Documentation

Ce projet utilise **MkDocs** avec le thème Material pour générer une documentation professionnelle.

### Structure de la documentation

La documentation est organisée en deux sections principales :

- **`docs/user/`** : Documentation pour les **utilisateurs** du projet (installation, utilisation, guides)
- **`docs/dev/`** : Documentation pour les **développeurs** qui contribuent (architecture, contribution, API interne)

### Commandes MkDocs

```bash
# Installer les dépendances de documentation
uv sync --extra docs

# Prévisualiser la documentation localement (http://localhost:8000)
uv run mkdocs serve

# Construire la documentation pour la production
uv run mkdocs build --strict
```

### Déploiement automatique

La documentation est automatiquement construite et déployée sur GitHub Pages via la workflow `.github/workflows/docs.yml` :
- Déclenché à chaque push sur `main` modifiant `docs/` ou `mkdocs.yml`
- Disponible à l'URL : https://camille626.github.io/entrainement-medecine

### Bonnes pratiques de rédaction

Lors de la génération de documentation avec l'IA (Claude Code), suivre ces principes :

#### ✅ À faire

**Décrire l'état actuel** du système :
- Expliquer ce que le système **fait maintenant**
- Fournir des spécifications techniques et des exemples d'utilisation
- Documenter les fonctionnalités telles qu'elles existent
- Utiliser le présent de l'indicatif

#### ❌ À éviter

- **Références historiques** : Éviter "L'issue #X a amélioré..." ou "La version 2.0 a introduit..."
- **Récits d'évolution** : Éviter "Nous avons d'abord implémenté X, puis Y..."
- **Marqueurs temporels** : Éviter "Nouvelle fonctionnalité", "Récemment ajouté", "Bientôt disponible"
- **Métriques de tests** : Ne pas inclure le nombre de tests ou le taux de couverture dans la documentation

#### Exemple de bonne documentation

**❌ Mauvais** :
> "Nouvelle dans l'issue #42 : L'authentification JWT est maintenant disponible. C'est une amélioration majeure par rapport à l'ancienne méthode OAuth que nous utilisions avant."

**✅ Bon** :
> "L'authentification utilise des tokens JWT (JSON Web Tokens) signés avec RS256. Les tokens ont une durée de vie de 24h et peuvent être renouvelés via le refresh token."

#### Où placer les références historiques

Les références aux issues GitHub et l'historique ont leur place dans :
- ✅ Les sections dédiées "Historique" ou "Notes de développement" (en fin de document)
- ✅ Les messages de commit et pull requests
- ✅ Les commentaires de code expliquant des décisions techniques
- ✅ Le fichier `docs/claude/memory/` pour la mémoire contextuelle
- ❌ **Jamais** dans la documentation fonctionnelle principale (user/ ou dev/)

### Organisation docs/user/ vs docs/dev/

**`docs/user/`** - Pour ceux qui **utilisent** le projet :
- Installation et configuration
- Guides d'utilisation et tutoriels
- Cas d'usage et exemples pratiques
- FAQ et dépannage
- API publique (endpoints, fonctions exposées)

**`docs/dev/`** - Pour ceux qui **modifient** le projet :
- Architecture et design patterns
- Configuration de l'environnement de développement
- Guide de contribution et standards de code
- API interne et structure du code
- Processus de développement et workflow

## Conventions de Code

### Commits
Suivre la convention Conventional Commits:
- `feat:` Nouvelle fonctionnalité
- `fix:` Correction de bug
- `docs:` Documentation
- `test:` Ajout/modification de tests
- `chore:` Tâches de maintenance
- `refactor:` Refactoring sans changement de fonctionnalité

Exemple: `feat(data): ajouter pipeline de preprocessing`

### Style Python
- Utiliser les type hints autant que possible
- Documenter les fonctions avec des docstrings
- Respecter PEP 8 (appliqué automatiquement par ruff)
- Maximum 88 caractères par ligne

## Commandes Claude Code

Ce projet inclut des commandes slash pré-configurées pour Claude Code :

### `/fix-issue {numéro}`
Workflow TDD complet pour résoudre une issue GitHub :
- Récupère les détails de l'issue
- Crée une branche depuis l'issue
- Implémente en TDD (tests RED puis code)
- Vérifie qualité (tests, lint, typecheck)
- Met à jour la documentation
- Commit, push et crée la PR

### `/stocke-memoire`
Sauvegarde les apprentissages et décisions importantes dans `docs/claude/memory/` avec horodatage.

#### Organisation du dossier docs/claude/memory/

Ce dossier sert à conserver une trace des décisions importantes, apprentissages et contexte du projet :

- **Format des fichiers** : Markdown (`.md`)
- **Nommage** : `YYMMDD-HHMM-sujet.md` (ex: `251121-1430-architecture-api.md`)
- **Contenu suggéré** :
  - Décisions d'architecture et leur justification
  - Solutions à des problèmes complexes
  - Patterns de code spécifiques au projet
  - Leçons apprises pendant le développement
  - Contexte métier important

Cette mémoire aide Claude Code à maintenir la cohérence du projet au fil du temps.

## Workflow de Développement

### Cycle typique de développement avec Claude Code

Le workflow complet est détaillé dans [.claude/commands/fix-issue.md](.claude/commands/fix-issue.md).

**Résumé du cycle** :

1. **Démarrage** : Créer ou prendre une issue GitHub
2. **Branche** : `gh issue develop {numéro}` crée automatiquement une branche
3. **TDD** :
   - Écrire les tests qui échouent (RED)
   - Implémenter le code minimum pour passer les tests (GREEN)
   - Refactorer si nécessaire (REFACTOR)
4. **Qualité** : Vérifier que tests, linting et typecheck passent
5. **Documentation** : Mettre à jour README.md, CLAUDE.md si nécessaire
6. **Commit** : Message suivant Conventional Commits
7. **CI/CD** : Attendre que la CI passe avant de continuer
8. **PR** : Créer la pull request et demander validation

**Commande rapide** : Utilisez `/fix-issue {numéro}` pour automatiser ce workflow complet.

### Développement exploratoire

Pour l'exploration de données ou le prototypage :

1. Travailler dans `notebooks/` pour l'exploration
2. Une fois le code stabilisé, le déplacer dans `src/`
3. Ajouter des tests dans `tests/`
4. Documenter les insights dans `docs/claude/memory/`

## Commandes Shell Utiles

```bash
# Synchroniser les dépendances
uv pip sync

# Lancer les tests
pytest

# Vérifier la qualité du code
ruff check .

# Formater le code
ruff format .

# Lancer pre-commit hooks
pre-commit run --all-files

# Mettre à jour pre-commit hooks
pre-commit autoupdate

# Prévisualiser la documentation
uv run mkdocs serve

# Construire la documentation
uv run mkdocs build --strict
```

## Ressources
- Dépôt GitHub: https://github.com/camille626/entrainement-medecine
- Documentation du projet: https://camille626.github.io/entrainement-medecine
- Documentation Python: https://docs.python.org/3.11/
- Documentation uv: https://github.com/astral-sh/uv
- Documentation ruff: https://docs.astral.sh/ruff/
- Documentation MkDocs: https://www.mkdocs.org/
