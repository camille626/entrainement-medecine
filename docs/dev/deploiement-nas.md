# Déploiement sur un NAS Synology

## Vue d'ensemble

```
GitHub (push sur main)
  └── CI build l'image Docker, la publie sur ghcr.io (tag `latest`)

NAS Synology
  └── Portainer : stack Git pointant sur docker-compose.yml du repo
        ├── pull l'image web depuis ghcr.io (pas de build sur le NAS)
        ├── variables d'env fournies via l'UI Portainer (pas de .env committé)
        └── tous les fichiers nécessaires (données + config nginx) montés en
            bind-mount sous ${STORAGE_DIR}/ (ex: /volume1/docker/studymed/),
            indépendant du dossier interne où Portainer clone le repo

DSM (reverse-proxy) : termine le TLS, route vers le port nginx du stack
```

Le NAS ne build jamais l'image : c'est la CI GitHub qui s'en charge et la publie sur `ghcr.io/camille626/entrainement-medecine:latest` à chaque push sur `main`. Portainer n'a qu'à la pull.

Comme plus aucun service de `docker-compose.yml` n'a besoin de code local pour fonctionner (`db` ne dépend de rien, `web` pull son image), Portainer n'est pas garanti de cloner le repo en entier — seul `docker-compose.yml` lui-même est garanti d'être présent. Tout fichier dont la stack a besoin sur disque (données persistantes **et** config nginx) est donc monté via un chemin **absolu**, fourni par `STORAGE_DIR` (voir étape 3), plutôt que relatif au clone du repo :

| Sous-dossier | Origine | Recréé automatiquement par Docker ? |
|---|---|---|
| `${STORAGE_DIR}/data/` | données applicatives (Postgres, médias, statiques) | oui, au démarrage |
| `${STORAGE_DIR}/conf/nginx.conf` | copie manuelle du fichier du repo (`conf/nginx.conf`) | non — à déposer soi-même, voir étape 2 |
| `${STORAGE_DIR}/import_init/` | fixture + médias pour l'import initial (étape 5) | non — à créer soi-même, voir étape 2 |

## 1. CI/CD — publication de l'image

Le workflow `.github/workflows/docker-publish.yml` build et push l'image sur ghcr.io à chaque push sur `main` touchant le code applicatif (`Dockerfile`, `config/`, `qcm/`, `pyproject.toml`, etc.).

Le package est public dès le premier push (il hérite de la visibilité publique du dépôt), donc le NAS peut le pull sans authentification. À vérifier si besoin sur la page du package (lien "Packages" dans la sidebar du repo) > **Package settings** > section **Danger Zone** > **Change package visibility**.

## 2. Structure sur le NAS

Choisir un dossier de stockage, ex: `/volume1/docker/studymed`, et **créer toute l'arborescence soi-même** (via File Station, ou `mkdir -p` en SSH) **avant le premier déploiement du stack** :

```
${STORAGE_DIR}/
├── data/
│   ├── postgres/
│   ├── media/
│   └── static/
├── conf/
│   └── nginx.conf          # copie manuelle de conf/nginx.conf du repo
└── import_init/
```

Deux raisons indépendantes imposent de tout créer à l'avance sur le NAS (alors que ce n'est pas nécessaire en local) :

