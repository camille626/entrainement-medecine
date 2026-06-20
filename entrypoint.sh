#!/bin/sh
set -e

# Les points de montage (media/staticfiles) peuvent être créés par Docker en root
# si le dossier hôte n'existe pas encore — on corrige ici avant de basculer vers
# l'utilisateur non-root, plutôt que de dépendre d'une permission préexistante
# sur le NAS.
mkdir -p /app/media /app/staticfiles
chown -R app:app /app/media /app/staticfiles

gosu app python manage.py migrate --noinput
gosu app python manage.py collectstatic --noinput

exec gosu app "$@"
