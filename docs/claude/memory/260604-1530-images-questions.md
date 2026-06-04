# Images dans les énoncés de questions (issue #29)

## Contexte

Les questions importées depuis Moodle contiennent des références d'images `@@PLUGINFILE@@/filename.png`
qui étaient rendues comme du texte cassé. 219 questions concernées au total (183 `@@PLUGINFILE@@`,
33 chemins relatifs, 2 base64 OK, 1 URL externe placeholder).

## Architecture mise en place

### Modèle `QuestionImage` (`qcm/models.py`)

```python
class QuestionImage(models.Model):
    question = ForeignKey(Question, related_name="images")
    moodle_filename = CharField(max_length=255)
    file = FileField(upload_to="question_images/")
    class Meta:
        unique_together = [("question", "moodle_filename")]
```

- Pas de `ImageField` (évite la dépendance Pillow) — `FileField` suffit car upload staff uniquement
- `unique_together` sur `(question, moodle_filename)` : deux questions peuvent avoir `image.png` mais pas la même question deux fois

### Méthode `Question.render_text()` (`qcm/models.py`)

- Regex `_PLUGINFILE_IMG_RE` compilée au niveau module pour performance
- Remplace `<img src="@@PLUGINFILE@@/filename">` par l'URL locale si uploadée
- Sinon badge placeholder `⚠ Image non disponible`
- **Utilisée dans les templates à la place de `{{ question.text|safe }}`** : `question.html` et `errata_list.html`

### Templatetag `pluginfile_names` (`qcm/templatetags/qcm_extras.py`)

- Filtre Django qui extrait les noms de fichiers `@@PLUGINFILE@@/xxx` d'un texte
- Utilisé pour pré-remplir le champ `moodle_filename` dans les formulaires d'upload

### Vue `ErrataUploadImageView` (`qcm/views.py`)

- `POST /errata/<pk>/upload-image/`
- Staff uniquement (404 sinon)
- Crée ou remplace (`update_or_create`) le `QuestionImage`
- Accepte l'errata + notifie le reporter
- Registered dans `qcm/urls.py` sous `name="errata_upload_image"`

### Admin Django (`qcm/admin.py`)

- `QuestionImageInline` (TabularInline) ajouté à `QuestionAdmin`
- Permet upload direct depuis `/admin/qcm/question/<pk>/change/`

### Formulaire question admin-site (`qcm/templates/qcm/admin_site/question_form.html`)

- Section "Images" avec upload optionnel (fields `new_image_file` + `new_image_filename`)
- Preview JS avec `FileReader` + bouton "✕ Annuler" (`clearImagePreview()`)
- Affichage des images existantes avec case "Supprimer" en mode édition
- **Cours rendu obligatoire** (`required`) à la place de Catégorie visuellement
- Formulaire avec `enctype="multipart/form-data"`
- Vues `AdminQuestionAddView` et `AdminQuestionEditView` dans `qcm/views_admin.py` gèrent l'upload + suppression

### Management commands

- `find_missing_images` : liste les questions avec `@@PLUGINFILE@@` non résolus
- `seed_image_erratas` : crée les erratas IMAGE pour toutes les questions avec `<img>` cassé
  - Ignore base64 et URLs externes
  - Idempotent (ne duplique pas les erratas existants)
  - Option `--dry-run`, option `--reporter <username>`
  - **A été exécuté** : 216 erratas IMAGE créés sur la BDD de dev

### Conservation des filtres dans errata_list

- `ErrataListView` passe `back_params = request.GET.urlencode()` au template
- Chaque formulaire (accept/reject/upload/feedback) a `<input name="back" value="{{ back_params }}">`
- `_errata_list_redirect(request)` dans `qcm/views.py` reconstruit l'URL `/errata/?{back}`

## Migration

`qcm/migrations/0021_questionimage.py` — migration standard Django

## Tests

`tests/test_images.py` — 13 tests couvrant :
- Modèle `QuestionImage` (création, str, unique_together, multi-question)
- `render_text()` (texte sans image, image uploadée, placeholder, multi-images, attributs préservés)
- `ErrataUploadImageView` (upload + accept, 404 non-staff, redirect login, notification)

## Patterns à retenir

- Django renomme les fichiers uploadés avec un suffix aléatoire (`schema_ORBIMwz.png`) — ne pas tester le nom exact du fichier dans l'URL
- Pour l'auto-détection du filename dans les formulaires, utiliser le templatetag `pluginfile_names` sur `question.text`
- `update_or_create` pour l'upload permet de remplacer une image existante sans doublon
- La regex `_PLUGINFILE_IMG_RE` doit capturer les attributs avant et après `src` pour les préserver
