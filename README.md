# StudyMed

Plateforme web de QCMs interactifs pour l'apprentissage des cours de médecine (P2, D1).

## Fonctionnalités

- QCMs organisés par cours, EC et chapitres
- Sessions d'entraînement personnalisables (nombre de questions, thèmes, mode d'apprentissage, QROCs...)
- Modes différents : revoir uniquement les questions ratées, revoir les questions non ancrées, revoir les questions jamais réalisées ...
- Statistiques personnalisées par matière et par EC (progression, % de questions réalisées)
- Correction immédiate ou différée (format flash / format classique)
- Interface d'administration pour gérer les questions : ajouter des questions (fichiers moodle xml ou manuellement)
- Interface d'erratas : les utilisateurs peuvent signaler des erreurs dans les questions qui sont relues et acceptées/refusées par l'admin
- Multi-utilisateurs avec comptes individuels
- Des trophées inspirés de playstation

## Stack technique

- **Backend** : Django 5+ / Python 3.11
- **Base de données** : SQLite (dev) / PostgreSQL (prod)
- **Qualité** : pytest, ruff, mypy, pre-commit

## Installation

```bash
# Cloner le dépôt et synchroniser les dépendances
uv sync --active --all-extras

# Appliquer les migrations
uv run --active python manage.py migrate

# Créer un compte admin
uv run --active python manage.py createsuperuser

# Lancer le serveur de développement
uv run --active python manage.py runserver
```

L'interface d'administration est disponible sur http://127.0.0.1:8000/admin/

## Déploiement

Un déploiement Docker (gunicorn + PostgreSQL + nginx) est disponible pour un hébergement sur NAS privé, voir `docs/dev/deploiement-nas.md`.

```bash
cp .env.example .env
docker compose up -d --build
```

## Lancer les tests

```bash
uv run --active pytest tests/ -v
```

## Documentation

- Documentation du projet : https://camille626.github.io/entrainement-medecine
- Dépôt GitHub : https://github.com/camille626/entrainement-medecine
