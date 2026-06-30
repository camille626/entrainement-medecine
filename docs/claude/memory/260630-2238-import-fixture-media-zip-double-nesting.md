# Bug : double nesting media/media/ dans import_fixture (issue #80)

## Contexte

Les images de fond des questions ddimageortext étaient invisibles sur le NAS
(déploiement Docker via Portainer). En dev local, tout fonctionnait.

## Cause racine

La commande documentée pour zipper les médias était `zip -r media.zip media/`,
lancée depuis la racine du projet. Cette commande crée une archive où **tous les
chemins contiennent un préfixe `media/`** :

- `media/question_images/oeil.png`
- `media/certificates/foo.pdf`

Quand `import_fixture --media-zip` faisait `archive.extractall(MEDIA_ROOT)`,
ça extrayait dans `MEDIA_ROOT/media/question_images/...` — double nesting.
Django et nginx cherchant les fichiers à `MEDIA_ROOT/question_images/...`,
l'image était introuvable.

`certificates/` et `profile_photos/` étaient au bon niveau sur le NAS car
créés directement par Django lors d'uploads utilisateurs (jamais via import_fixture).

## Correctif (branche 80-légendes-interactives...)

### 1. `qcm/management/commands/import_fixture.py`

Ajout de la fonction module-level `_zip_strip_prefix(members: list[str]) -> str`
qui détecte si tous les membres du zip partagent un dossier wrapper commun
(identifié par le fait qu'il contient lui-même des sous-répertoires) et retourne
ce préfixe à stripper.

`_extract_media_zip` remplace `archive.extractall(MEDIA_ROOT)` par une boucle
manuelle qui applique ce strip, crée les dossiers parents au besoin et écrit
chaque fichier individuellement.

**Heuristique** : strip uniquement si le top-level unique contient des
sous-répertoires (`has_subdirs`). Cela évite de stripper un dossier de contenu
direct comme `question_images/` (qui serait dans un zip correct ne contenant
qu'un seul sous-répertoire de type).

### 2. `docs/dev/deploiement-nas.md` (étape 5)

Correction de la commande zip :
- Avant : `zip -r media.zip media/`
- Après : `(cd media && zip -r ../media.zip .)`

Note explicative ajoutée pour expliquer pourquoi la forme `zip -r media.zip media/`
est incorrecte.

## Tests (`tests/test_import_fixture.py`)

- `test_extracts_media_zip_with_prefix` : zip avec préfixe `media/` → vérifie
  extraction correcte à `question_images/test.png`, et absence de `media/` imbriqué
- `TestZipStripPrefix` : 4 tests unitaires de `_zip_strip_prefix`
  (préfixe commun, plusieurs top-dirs, pas de préfixe, liste vide)

## Récupérer les données sur le NAS déjà affecté

Pour un NAS déjà déployé avec le double nesting, il faut soit :
- Re-lancer `import_fixture` avec le nouveau code (après redéploiement) avec
  le même `media.zip` → les fichiers seront correctement extraits
- Ou manuellement déplacer `data/media/media/question_images/` vers
  `data/media/question_images/` via File Station
