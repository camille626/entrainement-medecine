# Erratas IMAGE : suppression du bouton "Accepter" standalone (issue #61)

## Contexte

Dans la liste des erratas (`errata_list.html`), la section "Actions standard" (staff, pending) comporte un bloc conditionnel pour les boutons d'action. Pour les erratas de type IMAGE, deux boutons coexistaient :
1. Le formulaire d'upload avec "Uploader et accepter le signalement" (correct)
2. Le bouton générique "Accepter le signalement" du bloc `{% else %}` (en doublon, dangereux)

## Modification

`qcm/templates/qcm/errata_list.html` — une seule ligne changée :

```diff
- {% else %}
+ {% elif e.error_type != 'image' %}
```

Cela exclut le type IMAGE du bouton générique "Accepter le signalement". Les types tag/correction/points/qroc_answer conservent leur bouton inchangé.

## Pattern à retenir

La structure de conditions dans le bloc actions de `errata_list.html` est :
```
{% if e.error_type == 'tag' and e.suggested_tags.exists %}
  → bouton "Accepter la suggestion"
{% elif e.error_type != 'image' %}
  → bouton "Accepter le signalement" (générique)
{% endif %}
```

Pour IMAGE, seul le formulaire upload (au-dessus de ce bloc, conditionné `{% if e.error_type == 'image' %}`) est affiché.

## Tests

Dans `tests/test_erratas.py`, classe `TestErrataImageTemplate` :
- `test_no_standalone_accept_button_for_image` — vérifie l'absence de `action="/errata/{pk}/accept/"` pour IMAGE
- `test_upload_and_accept_button_present_for_image` — vérifie la présence de "Uploader et accepter le signalement"

Classe `TestErrataTagTemplate` :
- `test_accept_button_present_for_tag` — vérifie que les erratas TAG conservent leur bouton accept
