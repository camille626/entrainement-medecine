# Fusion de tags EC par cours — commande `merge_tags` (Issue #108)

## Contexte

Le tag EC "semio" (dupliqué en amont dans l'import Moodle) était partagé par 6
cours à la fois, alors que 3 d'entre eux disposaient déjà d'un tag EC plus
spécifique ("semio neuro", "semio respi", "semio cardio"). Le cours "système
cardiovasculaire" avait en plus un tag "radio" mal catégorisé (EC au lieu de
chapitre) et un tag "physio" hors-sujet sur 9 questions. Aucun outil de fusion
de tags n'existait dans le projet.

## Point technique clé

`Tag.name` est **unique en base** (`qcm/models.py:89`) : un tag comme "semio"
est un seul objet partagé par tous les cours qui l'utilisent. Toute fusion doit
donc se faire au niveau des `Question.tags` (M2M), filtrée par cours — jamais
en renommant/supprimant le `Tag` globalement.

Les `TagCategory` (`qcm/models.py:58`) sont globales et non dupliquées par
cours : il n'en existe que 3 en base, `course=None` pour toutes — id=1 "Année"
(annee), id=2 "EC" (souscategorie), id=3 "Chapitre" (chapitre). C'est cette
`TagCategory` id=3 qui est réutilisée pour convertir un tag EC en tag chapitre.

## Ce qui a été fait

### Nouvelle commande `qcm/management/commands/merge_tags.py`

Interface : `manage.py merge_tags <action> --course "<nom>" [options] [--dry-run]`
avec `action ∈ {merge, convert-to-chapter, remove}` (positionnel, `choices=`).

- **`merge`** (`--from-tag`, `--to-tag`) : pour les `Question` du cours ciblé
  ayant `from-tag`, ajoute `to-tag` et retire `from-tag`. Reparente aussi
  génériquement (pas de nom de tag câblé en dur) les tags-chapitres scopés à ce
  cours dont `parent_ec == from_tag` vers `to_tag`
  (`Tag.objects.filter(course=, parent_ec=from_tag).update(parent_ec=to_tag)`).
- **`convert-to-chapter`** (`--tag`, `--parent-ec`) : bascule `tag.category`
  vers la `TagCategory` globale de type chapitre, fixe `tag.parent_ec` et
  `tag.course`, puis ajoute `parent-ec` aux questions du cours taguées `tag`
  (un tag chapitre coexiste toujours avec son EC parent sur les questions,
  vérifié empiriquement : les 32 questions taguées "ECG" avaient déjà "semio").
  Erreur si `parent-ec` n'est pas un tag EC (`category.tag_type != SOUSCATEGORIE`).
- **`remove`** (`--tag`) : retire le tag du M2M des questions du cours ciblé
  uniquement, sans jamais supprimer le `Tag` global ni toucher aux autres cours.

Résolution du cours (`_resolve_course`) : égalité exacte d'abord, sinon
`icontains` avec `CommandError` si 0 ou >1 résultat. Nécessaire car
`Course.name` de "appareil respiratoire" a un **espace final en DB**
(`'P2 - appareil respiratoire '`).

`--dry-run` retourne avant toute écriture. Mutations sous `transaction.atomic()`.
Toutes les actions sont idempotentes par construction (un 2e run ne trouve plus
rien à modifier).

### Tests `tests/test_merge_tags_command.py` (29 tests)

Classes `TestMergeAction`, `TestConvertToChapterAction`, `TestRemoveAction`,
`TestCourseResolution`, `TestInvalidAction`. Fixtures locales (pas de
factory_boy), style `tests/test_tags.py`. Invocation via
`call_command("merge_tags", action, course=..., ...)`.

### Documentation `CLAUDE.md`

Ajout des 5 invocations exactes dans la section "Commandes Django".

### Exécution réelle sur `db.sqlite3` (local, non versionné)

Après vérification `--dry-run` (comptages exacts : 41/22/324/15/9 questions),
sauvegarde `db.sqlite3.bak` puis exécution réelle des 5 commandes. Résultat
vérifié par requêtes shell Django : `semio neuro` 179+41=220, `semio respi`
26+22=48, `semio cardio` 92+324=416, `radio` toujours 15 questions mais
`category=Chapitre, parent_ec=semio cardio, course=cardio`, `physio` disparu
des 9 questions cardio mais conservé dans locomoteur/respi/digestif (270
questions), tag `semio` disparu de neuro/respi/cardio mais conservé dans
reins/digestif/locomoteur (713 questions).

Cette exécution locale ne modifie aucun fichier versionné (DB gitignorée) — la
doc CLAUDE.md permet de rejouer les mêmes commandes en prod/NAS séparément.

## Décisions techniques

- CLI à action positionnelle + validation manuelle des options requises par
  action (dict `REQUIRED_OPTIONS`), plutôt que des `argparse` subparsers —
  cohérent avec le reste du projet qui n'utilise pas de subparsers, et plus
  simple à tester avec `call_command(**kwargs)`.
- Le reparenting des tags-chapitres dans `merge` est un effet de bord générique
  de l'action (basé sur une requête `filter(course=, parent_ec=from_tag)`), pas
  un cas spécial câblé pour cardio/neuro — réutilisable pour de futures fusions.
- `_resolve_course`/`_resolve_tag` retournent l'objet directement (`.get()`)
  plutôt que `.first()` pour éviter des `Optional` non gérés par mypy.
