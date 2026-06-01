"""Tests pour la réinitialisation de mot de passe (issue #25)."""

import pytest
from django.contrib.auth.models import User
from django.core import mail


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="etudiant",
        email="etudiant@example.com",
        password="ancienmdp123",  # pragma: allowlist secret
    )


@pytest.mark.django_db
class TestPasswordResetPages:
    def test_reset_form_page_returns_200(self, client):
        response = client.get("/password_reset/")
        assert response.status_code == 200

    def test_reset_form_has_email_field(self, client):
        response = client.get("/password_reset/")
        assert b"email" in response.content.lower()

    def test_reset_done_page_returns_200(self, client):
        response = client.get("/password_reset/done/")
        assert response.status_code == 200

    def test_reset_complete_page_returns_200(self, client):
        response = client.get("/password_reset/complete/")
        assert response.status_code == 200


@pytest.mark.django_db
class TestPasswordResetFlow:
    def test_submit_valid_email_sends_email(self, client, user):
        client.post("/password_reset/", {"email": "etudiant@example.com"})
        assert len(mail.outbox) == 1
        assert "etudiant@example.com" in mail.outbox[0].to

    def test_submit_unknown_email_no_error(self, client):
        # Django ne révèle pas si l'email existe (sécurité)
        response = client.post("/password_reset/", {"email": "inconnu@example.com"})
        assert (
            response.status_code == 302
        )  # redirect vers done même si email inexistant

    def test_reset_email_contains_reset_link(self, client, user):
        client.post("/password_reset/", {"email": "etudiant@example.com"})
        assert len(mail.outbox) == 1
        assert "password_reset/confirm" in mail.outbox[0].body


@pytest.mark.django_db
class TestLoginPageHasForgotLink:
    def test_login_page_has_forgot_password_link(self, client):
        response = client.get("/login/")
        assert (
            b"password_reset" in response.content
            or b"oubli" in response.content.lower()
        )
