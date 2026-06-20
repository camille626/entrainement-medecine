# Déploiement sur un NAS Synology

## Vue d'ensemble

```
GitHub (push sur main)
  └── CI build l'image Docker, la publie sur ghcr.io (tag `latest`)

NAS Synology
  └── Portainer : stack Git pointant sur docker-compose.yml du repo
        ├── pull l'image web depuis ghcr.io (pas de build sur le NAS)
        ├── variables d'env fournies via l'UI Portainer (pas de .env committé)
        └── données persistantes en bind-mount sous /docker/studymed/data/

DSM (reverse-proxy) : termine le TLS, route vers le port nginx du stack
```

Le NAS ne build jamais l'image : c'est la CI GitHub qui s'en charge et la publie publiquement sur `ghcr.io/camille626/entrainement-medecine:latest`. Portainer n'a qu'à la pull.

## 1. CI/CD — publication de l'image

Le workflow `.github/workflows/docker-publish.yml` build et push l'image sur ghcr.io à chaque push sur `main` touchant le code applicatif (`Dockerfile`, `config/`, `qcm/`, `pyproject.toml`, etc.).

**Étape unique à faire à la main après le premier push** : le package créé par `GITHUB_TOKEN` est privé par défaut. Aller dans GitHub > onglet **Packages** du compte/repo > `entrainement-medecine` > **Package settings** > **Change visibility** > **Public**, pour que le NAS puisse pull sans authentification.

## 2. Structure sur le NAS

Créer le dossier du projet et ses sous-dossiers de données persistantes :

```bash
ssh admin@<ip-du-nas>
mkdir -p /docker/studymed/data/{postgres,media,static}
cd /docker/studymed
```

Ces dossiers sont montés en bind-mount par `docker-compose.yml` :

| Dossier NAS | Monté dans | Contenu |
|---|---|---|
| `data/postgres/` | conteneur `db` | données PostgreSQL |
| `data/media/` | conteneurs `web` et `nginx` | fichiers uploadés (images, certificats) |
| `data/static/` | conteneurs `web` et `nginx` | fichiers statiques collectés (`collectstatic`) |

## 3. Créer le stack dans Portainer

**Stacks** > **Add stack** > **Repository** :

- Repository URL : `https://github.com/camille626/entrainement-medecine`
- Compose path : `docker-compose.yml`
- **Environment variables** : saisir dans l'UI (équivalent du `.env`, voir `.env.example` pour la liste complète) :

| Variable | Valeur pour ce déploiement |
|---|---|
| `DJANGO_SECRET_KEY` | une longue chaîne aléatoire générée |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `studymed.ascot63.synology.me` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://studymed.ascot63.synology.me` |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | identifiants de la base |
| `NGINX_PORT` | port interne choisi, ex: `9666` |

Déployer le stack : Portainer clone le repo, lit `docker-compose.yml`, **pull** l'image `web` depuis ghcr.io (pas de build) et démarre les 3 services.

Pour générer `DJANGO_SECRET_KEY` :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

## 4. Configurer le reverse-proxy DSM

**Panneau de configuration** > **Portail de connexion** > **Avancé** > **Reverse Proxy** > **Créer** :

