# Guide d'installation

## Prérequis

- Docker + VS Code avec l'extension Dev Containers
- ou Python 3.11+ avec `uv` installé

## Installation avec Dev Container (recommandé)

1. Ouvrir le projet dans VS Code
2. Accepter la proposition d'ouvrir dans un Dev Container
3. Le container se construit automatiquement avec toutes les dépendances

## Installation manuelle

```bash
# Synchroniser les dépendances
uv sync --active --all-extras

# Appliquer les migrations de base de données
uv run --active python manage.py migrate

# Créer un compte administrateur
uv run --active python manage.py createsuperuser
```

## Lancer l'application

```bash
uv run --active python manage.py runserver
```

L'application est accessible sur http://127.0.0.1:8000/

L'interface d'administration est accessible sur http://127.0.0.1:8000/admin/

## Variables d'environnement

Créer un fichier `.env` à la racine du projet pour configurer l'application :

```env
# Obligatoire en production
DJANGO_SECRET_KEY=votre-clé-secrète

# Optionnel (True par défaut)
DJANGO_DEBUG=False

# Optionnel — connexion PostgreSQL en production
DATABASE_URL=postgresql://user:password@host:5432/dbname  # pragma: allowlist secret

# Optionnel (localhost,127.0.0.1 par défaut)
DJANGO_ALLOWED_HOSTS=mondomaine.com
```
