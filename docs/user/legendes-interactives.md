# Légendes interactives

Les questions de type **légende interactive** présentent une image anatomique (schéma, coupe…) sur laquelle l'utilisateur doit nommer chaque structure marquée.

## Comment répondre

1. Créez ou rejoignez une session en cochant **"Inclure les légendes interactives"** dans la page de configuration.
2. Sur la question, une image s'affiche avec de petits repères positionnés sur chaque zone à légender.
3. Cliquez sur un repère : un champ de saisie s'ouvre. Tapez le nom de la structure.
4. En passant au champ suivant (Tab ou clic ailleurs), le champ rempli se rétracte en **petite étiquette bleue** affichant votre réponse — il ne masque plus les zones voisines du schéma. Cliquez sur l'étiquette pour la rouvrir et modifier votre réponse avant la soumission.
5. Remplissez toutes les zones puis cliquez **Vérifier**.

## Saisie libre (style QROC)

La saisie est libre et **insensible à la casse et aux accents** : "Sclerotique", "sclérotique" et "SCLÉROTIQUE" sont toutes acceptées si la réponse attendue est "sclérotique".

## Correction

Après soumission, **l'image reste affichée** avec les réponses positionnées sur le schéma :

- Étiquette **verte** : réponse correcte
- Étiquette **rouge** : réponse incorrecte — survolez l'étiquette pour afficher la bonne réponse attendue et les alternatives acceptées

Le score est proportionnel au nombre de zones correctement légendées (ex: 8/10 → 0,80 point).

## Signaler une erreur

Sur l'écran de correction, le bouton **Signaler une erreur** propose 4 types de signalement adaptés aux légendes interactives :

- **Image manquante** : l'image de fond ne s'affiche pas.
- **Erreur de tag** : la question est mal classée (mêmes tags EC/chapitre que pour les autres types de question).
- **Une de mes réponses est correcte** : votre réponse a été marquée fausse à tort. Sélectionnez ce type puis **cliquez directement sur la zone concernée dans l'image**, qui reste affichée et interactive pendant la sélection. La réponse que vous aviez saisie est pré-remplie et modifiable avant l'envoi. Si l'administrateur accepte votre signalement, votre réponse est ajoutée aux variantes acceptées pour cette zone.
- **Autre** : tout autre problème avec une description libre.

## Pour les administrateurs : créer ou modifier une question légende

Depuis `/admin-site/questions/`, le bouton **+ Nouvelle question légende** ouvre le formulaire
d'ajout avec le type « Légende interactive » présélectionné. La fiche d'une question existante
(`/admin-site/questions/<id>/modifier/`) permet de la modifier de la même façon, y compris les
questions importées depuis Moodle.

Dans la section **Légende interactive** du formulaire :

1. **Image de fond** : sélectionnez un fichier image. Il remplace systématiquement l'image
   précédente (une question légende n'a jamais qu'une seule image de fond).
2. **Zones** : cliquez sur l'image à l'endroit où placer une zone — un repère bleu apparaît, avec
   une ligne de formulaire correspondante en dessous. Pour repositionner une zone, glissez son
   repère sur l'image ; vous pouvez aussi saisir les coordonnées X/Y directement dans les champs
   correspondants.
3. **Réponses acceptées** : pour chaque zone, indiquez le **label attendu** (réponse principale)
   et, si besoin, des **alternatives** séparées par un point-virgule (`;`) — par exemple
   `sclere; sclerotic` en plus du label principal `sclérotique`. N'importe laquelle de ces
   réponses sera acceptée comme correcte par l'étudiant, en plus d'être déjà insensible à la
   casse et aux accents.
4. **Étiquettes** : une liste de labels éditable (ajout/suppression), à titre informatif.

Le bouton **🗑 Supprimer la question** (disponible aussi sur la fiche de modification) supprime
la question avec confirmation.
