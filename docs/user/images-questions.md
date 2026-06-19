# Images dans les questions

Certaines questions contiennent des schémas anatomiques, des coupes histologiques ou des radios.
Ces images doivent être uploadées par un administrateur pour être visibles dans les énoncés.

## Pour les étudiants

Quand une image n'a pas encore été uploadée, un badge **⚠ Image non disponible** s'affiche à la
place. Si vous voyez ce badge, vous pouvez signaler le problème via le bouton **Signaler une erreur**
en bas de la question, en choisissant le type **Image manquante**.

## Pour les administrateurs

### Uploader une image depuis la liste des erratas

1. Aller sur `/errata/` et filtrer par type **Image manquante** et statut **En attente**
2. Ouvrir l'errata concerné
3. Renseigner le **nom du fichier Moodle** (pré-rempli automatiquement si détectable)
4. Sélectionner le **fichier image** depuis votre ordinateur
5. Cliquer **Uploader et accepter le signalement**

L'image est immédiatement visible dans l'énoncé de la question.

### Uploader une image depuis le formulaire question

Lors de la création ou modification d'une question (`/admin-site/questions/`) :

- La section **Images** permet d'uploader un fichier (non obligatoire)
- Une prévisualisation s'affiche dès la sélection du fichier
- En mode édition, les images existantes sont listées avec une option de suppression

Pour les questions de type **Légende interactive** (ddimageortext), l'image de fond se gère dans la
section dédiée **Légende interactive** du formulaire, pas dans la section **Images** générique
(masquée pour ce type de question). Voir la documentation développeur pour le détail du
positionnement des zones.

### Détecter les images manquantes

```bash
uv run --active python manage.py find_missing_images
```

Liste toutes les questions avec des références `@@PLUGINFILE@@` non encore résolues.

### Créer les erratas en lot

```bash
# Prévisualiser
uv run --active python manage.py seed_image_erratas --dry-run

# Créer
uv run --active python manage.py seed_image_erratas
```

Crée automatiquement un errata **Image manquante** pour chaque question contenant une image cassée.
La commande est idempotente : elle ne duplique pas les erratas existants.
