# Issue #59 — Dockerisation (Phase 1) — Mémoire de session

**Contexte de cette note** : l'utilisateur va activer docker-in-docker dans le devcontainer (modification probable de `.devcontainer/devcontainer.json` + rebuild). Un rebuild de devcontainer **efface tout ce qui n'est pas dans un mount persistant**. Vérification faite : seuls `~/.gitconfig`, `~/.ssh`, `~/.cache/uv` et `/etc/localtime` sont montés depuis l'host (`.devcontainer/devcontainer.json` lignes 95-100). **`/home/vscode/.claude/` n'est PAS monté** → le fichier de plan (`/home/vscode/.claude/plans/...`) et le système de mémoire auto (`/home/vscode/.claude/projects/.../memory/`) seront perdus au rebuild. Seul ce qui est sous `/workspaces/entrainement-medecine/` (bind-mount host, donc cette note) survit.

**Pour reprendre après le rebuild** : donner à Claude le chemin de ce fichier, ou lui dire "lis docs/claude/memory/260620-1157-issue59-deploiement-docker-nas.md et reprends l'issue 59".

## État au moment de l'écriture

- Branche créée et checkoutée : `59-déploiement-docker-nas-privé-+-cloud-public-avec-sync-de-données` (issue #59 via `gh issue develop 59`)
- On était en **plan mode**, plan rédigé dans `/home/vscode/.claude/plans/moonlit-leaping-sutherland.md` (sera perdu au rebuild — voir contenu complet ci-dessous), **pas encore approuvé par l'utilisateur** (ExitPlanMode a été rejeté pour donner des remarques, pas pour refuser le plan)
- Aucun fichier de code n'a encore été créé/modifié. Aucun commit fait sur la branche.

## Décisions déjà validées avec l'utilisateur

Via `AskUserQuestion`, deux choix actés :
1. **Périmètre de cette PR : Phase 1 seule (Dockerisation)**. Les phases 2 (hébergement cloud public) et 3 (sync NAS↔cloud) iront dans des **issues de suivi séparées** à créer (nécessitent des comptes/choix externes que je ne peux pas faire depuis ce sandbox).
2. **Stratégie de sync (phase 3) : pas encore décidée**, à documenter comme options ouvertes dans l'issue de suivi (Option A : DB cloud partagée vs Option B : DBs indépendantes + export/import via `dumpdata`/`loaddata`).

## Constat technique important : Docker indisponible dans ce sandbox

`docker`, `docker-compose`, `podman` : aucun n'est installé, pas de socket `/var/run/docker.sock`. Impossible de faire `docker build`/`docker compose up` pour valider de bout en bout depuis cet environnement actuel. **Une fois docker-in-docker activé par l'utilisateur, ce constat change** — il faudra re-vérifier la disponibilité de `docker` et, si possible, basculer la validation sur un vrai `docker compose up --build` plutôt que sur les tests pytest de substitution décrits ci-dessous.

## Constat additionnel : `.venv` parasite à la racine du repo

`/workspaces/entrainement-medecine/.venv` existe (créé le 2 juin, probablement par un `uv sync` lancé sans `--active` à un moment donné) **mais n'est pas l'environnement actif**. L'environnement réellement utilisé est `/home/vscode/.venv` (confirmé : `VIRTUAL_ENV=/home/vscode/.venv`, `which python` → `/home/vscode/.venv/bin/python`, et `devcontainer.json` fixe `UV_PYTHON=/home/vscode/.venv/bin/python`). Le `.venv` racine est déjà ignoré par `.gitignore` (`.venv/`) et sera de toute façon exclu par l'entrée `.venv` prévue dans le futur `.dockerignore` — **aucun impact sur le plan Docker**, c'est juste un répertoire mort que l'utilisateur peut supprimer s'il veut faire le ménage (pas fait automatiquement, action destructive non demandée).

## Plan complet rédigé (à dérouler une fois le rebuild fait et le plan approuvé)

### Fichiers à créer/modifier

- **`Dockerfile`** (racine) — multi-stage avec `uv` :
  - stage `builder` (`python:3.11-slim`) : installe `uv`, `uv sync --frozen --no-dev --no-install-project`, copie le code, `uv sync --frozen --no-dev`
  - stage `runtime` (`python:3.11-slim`) : copie le venv + code depuis `builder`, crée un user non-root, `ENV PATH="/app/.venv/bin:$PATH"`, `EXPOSE 8000`, `ENTRYPOINT ["./entrypoint.sh"]`, `CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]`
- **`entrypoint.sh`** (racine, `chmod +x`) — `migrate --noinput` puis `collectstatic --noinput`, puis `exec "$@"`
- **`docker-compose.yml`** (racine) — services `db` (postgres:17-alpine + volume + healthcheck), `web` (build local, `env_file: .env`, volumes media/static, `depends_on: db` avec `condition: service_healthy`), `nginx` (nginx:alpine, sert `/static/` et `/media/` directement via volumes partagés, reverse-proxy le reste vers `web:8000`, port externe configurable via `${NGINX_PORT:-8080}` pour ne pas entrer en conflit avec l'UI web du NAS)
- **`docker/nginx.conf`** — config nginx (alias static/media + proxy_pass + headers `X-Forwarded-*`)
- **`.env.example`** (racine) — `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD` (le `DATABASE_URL` du service `web` est dérivé de ces variables Postgres directement dans `docker-compose.yml`, pas besoin de le dupliquer dans `.env`)
- **`.dockerignore`** (racine) — exclut `.venv` (couvre le parasite racine), `.git`, `tests/`, `notebooks/`, `docs/`, `data/raw/*`, `db.sqlite3`, `media/`, `staticfiles/`, caches, `.devcontainer/`
- **`pyproject.toml`** — ajoute `gunicorn` aux `dependencies` (runtime, pas `dev`) ; régénérer `uv.lock` avec `uv lock`
- **`tests/test_deployment.py`** (nouveau, TDD adapté à l'infra) — vérifie : Dockerfile multi-stage (2 `FROM`, stages `builder`/`runtime`), `docker-compose.yml` valide (parsé en YAML, `pyyaml` déjà dispo transitivement via `cruft`/`mkdocs` dans les extras `dev`) et contient les services `db`/`web`/`nginx` + volumes media/static sur `web`, `entrypoint.sh` exécutable (`os.access(path, os.X_OK)`), `gunicorn` listé dans `pyproject.toml`, `.env.example` documente les variables clés
- **`docs/dev/deploiement-nas.md`** (nouveau) + entrée dans **`docs/dev/.nav.yml`** — architecture Docker, variables d'env, commandes (`docker compose up -d --build`, `docker compose exec web python manage.py createsuperuser`, sauvegarde du volume Postgres), note explicite que HTTPS/`CSRF_TRUSTED_ORIGINS` sont hors scope (à traiter si un reverse-proxy TLS est ajouté plus tard — pas nécessaire pour un accès HTTP simple sur le NAS)
- **`CLAUDE.md`** — ajoute `Dockerfile`/`docker-compose.yml`/`entrypoint.sh` à l'arborescence + section "Déploiement NAS" renvoyant vers la doc
- **`README.md`** — courte mention + lien vers la doc

### Pas de changement dans `config/settings.py`

Déjà prêt pour la prod (`DATABASE_URL`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_DEBUG`, whitenoise pour les statics). Pas besoin de `CSRF_TRUSTED_ORIGINS` pour un accès HTTP simple — documenté comme point d'attention futur si HTTPS est ajouté.

### Étapes d'implémentation

1. Écrire `tests/test_deployment.py` (RED)
2. Créer `Dockerfile`, `entrypoint.sh` (+exécutable), `docker-compose.yml`, `docker/nginx.conf`, `.env.example`, `.dockerignore`
3. Ajouter `gunicorn` à `pyproject.toml`, `uv lock`, `uv sync --active --all-extras`
4. `uv run --active pytest tests/test_deployment.py -v` jusqu'au GREEN, puis suite complète
5. `ruff check .` / `ruff format .` / `mypy`
6. Rédiger `docs/dev/deploiement-nas.md` + nav, `CLAUDE.md`, `README.md`
7. `mkdocs build --strict`
8. **Si Docker est maintenant disponible (post-rebuild)** : ajouter une vraie validation `docker compose up -d --build` + smoke-test HTTP, en plus des tests pytest

### Vérification

- `uv run --active pytest tests/ -v` → tout passe
- `ruff check .` + `pre-commit run --all-files` → propre
- `mkdocs build --strict` → sans erreur
- Si Docker dispo : `docker compose up -d --build` réel + test manuel de l'app
