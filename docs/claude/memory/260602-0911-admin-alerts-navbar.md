# Alertes admin en navbar — Issue #26

## Résumé

Badges de notification dans la navbar pour les administrateurs, indiquant le nombre d'éléments nécessitant une action.

---

## Implémentation

### `qcm/context_processors.py`

Le context processor `notifications` (déjà existant pour les notifs utilisateur) a été étendu pour injecter des compteurs admin :

- `admin_pending_erratas` : `Errata.objects.filter(status=Errata.PENDING).count()`
- `admin_pending_registrations` : `RegistrationRequest.objects.filter(status=RegistrationRequest.PENDING).count()`
- `admin_alert_count` : somme des deux

Ces variables ne sont calculées que pour `request.user.is_staff` (guard explicite). Pour les non-staff, les trois valeurs retournent `0` sans requête DB.

### `qcm/templates/qcm/base.html`

Deux badges `<span class="admin-alert-badge">` ajoutés (staff only) :
- Sur l'onglet **Erratas** : affiche `admin_pending_erratas` quand > 0
- Sur l'onglet **Admin** : affiche `admin_pending_registrations` quand > 0

**Styling du badge** — cercle parfait via CSS personnalisé dans le `<style>` du base.html :
```css
.admin-alert-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.1rem;
  height: 1.1rem;
  border-radius: 50%;        /* cercle parfait */
  background-color: #dc3545;
  color: #fff !important;    /* override cascade du nav-link */
  font-size: 0.6rem;
  font-weight: 700;
  vertical-align: middle;
  margin-left: 3px;
  line-height: 1;
}
```

**Piège** : la règle `.nav-tabs .nav-link { color: #495057 }` cascade jusqu'au contenu du badge et écrase la couleur de texte Bootstrap. Le `color: #fff !important` est nécessaire. Idem pour la classe Bootstrap `bg-danger` qui peut être insuffisante — on utilise `background-color` directement dans le CSS personnalisé.

**Ne pas utiliser** `badge rounded-pill` de Bootstrap ici : `rounded-pill` donne un ovale, pas un cercle. Il faut `border-radius: 50%` avec `width = height` pour un vrai cercle.

---

## Tests (`tests/test_admin_alerts.py`)

9 tests :
- Context processor : non-staff → 0, staff sans pending → 0, staff avec erratas pending, staff avec registrations pending, somme correcte, erratas acceptés non comptés
- Navbar HTML : badge présent pour staff avec pending, absent pour non-staff, absent quand rien en attente

Le test navbar vérifie `b"admin-alert-badge" in response.content` sur `GET /`.

**Point d'attention** : `RegistrationRequest` n'a pas de champ `study_year` mais `year` + `parcours`. Utiliser `year="PASS", parcours=""` dans les fixtures de test.

---

## Sources des compteurs

- Erratas : modèle `Errata` (issue #19), champ `status`, constante `Errata.PENDING = "pending"`
- Inscriptions : modèle `RegistrationRequest`, champ `status`, constante `RegistrationRequest.PENDING = "pending"`
- Messages (issue #22) : non encore implémenté, prévu pour être ajouté au context processor quand l'issue #22 sera faite
