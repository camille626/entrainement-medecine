# Hiérarchie des cours : StudyYear → Semester → Course (Issue #6)

## Contexte

Ajout d'une organisation hiérarchique pour les cours afin de permettre la sélection par année/semestre dans l'interface d'entraînement (issue #5), et à terme de filtrer les cours par année d'étude de l'utilisateur.

## Ce qui a été fait

### Nouveaux modèles dans `qcm/models.py`

**`StudyYear`** — une année d'étude (P2, P3...)
- `name` (CharField max 20)
- `order` (IntegerField, pour le tri)
- `Meta.ordering = ["order"]`

**`Semester`** — un semestre dans une année
- `study_year` (FK → StudyYear, CASCADE, related_name="semesters")
- `name` (CharField max 20, ex: "S1", "S2")
- `order` (IntegerField)
- `__str__` : "P2 — S1"

**Modification de `Course`**
- Ajout de `semester` (FK → Semester, SET_NULL, null=True, blank=True, related_name="courses")

### Migrations

- `qcm/migrations/0003_add_studyyear_semester.py` — schéma : crée StudyYear, Semester, ajoute Course.semester
- `qcm/migrations/0004_init_p2_semesters.py` — data migration : crée P2/S1/S2 et tente d'assigner les cours existants

### Data migration (0004) — assignation P2

Les cours P2 sont définis par deux sets de moodle_ids dans `qcm/migrations/0004_init_p2_semesters.py` :
- `S1_MOODLE_IDS = {11, 12, 13, 14, 15, 16, 17, 18}` (cellule, neuro/psy, reins, tissu sanguin immuno, locomoteur, sémiologie générale, santé reproductive, langage/surdité)
- `S2_MOODLE_IDS = {19, 20, 21, 22, 23}` (cardiovasculaire, respiratoire, digestif, tissu sanguin sémiologie, anatomie radiologique)

**Important** : la data migration crée P2/S1/S2 dès `migrate`. L'assignation des cours se fait dans `import_moodle` (voir ci-dessous), pas dans la migration, car les cours n'existent pas encore en DB lors du premier `migrate`.

### `import_moodle` mis à jour

`qcm/management/commands/import_moodle.py` :
- Ajout de `S1_MOODLE_IDS` et `S2_MOODLE_IDS` constants
- Nouvelle méthode `_get_semester(moodle_id)` : retourne le Semester P2/S1 ou P2/S2 selon le moodle_id
- `_import_courses` : passe `semester=self._get_semester(moodle_id)` dans les `defaults` de `get_or_create`

### Admin

`qcm/admin.py` : ajout de `StudyYearAdmin` et `SemesterAdmin`.

### Tests (15 passent)

`tests/test_hierarchy.py` :
- `TestStudyYear` : création, __str__, ordering (utilise P4/P5 pour éviter conflit avec P2 de la data migration)
- `TestSemester` : création, __str__ "P2 — S1", ordering dans l'année
- `TestCourseHierarchy` : FK nullable, liaison FK, queryset via related_name
- `TestDataMigrationP2` : P2 existe, 2 semestres, S1 avant S2
- `TestCourseImportWithSemester` : cours S1 et S2 bien liés via FK

## Décisions techniques

- **Course.semester nullable** : les cours sans semestre sont possibles (compatibilité, années futures)
- **Data migration vs import** : la data migration crée seulement la structure (P2/S1/S2). L'assignation des cours se fait dans `import_moodle` lors de la création des cours. Si les cours existent déjà (import précédent), relancer `import_moodle` ne met pas à jour leur semestre (get_or_create ne touche pas les defaults si l'objet existe déjà) → prévoir un `update_or_create` ou commande manuelle si besoin.
- **Extensibilité P3+** : ajouter une nouvelle année ne casse rien. Il suffit d'une nouvelle data migration et d'étendre les COURSE_IDS dans import_moodle.

## Commandes utiles

```bash
# Appliquer les migrations (crée P2/S1/S2 automatiquement)
uv run --active python manage.py migrate

# Réimporter les cours avec assignation des semestres
uv run --active python manage.py import_moodle --dump data/raw/plateforme-medecine_moodlecloud.sql
```

## Point d'attention

`_import_courses` utilise `update_or_create` (pas `get_or_create`) pour mettre à jour le semestre même sur les cours déjà importés. Relancer `import_moodle` suffit pour propager les changements de semestre.
