# Entrainement Médecine

Plateforme web de QCMs interactifs pour l'apprentissage des cours de médecine (P2).

## Fonctionnalités

- QCMs organisés par cours et catégories (13 cours P2)
- Sessions d'entraînement personnalisables (nombre de questions, thèmes)
- Mode révision : revoir uniquement les questions ratées
- Statistiques personnalisées par matière (progression, % de questions réalisées)
- Correction immédiate ou différée (format flash / format classique)
- Interface d'administration pour gérer les questions
- Multi-utilisateurs avec comptes individuels

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

## Lancer les tests

```bash
uv run --active pytest tests/ -v
```

## Documentation

- Documentation du projet : https://camille626.github.io/entrainement-medecine
- Dépôt GitHub : https://github.com/camille626/entrainement-medecine
