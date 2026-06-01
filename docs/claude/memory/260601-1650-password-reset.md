# Réinitialisation de mot de passe (Issue #25)

## Contexte

Flux de reset mot de passe via email, utilisant les vues Django intégrées avec templates Bootstrap personnalisés.

## URLs ajoutées (`config/urls.py`)

- `password_reset/` → `PasswordResetView`
- `password_reset/done/` → `PasswordResetDoneView`
- `password_reset/confirm/<uidb64>/<token>/` → `PasswordResetConfirmView`
- `password_reset/complete/` → `PasswordResetCompleteView`

## Templates (`registration/`)

- `password_reset_form.html` — formulaire email
- `password_reset_done.html` — confirmation envoi
- `password_reset_confirm.html` — saisie nouveau mot de passe (gère `validlink`)
- `password_reset_complete.html` — succès
- `password_reset_subject.txt` — sujet email
- `password_reset_email.txt` — corps email texte avec lien

## Settings email (`config/settings.py`)

- `EMAIL_BACKEND` = console en dev (imprime dans le terminal), SMTP configurable via env en prod
- Variables env : `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`

## login.html

Lien "Mot de passe oublié ?" ajouté sous le bouton de connexion → `/password_reset/`

## Note dev

En développement, les emails s'affichent dans le terminal du serveur (pas envoyés réellement). En production, configurer les variables d'env SMTP.
