"""Tests pour les demandes d'inscription (issue #14)."""

import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile

from qcm.models import RegistrationRequest


def _fake_pdf() -> SimpleUploadedFile:
    return SimpleUploadedFile(
        "certificat.pdf", b"%PDF-1.4 fake pdf content", content_type="application/pdf"
    )


@pytest.mark.django_db
class TestInscriptionPage:
    def test_inscription_page_accessible_without_login(self, client):
        response = client.get("/inscription/")
        assert response.status_code == 200

    def test_inscription_page_has_form_fields(self, client):
        response = client.get("/inscription/")
        assert (
            b"first_name" in response.content or b"prenom" in response.content.lower()
        )
        assert b"email" in response.content

    def test_valid_submission_creates_request(self, client):
        client.post(
            "/inscription/",
            {
                "first_name": "Camille",
                "last_name": "Martin",
                "email": "camille@example.com",
                "year": "P2",
                "parcours": "PASS",
                "certificate": _fake_pdf(),
            },
        )
        assert RegistrationRequest.objects.filter(email="camille@example.com").exists()
        req = RegistrationRequest.objects.get(email="camille@example.com")
        assert req.status == "pending"
        assert req.year == "P2"
        assert req.certificate  # file was uploaded

    def test_valid_submission_redirects(self, client):
        response = client.post(
            "/inscription/",
            {
                "first_name": "Camille",
                "last_name": "Martin",
                "email": "camille@example.com",
                "year": "D1",
                "certificate": _fake_pdf(),
            },
        )
        assert response.status_code == 302

    def test_duplicate_email_shows_error(self, client, db):
        RegistrationRequest.objects.create(
            first_name="Camille",
            last_name="Martin",
            email="camille@example.com",
            message="P2 ex-LAS",
            status="pending",
        )
        response = client.post(
            "/inscription/",
            {
                "first_name": "Autre",
                "last_name": "Personne",
                "email": "camille@example.com",
                "message": "P2 ex-PASS",
                "certificate": _fake_pdf(),
            },
        )
        assert response.status_code == 200  # reste sur la page avec erreur
        assert (
            RegistrationRequest.objects.filter(email="camille@example.com").count() == 1
        )


@pytest.mark.django_db
class TestRegistrationRequestModel:
    def test_create_request(self, db):
        req = RegistrationRequest.objects.create(
            first_name="Alice",
            last_name="Dupont",
            email="alice@example.com",
            message="P2 ex-LAS",
        )
        assert req.pk is not None
        assert req.status == "pending"
        assert req.created_at is not None

    def test_str(self, db):
        req = RegistrationRequest.objects.create(
            first_name="Alice",
            last_name="Dupont",
            email="alice@example.com",
            message="P2 ex-LAS",
        )
        assert "alice@example.com" in str(req) or "Alice" in str(req)


@pytest.mark.django_db
class TestAdminActions:
    @pytest.fixture
    def admin_user(self, db):
        return User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass",  # pragma: allowlist secret
        )

    @pytest.fixture
    def pending_request(self, db):
        return RegistrationRequest.objects.create(
            first_name="Bob",
            last_name="Durand",
            email="bob@example.com",
            message="P2 ex-PASS",
            status="pending",
        )

    def test_accept_creates_user(self, client, admin_user, pending_request):
        client.force_login(admin_user)
        client.post(
            "/admin/qcm/registrationrequest/",
            {
                "action": "accept_requests",
                "_selected_action": [pending_request.pk],
            },
        )
        assert User.objects.filter(email="bob@example.com").exists()
        pending_request.refresh_from_db()
        assert pending_request.status == "accepted"

    def test_accept_sends_email(self, client, admin_user, pending_request):
        client.force_login(admin_user)
        client.post(
            "/admin/qcm/registrationrequest/",
            {
                "action": "accept_requests",
                "_selected_action": [pending_request.pk],
            },
        )
        assert len(mail.outbox) >= 1
        assert any("bob@example.com" in m.to for m in mail.outbox)

    def test_reject_updates_status(self, client, admin_user, pending_request):
        client.force_login(admin_user)
        client.post(
            "/admin/qcm/registrationrequest/",
            {
                "action": "reject_requests",
                "_selected_action": [pending_request.pk],
            },
        )
        pending_request.refresh_from_db()
        assert pending_request.status == "rejected"


@pytest.mark.django_db
class TestLoginPageLinkToInscription:
    def test_login_page_links_to_inscription(self, client):
        response = client.get("/login/")
        assert (
            b"/inscription/" in response.content
            or b"inscription" in response.content.lower()
        )
