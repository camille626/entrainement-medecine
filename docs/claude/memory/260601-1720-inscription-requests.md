# Demandes d'inscription (Issue #14)

## Contexte

Workflow complet pour qu'un nouvel utilisateur demande l'accès à la plateforme, et que l'admin accepte/refuse depuis Django admin.

## Modèle `RegistrationRequest` (`qcm/models.py`)

- `first_name`, `last_name`, `email` (unique), `message` (blank), `created_at` (auto), `status` (pending/accepted/rejected)
- Status par défaut : `pending`

## URL publique `/inscription/`

- `InscriptionView` (GET/POST) — **sans** `LoginRequiredMixin` (publique)
- `InscriptionDoneView` — page de confirmation

## Formulaire `InscriptionForm` (`qcm/forms.py`)

- Valide l'unicité de l'email via `clean_email` (lève `ValidationError` si doublon)

## Admin Django (`qcm/admin.py`)

`RegistrationRequestAdmin` avec deux actions :

**`accept_requests`** :
1. Génère un mot de passe aléatoire (12 chars, `secrets.choice`)
2. Crée un `User` Django (username = partie locale de l'email, géré unique)
3. Envoie un email avec les credentials via `send_mail`
4. Passe `status → accepted`

**`reject_requests`** :
- Passe `status → rejected` via `.update()`

## `login.html`

Lien "Demander l'accès" pointe maintenant vers `/inscription/` (était `#`).

## Note

En production, le mot de passe provisoire est envoyé par email SMTP. En dev, il s'affiche dans la console. L'utilisateur doit changer son mot de passe après la première connexion (via `/password_reset/`).
