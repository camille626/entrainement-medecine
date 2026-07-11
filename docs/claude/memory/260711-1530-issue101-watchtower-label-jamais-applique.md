# Issue #101 — Watchtower ne met jamais à jour le site sur le NAS

## Contexte

Le site `studymed.ascot63.synology.me` n'était jamais mis à jour automatiquement après un
push sur `main`, alors que watchtower tourne bien sur le NAS et met à jour d'autres stacks
avec succès.

## Diagnostic (pas de bug de code)

`docker-compose.yml` sur `main` contient déjà le label
`com.centurylinklabs.watchtower.enable=true` sur le service `web` depuis l'issue #86, et
`test_compose_web_has_watchtower_label` (`tests/test_deployment.py`) le vérifie et passe.

Watchtower tourne dans un **stack Portainer séparé** (pas dans ce repo), configuré avec
`WATCHTOWER_LABEL_ENABLE=true` et `WATCHTOWER_POLL_INTERVAL=86400` (scan quotidien). Ses
logs confirmaient des mises à jour réussies sur d'autres stacks (transmission, firefox,
mongo, portainer-ce, upsnap, lyrionmusicserver) mais jamais sur `entrainement-medecine`.

**Cause racine** : le conteneur `studymed-web-1` réellement en cours d'exécution sur le NAS
(vérifié via `docker inspect studymed-web-1 --format '{{json .Config.Labels}}'`) ne portait
**que** des labels internes `com.docker.compose.*` — pas le label watchtower. Un label
Docker ne prend effet qu'à la **création** du conteneur ; ce conteneur avait été créé le
2026-07-01 et n'a jamais été recréé depuis (le restart du 07-07 correspond à un reboot NAS,
qui redémarre le même conteneur sans le recréer). Portainer (stack Git) ne redéploie jamais
automatiquement suite à un simple push sur `main` — il faut une action explicite
("Pull and redeploy" / "Update the stack") pour que les conteneurs soient recréés avec la
config à jour.

## Méthode de diagnostic à retenir

Pour tout "ça semble bien configuré mais ça ne marche pas" impliquant des labels/env Docker
sur le NAS : toujours vérifier l'état du **conteneur vivant** via `docker inspect`, pas
seulement le fichier source du repo — un changement dans `docker-compose.yml` ne s'applique
qu'après recréation explicite du conteneur (redéploiement Portainer), jamais automatiquement.

## Fix appliqué

Aucun changement de code. Documentation mise à jour dans
`docs/dev/deploiement-nas.md` :
- Vue d'ensemble : watchtower explicitement mentionné comme stack Portainer indépendant.
- Section "Mises à jour ultérieures" : distinction claire entre mise à jour du **contenu**
  de l'image (automatique via watchtower) et changement de **`docker-compose.yml` lui-même**
  (toujours besoin d'un redéploiement manuel unique).
- Nouvelle entrée de dépannage "mise à jour automatique jamais déclenchée malgré watchtower
  actif", avec la commande `docker inspect` de diagnostic et le correctif.

Action opérationnelle restante côté utilisateur (hors repo) : redéployer une fois le stack
`studymed` dans Portainer pour que le conteneur `web` récupère le label.

## Note complémentaire (hors périmètre du fix)

L'image `containrrr/watchtower:latest` utilisée sur le NAS est un projet archivé depuis
décembre 2025, figé en v1.7.1, sans plus de correctifs de sécurité. Le fork actif et
compatible en drop-in est `ghcr.io/nicholas-fedor/watchtower`. Migration non faite ici car
ce stack watchtower n'est pas géré par ce repo.