1. Le moteur Docker embarqué par Synology Container Manager est souvent plus ancien que celui du devcontainer/host de dev, et **refuse** de démarrer si un dossier de bind-mount n'existe pas (`Bind mount failed: ... does not exist`) plutôt que de le créer automatiquement — concerne `data/postgres/`, `data/media/`, `data/static/`.
2. Comme plus aucun service de la stack n'a besoin du code applicatif (voir [Vue d'ensemble](#vue-densemble)), Portainer n'est pas garanti de cloner le repo en entier — `conf/nginx.conf` et `import_init/` doivent donc exister **en dehors** du clone Portainer, peu importe que celui-ci soit complet ou non.

**Sur `data/media/` et `data/static/`**, donner tout de suite le droit Lecture/Écriture au groupe **"Tout le monde"** (File Station > Propriétés > Permission) : les ACL Synology empêchent souvent le `chown` que fait le conteneur `web` au démarrage de prendre effet, ce qui fait échouer `collectstatic` avec une `PermissionError` (voir [Dépannage](#depannage-permissionerror-sur-staticfiles-ou-media) si ça arrive malgré tout).

Pour `conf/nginx.conf`, copier le contenu du fichier du repo (`conf/nginx.conf`) tel quel via File Station — il évoluera peu, mais en cas de changement futur du fichier dans le repo, il faudra répéter cette copie manuellement (contrairement à `docker-compose.yml` lui-même, toujours lu depuis le clone Portainer).

`data/postgres/`, `data/media/`, `data/static/` sont normalement re-`chown`-és par `entrypoint.sh` à chaque démarrage du conteneur `web` (nécessaire pour qu'un utilisateur non-root puisse y écrire, voir [Référence : architecture des conteneurs](#reference-architecture-des-conteneurs)) — d'où la recommandation ci-dessus de donner directement les droits "Tout le monde" sur le NAS, où ce `chown` n'a pas toujours d'effet réel (voir [Dépannage](#depannage-permissionerror-sur-staticfiles-ou-media) si l'erreur apparaît malgré tout).

`conf/nginx.conf` et `import_init/` sont différents : montés en lecture seule, ils ne sont **jamais** touchés par `entrypoint.sh`. S'ils ont été créés par Docker plutôt que par toi (ex: en root, lors d'un déploiement précédent), ils restent root-owned pour toujours, et plus aucun outil DSM (File Station compris) ne peut y écrire sans passer par un conteneur jetable — voir [Dépannage](#depannage-import_init-deja-cree-en-root) si c'est déjà arrivé.

| Dossier                                                | Monté dans                      | Contenu                                          |
| ------------------------------------------------------ | ------------------------------- | ------------------------------------------------ |
| `${STORAGE_DIR}/data/postgres/`                        | conteneur `db`                  | données PostgreSQL                               |
| `${STORAGE_DIR}/data/media/`                           | conteneurs `web` et `nginx`     | fichiers uploadés (images, certificats)          |
| `${STORAGE_DIR}/data/static/`                          | conteneurs `web` et `nginx`     | fichiers statiques collectés (`collectstatic`)   |
| `${STORAGE_DIR}/import_init/`                          | conteneur `web` (lecture seule) | fixture + médias pour l'import initial (étape 5) |
| `${STORAGE_DIR}/conf/nginx.conf`                       | conteneur `nginx` (lecture seule) | config nginx, copiée à la main depuis le repo  |


Pour des tests sur le host, créer la même arborescence avant le premier `docker compose up` (voir étape 3') :

```bash
source .env.local_temp   # pour pouvoir réutiliser $NGINX_PORT / $STORAGE_DIR ci-dessous
mkdir -p "$STORAGE_DIR/import_init" "$STORAGE_DIR/conf"
cp conf/nginx.conf "$STORAGE_DIR/conf/"
```


## 3. Créer le stack dans Portainer

**Stacks** > **Add stack** > **Repository** :

- Name : `studymed`
- Build method : Repository
- Repository URL : `https://github.com/camille626/entrainement-medecine`
- Repository reference : `refs/heads/main` et pendant la phase de mise au point : `refs/heads/59-déploiement-docker-nas-privé-+-cloud-public-avec-sync-de-données`
- Compose path : `docker-compose.yml`
- **Environment variables** : saisir dans l'UI (ou charger depuis un `.env` local au poste qui ouvre Portainer) :

| Variable                                              | Valeur pour ce déploiement                              |
| ----------------------------------------------------- | ------------------------------------------------------- |
| `DJANGO_SECRET_KEY`                                   | une longue chaîne aléatoire générée                     |
| `DJANGO_DEBUG`                                        | `False`                                                 |
| `DJANGO_ALLOWED_HOSTS`                                | `studymed.ascot63.synology.me`                          |
| `DJANGO_CSRF_TRUSTED_ORIGINS`                         | `https://studymed.ascot63.synology.me`                  |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | identifiants de la base                                 |
| `NGINX_PORT`                                          | port interne choisi, ex: `9666`                         |
| `STORAGE_DIR`                                         | `/volume1/docker/studymed` (dossier choisi à l'étape 2) |

Déployer le stack : Portainer clone le repo, lit `docker-compose.yml`, pull l'image `web` depuis ghcr.io, et démarre les 3 services.

Pour générer `DJANGO_SECRET_KEY` :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

## 3'. Tester la stack en local

Équivalent de l'étape 3, mais en local (sans Portainer ni NAS) pour valider la stack — et notamment tester une modification de code avant qu'elle soit publiée sur ghcr.io par la CI.

> **Ne pas tester depuis le devcontainer.** Le devcontainer utilise docker-in-docker : son daemon Docker imbriqué crée un réseau bridge isolé pour la stack, mais la connectivité TCP entre conteneurs est instable dans cet environnement (timeout entre `web` et `db` même quand les deux sont démarrés). Deux alternatives fiables : tester **depuis la machine hôte** (ci-dessous) ou directement **sur le NAS** après déploiement.

Utiliser un fichier d'env séparé (`.env.local_temp`, ignoré par git) plutôt que `.env`, pour ne pas écraser la config de prod :

```
DJANGO_SECRET_KEY=une-cle-quelconque-pour-les-tests
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:8081
POSTGRES_DB=studymed
POSTGRES_USER=studymed
POSTGRES_PASSWORD=studymed
NGINX_PORT=8081
STORAGE_DIR=/tmp/studymed
```

Repartir de `.env.example` si nécessaire.

Depuis un terminal sur la machine hôte (WSL2 ou macOS/Linux avec Docker installé, **hors devcontainer**), dans le dossier du repo :

**1. Créer l'arborescence :**

```bash
source .env.local_temp

mkdir -p "$STORAGE_DIR"/{data/{postgres,media,static},conf,import_init}
cp conf/nginx.conf "$STORAGE_DIR/conf/"
```

**2. Builder l'image depuis le code local :**

```bash
docker build -t ghcr.io/camille626/entrainement-medecine:latest .
```

**3. Démarrer la stack :**

```bash
docker compose --env-file .env.local_temp up -d
docker compose --env-file .env.local_temp ps
curl -I http://localhost:$NGINX_PORT/   # doit répondre 302 vers /login/
```

**4. Tester `import_fixture` :**

```bash
cp fixture.json media.zip "$STORAGE_DIR/import_init/"

docker compose --env-file .env.local_temp exec web python manage.py import_fixture \
  --fixture /app/import_init/fixture.json \
  --media-zip /app/import_init/media.zip

# Vérifier l'arborescence : question_images/ doit être direct sous media/
ls "$STORAGE_DIR/data/media/"
# Attendu : certificates/  profile_photos/  question_images/
# Pas de sous-dossier media/ intermédiaire
```

**5. Nettoyage :**

```bash
docker compose --env-file .env.local_temp down

if [[ -n "$STORAGE_DIR" && "$STORAGE_DIR" == /tmp/* ]]; then
  docker run --rm -v /tmp:/host_tmp alpine rm -rf "/host_tmp/$(basename "$STORAGE_DIR")"
else
  echo "STORAGE_DIR non défini ou hors /tmp ($STORAGE_DIR) — suppression annulée." >&2
fi
```

## 4. Configurer le reverse-proxy DSM

**Panneau de configuration** > **Portail de connexion** > **Avancé** > **Reverse Proxy** > **Créer** :

- Source : `studymed.ascot63.synology.me`, HTTPS, port 443
- Destination : `localhost`, HTTP, port `9666` (le `NGINX_PORT` choisi à l'étape 3)

**Ajouter un en-tête personnalisé** (onglet "En-tête personnalisé" de la règle) : `X-Forwarded-Proto: https`. Le conteneur `nginx` du stack relaie cet en-tête vers Django (au lieu de le forcer en dur, ce qui casserait les tests en HTTP direct — voir [Note de sécurité](#note-de-securite)) ; sans cet en-tête envoyé par DSM, Django croira que la connexion est en HTTP même derrière le HTTPS de DSM.

![alt text](img/custom-header.png)

Vérifier aussi dans **Panneau de configuration** > **Sécurité** > **Certificat** que `studymed.ascot63.synology.me` a un certificat HTTPS valide associé.

## 5. Initialiser l'application

Peupler la base Postgres vierge avec les données existantes (cas du dev local sur SQLite, `db.sqlite3`), via une commande dédiée (`import_fixture`) qui charge un fixture JSON Django et extrait une archive zip de fichiers médias — pas de copie binaire du fichier SQLite (les formats sont incompatibles avec Postgres), et pas besoin de SSH pour transférer les fichiers (juste **File Station**).

1. **Localement**, exporter les données et zipper les médias :

   ```bash
   uv run --active python manage.py dumpdata qcm auth --output=fixture.json
   (cd media && zip -r ../media.zip .)
   ```

   > **Important** : ne pas utiliser `zip -r media.zip media/` (depuis la racine du
   > projet) — cette forme inclut `media/` dans les chemins de l'archive
   > (`media/question_images/foo.jpg`), ce qui provoque une double arborescence
   > `media/media/question_images/` sur le NAS après extraction. La commande
   > `(cd media && zip -r ../media.zip .)` produit des chemins directs
   > (`question_images/foo.jpg`) correctement extraits dans `MEDIA_ROOT`.

2. **Via File Station**, glisser-déposer `fixture.json` et `media.zip` dans `${STORAGE_DIR}/import_init/` — déjà créé à l'étape 2, donc pas de souci de permissions pour l'upload.

3. **Entrer dans le conteneur `web`** via Portainer (sans SSH) : Containers > conteneur `web` > **Console** (choisir `/bin/bash`, **Connect**).

   Puis, dans le shell du conteneur :

   ```bash
   python manage.py import_fixture \
     --fixture /app/import_init/fixture.json \
     --media-zip /app/import_init/media.zip
   ```

   C'est la seule action liée à Docker nécessaire pour cette étape côté NAS.

À ne lancer qu'une fois sur une base Postgres vierge (juste après `migrate`, avant toute utilisation) — `loaddata` ne gère pas les conflits si des données existent déjà avec les mêmes clés primaires.

4. **Nettoyer** `import_init/` après coup via File Station (pas indispensable : la commande n'est jamais relancée automatiquement, mais évite de laisser un export de données sensibles trainer sur le NAS).

### Dépannage : `import_init` déjà créé en root

Si le stack a déjà tourné avant que `import_init/` n'existe (cas vécu pendant les tests de cette session), Docker l'a créé en root — ni File Station ni un `cp` côté host ne peuvent plus y écrire. Rattrapage ponctuel via un conteneur jetable (root), en remplaçant les chemins source par ceux de `fixture.json`/`media.zip` :

```bash
docker run --rm \
  -v "$(pwd)/fixture.json":/src/fixture.json:ro \
  -v "$(pwd)/media.zip":/src/media.zip:ro \
  -v "$STORAGE_DIR/import_init":/target \
  alpine sh -c "cp /src/fixture.json /src/media.zip /target/"
```

Pour éviter de refaire ce rattrapage à chaque fois, supprimer le dossier root-owned et le recréer soi-même avant le prochain démarrage du stack (même conteneur jetable pour la suppression, voir [Nettoyage après test](#3-creer-le-stack-sous-lhote-dans-tmp-pour-tester) plus haut pour le pattern).

### Dépannage : `PermissionError` sur `staticfiles` ou `media`

Logs du conteneur `web` du type :

```
PermissionError: [Errno 13] Permission denied: '/app/staticfiles/admin'
```

`entrypoint.sh` fait un `chown -R app:app` sur `data/media`/`data/static` avant de lancer `collectstatic`, mais sur un NAS Synology ce `chown` peut réussir (pas d'erreur) sans avoir d'effet réel : les ACL Windows/NFSv4 que DSM applique par défaut aux dossiers partagés prévalent sur le `chown` Unix classique fait depuis un conteneur. Vérifiable via File Station > `data/static` (ou `media`) > Propriétés > onglet **General** : si le **Propriétaire** affiché est ton compte DSM (ex: `administrateur`) plutôt qu'un utilisateur système, c'est confirmé.

Correctif : File Station > `data/media/` et `data/static/` > **Propriétés** > **Permission** > ajouter le groupe **"Tout le monde"** avec accès **Lecture/Écriture**, puis redémarrer le conteneur `web`.

## 6. Tester

`https://studymed.ascot63.synology.me` doit afficher l'application, et la connexion/inscription doit fonctionner sans erreur CSRF.

## Mises à jour ultérieures

1. Un push sur `main` republie automatiquement l'image `latest` sur ghcr.io.
2. Dans Portainer : **Stacks** > `studymed` > **Pull and redeploy** (ou re-déployer le stack) pour récupérer la nouvelle image et redémarrer les conteneurs.

Les migrations et le `collectstatic` sont rejoués automatiquement par `entrypoint.sh` à chaque redémarrage du conteneur `web`.

## Sauvegarde de la base de données

```bash
docker compose exec db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
```

`${STORAGE_DIR}/data/postgres/` étant un dossier normal sur le NAS, il peut aussi être sauvegardé directement (Hyper Backup, snapshot du volume...) en plus des dumps SQL réguliers.

## Note de sécurité

`NGINX_PORT` (ex: `9666`) **ne doit jamais être exposé directement sur Internet** (pas de redirection de port sur la box/routeur vers ce port) — seul le port 443 du reverse-proxy DSM doit être accessible depuis l'extérieur. Le conteneur `nginx` relaie tel quel le `X-Forwarded-Proto` reçu de son appelant (DSM en prod) sans le forcer en dur, pour ne pas casser les tests en HTTP direct (sinon Django croit la connexion HTTPS alors que le `Referer` du navigateur est en `http://`, et rejette le CSRF). Si ce port était exposé directement, n'importe qui pourrait usurper une connexion "sécurisée" auprès de Django en envoyant lui-même cet en-tête.

## Référence : architecture des conteneurs

```
nginx (reverse-proxy interne, port ${NGINX_PORT:-8080})
  ├── config : bind-mount ${STORAGE_DIR}/conf/nginx.conf
  ├── sert /static/ et /media/ directement (bind-mounts ${STORAGE_DIR}/data/static, ${STORAGE_DIR}/data/media)
  └── proxy_pass tout le reste vers web:8000
web (gunicorn + Django, image ghcr.io/camille626/entrainement-medecine:latest)
db (postgres:17-alpine, bind-mount ${STORAGE_DIR}/data/postgres)
```

`STORAGE_DIR` vaut `.` par défaut (donc `./data/...` et `./conf/nginx.conf`, relatifs au repo — pratique en local) ; en valeur absolue (ex: `/volume1/docker/studymed`) pour un déploiement Portainer, où il faut que les données **et** la config nginx survivent à une éventuelle suppression/recréation du stack (voir [Vue d'ensemble](#vue-densemble) pour le détail).

Le `Dockerfile` est multi-stage :

- stage `builder` : installe les dépendances avec `uv sync --frozen --no-dev`
- stage `runtime` : copie l'environnement virtuel et le code depuis `builder`, tourne avec un utilisateur non-root

Au démarrage du conteneur `web`, `entrypoint.sh` exécute `migrate --noinput` puis `collectstatic --noinput` avant de lancer la commande passée (`gunicorn` par défaut).

`docker-compose.yml` ne déclare que `image:` (pas de `build:`) sur le service `web` : `docker compose up`/Portainer pull systématiquement depuis ghcr.io, jamais de build sur le NAS. Pour tester une modification de code en local avant qu'elle soit publiée par la CI, builder et tagger l'image manuellement avant `docker compose up` :

```bash
docker build -t ghcr.io/camille626/entrainement-medecine:latest .
docker compose up -d
```

## Référence : variables d'environnement

| Variable                                              | Rôle                                                                                                                              |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `DJANGO_SECRET_KEY`                                   | Clé secrète Django (à générer, ne jamais committer)                                                                               |
| `DJANGO_DEBUG`                                        | `False` en production                                                                                                             |
| `DJANGO_ALLOWED_HOSTS`                                | Liste des hôtes autorisés, séparés par des virgules                                                                               |
| `DJANGO_CSRF_TRUSTED_ORIGINS`                         | Origines autorisées pour les requêtes POST, avec le schéma (ex: `https://studymed.ascot63.synology.me`)                           |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | Identifiants de la base PostgreSQL                                                                                                |
| `NGINX_PORT`                                          | Port interne sur lequel nginx écoute (mappé par docker-compose, défaut `8080`)                                                    |
| `STORAGE_DIR`                                         | Dossier de base des données persistantes et de la config nginx (défaut `.`, relatif — à fixer en absolu pour Portainer, ex: `/volume1/docker/studymed`) |

Le `DATABASE_URL` utilisé par le service `web` est construit automatiquement dans `docker-compose.yml` à partir des variables `POSTGRES_*` (pas besoin de le dupliquer dans `.env`).
