# Navigateur de questions et tags en session — Issue #20

## Résumé

Deux améliorations UX pendant une session d'entraînement :
1. Panneau de navigation latéral (droit, collapsable) avec grille de questions colorées
2. Tags EC et chapitre affichés dans le panneau gauche à la place du bouton "Nouvelle session"

---

## `QuestionView` — changements majeurs (`qcm/views.py`)

### Navigation directe via `?q=<ordre>`
`GET /entrainement/session/<pk>/?q=2` → affiche la question à l'ordre 2 (1-based).
Si `q` absent → comportement habituel (première question non répondue).

### `sq_list` (context)
Liste de dicts pour toutes les questions de la session :
```python
{"order": int, "question_id": int, "status": str, "is_current": bool}
```
Status : `not_answered` | `correct` | `partial` | `incorrect`
Calculé depuis `UserAnswer` en une seule requête (defaultdict pour éviter N+1).

### `ec_tags` / `chapter_tags`
Tags de la question courante filtrés par `category.tag_type` :
- EC : `tag_type == "souscategorie"`
- Chapitre : `tag_type == "chapitre"`

### `is_answered` + contexte de correction
Si on navigue vers une question déjà répondue :
- `is_answered = True`
- Contexte additionnel : `selected_ids`, `score`, `status`, `is_last`
- Template inclut `_correction.html` directement (pas de formulaire)

### `prev_order` / `next_order`
`current_sq.order - 1` et `current_sq.order + 1` (None si hors bornes).

---

## `CheckView` — ajout `prev_order`/`next_order`
Après le Check, `_correction.html` reçoit maintenant `prev_order` et `next_order` pour pouvoir afficher les boutons de navigation à l'intérieur du cadre bleu.

---

## `_correction.html` — navigation intégrée
Remplace le simple "Page suivante →" par :
- Bouton ← Précédente (si `prev_order`)
- Bouton Page suivante → (ou Voir les résultats si `is_last`)

Ceci évite le doublon avec les boutons externes, et place les boutons dans le cadre bleu (là où l'utilisateur regarde).

---

## `question.html` — template

### Layout 3 colonnes
`col-md-2` info | `col-md-7` question | `col-md-3` navigateur

### Navigateur (panneau droit)
- CSS custom `nav-q` : blocs `2.5rem × 1.7rem`, `border-radius: 4px`, pastel
- Couleurs : `#d1f0d8` (correct), `#fff3cd` (partial), `#fde8ea` (incorrect), `#f0f0f0` (non répondu)
- `color: #555 !important; text-decoration: none !important` pour override les couleurs de lien Bootstrap
- Numéro toujours affiché (pas de symbole)
- Classe `nav-q-current` = `outline: 2px solid #0d6efd`
- Bouton toggle : ✕ dans le panneau (avec `text-decoration: none` pour éviter le soulignement Bootstrap `btn-link`), et bouton flottant 🧭 `position-fixed` quand masqué

### Boutons prev/next externes
Uniquement affichés `{% if not is_answered %}` — pour les questions répondues, les boutons sont dans `_correction.html`.

### Bouton Check désactivé
`disabled` par défaut, activé via JS dès qu'une checkbox est cochée.
```javascript
document.querySelectorAll('input[name="answers"]').forEach(cb => {
  cb.addEventListener('change', () => {
    btn.disabled = !document.querySelector('input[name="answers"]:checked');
  });
});
```

---

## Points CSS Bootstrap à retenir

- `btn-link` ajoute `text-decoration: underline` → fix: `style="text-decoration:none;"`
- `<a>` hérite la couleur de lien bleue même avec des classes → fix: `color: #555 !important` dans CSS custom
- `col-md-X` toggle via `classList.replace('col-md-7', 'col-md-10')` (Bootstrap)
