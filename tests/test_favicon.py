"""Tests pour le favicon (issue #77)."""

from pathlib import Path

import pytest
from django.contrib.auth.models import User


BASE_DIR = Path(__file__).resolve().parent.parent

# Pages d'authentification : <head> indépendant de base.html (pas de {% extends %}),
# donc le favicon doit y être ajouté séparément.
STANDALONE_AUTH_TEMPLATES = [
    "qcm/templates/registration/login.html",
    "qcm/templates/registration/inscription.html",
    "qcm/templates/registration/inscription_done.html",
    "qcm/templates/registration/password_reset_form.html",
    "qcm/templates/registration/password_reset_done.html",
    "qcm/templates/registration/password_reset_confirm.html",
    "qcm/templates/registration/password_reset_complete.html",
]


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="camille",
        password="pass",  # pragma: allowlist secret
    )


@pytest.mark.django_db
def test_base_html_includes_favicon_link(client, user):
    client.force_login(user)
    response = client.get("/")
    assert b'rel="icon"' in response.content
    assert b"favicon.svg" in response.content


@pytest.mark.parametrize("template_path", STANDALONE_AUTH_TEMPLATES)
def test_standalone_auth_templates_include_favicon_link(template_path):
    content = (BASE_DIR / template_path).read_text()
    assert 'rel="icon"' in content
    assert "favicon.svg" in content
