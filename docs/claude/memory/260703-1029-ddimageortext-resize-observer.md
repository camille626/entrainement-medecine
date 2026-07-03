# Issue #91 — Bug zones de dépôt ddimageortext : ResizeObserver

**Date** : 2026-07-03
**Branche** : `91-bug-légendes-interactives-les-zones-de-dépôt-ne-suivent-pas-le-redimensionnement-de-limage`

## Problème

Les zones de dépôt (boîtes numérotées) des questions ddimageortext se décalaient par rapport
à l'image quand la largeur disponible changeait sans resize de fenêtre :
- Toggle du panneau de navigation (col-md-7 → col-md-10)
- Viewport plus petit que la taille naturelle de l'image Moodle

## Cause racine

`_ddimageortext_question.html` utilisait `window.addEventListener('resize', ...)` pour
rescaler les zones. Or le toggle du panneau de navigation change le layout CSS sans déclencher
d'événement `resize` sur la fenêtre.

**La fonction `ddiScaleZones(img)` existait déjà et était correcte** — seul le déclencheur
était inadapté.

## Fix

Fichier : `qcm/templates/qcm/_ddimageortext_question.html`

Remplacement du listener `window.resize` par un `ResizeObserver` sur l'image elle-même :

```js
// Avant
window.addEventListener('resize', function() {
  var img = document.getElementById('ddi-img');
  if (img && img.complete) ddiScaleZones(img);
});

// Après
var _ddiImg = document.getElementById('ddi-img');
if (_ddiImg) {
  new ResizeObserver(function() {
    if (_ddiImg.complete) ddiScaleZones(_ddiImg);
  }).observe(_ddiImg);
}
```

`ResizeObserver` se déclenche dès que la taille de l'élément observé change, quelle qu'en
soit la cause (window resize, layout change, flex/grid reflow). Supporté par tous les
navigateurs modernes depuis 2020 (Chrome 64+, Firefox 69+, Safari 13.1+).

## Pattern générique à retenir

**`window.addEventListener('resize')` ne suffit pas** pour les cas où la taille d'un élément
change sans resize de la fenêtre (ex: sidebar toggle, panel collapse, grid column change).
Utiliser `ResizeObserver` sur l'élément cible à la place.

La même logique `ddiResultScale` dans `_correction.html` utilisait aussi `window.resize` —
elle bénéficiera du même correctif si nécessaire.

## Test ajouté

Dans `tests/test_ddimageortext.py`, classe `TestDDIQuestionZoneScaling` :

```python
def test_question_view_uses_resize_observer(self, ...):
    """La page question ddimageortext utilise ResizeObserver pour rescaler les zones."""
    assert b"ResizeObserver" in response.content
```

GET `/entrainement/session/<pk>/` avec une question ddimageortext + bg_image.