- Source : `studymed.ascot63.synology.me`, HTTPS, port 443
- Destination : `localhost`, HTTP, port `9666` (le `NGINX_PORT` choisi à l'étape 3)

Aucun en-tête personnalisé à ajouter : le conteneur `nginx` du stack force déjà `X-Forwarded-Proto: https` vers Django (voir [Note de sécurité](#note-de-securite)).

Vérifier aussi dans **Panneau de configuration** > **Sécurité** > **Certificat** que `studymed.ascot63.synology.me` a un certificat HTTPS valide associé.

## 5. Initialiser l'application

Le nom des conteneurs dépend du nom donné au stack dans Portainer (`<nom-du-stack>-web-1`, etc.) — `studymed-web-1` ci-dessous suppose un stack nommé `studymed`. Depuis Portainer (Container > `studymed-web-1` > Console) ou en SSH :

```bash
docker exec -it studymed-web-1 python manage.py createsuperuser
```

Import des données Moodle (si pas déjà fait) — nécessite que le dump SQL soit accessible dans le conteneur, par exemple copié au préalable dans `data/media/` ou un volume dédié :

```bash
docker exec -it studymed-web-1 python manage.py import_moodle --dump <chemin-du-dump>.sql
```

## 6. Tester

`https://studymed.ascot63.synology.me` doit afficher l'application, et la connexion/inscription doit fonctionner sans erreur CSRF.

## Mises à jour ultérieures

1. Un push sur `main` republie automatiquement l'image `latest` sur ghcr.io.
2. Dans Portainer : **Stacks** > `studymed` > **Pull and redeploy** (ou re-déployer le stack) pour récupérer la nouvelle image et redémarrer les conteneurs.

Les migrations et le `collectstatic` sont rejoués automatiquement par `entrypoint.sh` à chaque redémarrage du conteneur `web`.

## Sauvegarde de la base de données

```bash
docker exec studymed-db-1 pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
```

`data/postgres/` étant un dossier normal sur le NAS, il peut aussi être sauvegardé directement (Hyper Backup, snapshot du volume...) en plus des dumps SQL réguliers.

## Note de sécurité

`NGINX_PORT` (ex: `9666`) **ne doit jamais être exposé directement sur Internet** (pas de redirection de port sur la box/routeur vers ce port) — seul le port 443 du reverse-proxy DSM doit être accessible depuis l'extérieur. Le conteneur `nginx` fait confiance à son unique appelant pour la terminaison TLS et force `X-Forwarded-Proto: https` vers Django sans vérification : si ce port était exposé directement, n'importe qui pourrait usurper une connexion "sécurisée" auprès de Django.

## Référence : architecture des conteneurs

```
nginx (reverse-proxy interne, port ${NGINX_PORT:-8080})
  ├── sert /static/ et /media/ directement (bind-mounts data/static, data/media)
  └── proxy_pass tout le reste vers web:8000
web (gunicorn + Django, image ghcr.io/camille626/entrainement-medecine:latest)
db (postgres:17-alpine, bind-mount data/postgres)
```

Le `Dockerfile` est multi-stage :

- stage `builder` : installe les dépendances avec `uv sync --frozen --no-dev`
- stage `runtime` : copie l'environnement virtuel et le code depuis `builder`, tourne avec un utilisateur non-root

Au démarrage du conteneur `web`, `entrypoint.sh` exécute `migrate --noinput` puis `collectstatic --noinput` avant de lancer la commande passée (`gunicorn` par défaut).

`docker-compose.yml` garde aussi `build: .` sur le service `web`, ce qui permet à un développeur de faire `docker compose up --build` en local sans dépendre de ghcr.io ; seul un déploiement qui fait un simple `pull` (comme Portainer) utilise l'image publiée par la CI.

## Référence : variables d'environnement

| Variable | Rôle |
|----------|------|
| `DJANGO_SECRET_KEY` | Clé secrète Django (à générer, ne jamais committer) |
| `DJANGO_DEBUG` | `False` en production |
| `DJANGO_ALLOWED_HOSTS` | Liste des hôtes autorisés, séparés par des virgules |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Origines autorisées pour les requêtes POST, avec le schéma (ex: `https://studymed.ascot63.synology.me`) |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Identifiants de la base PostgreSQL |
| `NGINX_PORT` | Port interne sur lequel nginx écoute (mappé par docker-compose, défaut `8080`) |

Le `DATABASE_URL` utilisé par le service `web` est construit automatiquement dans `docker-compose.yml` à partir des variables `POSTGRES_*` (pas besoin de le dupliquer dans `.env`).
