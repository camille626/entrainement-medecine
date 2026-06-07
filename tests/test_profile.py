"""Tests pour la page profil utilisateur (issue #17)."""

import io

import pytest
from django.contrib.auth.models import User
from PIL import Image

from qcm.models import RegistrationRequest, UserProfile


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="etudiant",
        password="motdepasse123",  # pragma: allowlist secret
        first_name="Camille",
        last_name="Martin",
        email="camille@example.com",
    )


@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        username="autre",
        password="motdepasse456",  # pragma: allowlist secret
        email="autre@example.com",
    )


# ---------------------------------------------------------------------------
# Protection des routes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestProfileRouteProtection:
    def test_profile_requires_login(self, client):
        response = client.get("/profil/")
        assert response.status_code == 302
        assert "/login/" in response["Location"]

    def test_password_change_requires_login(self, client):
        response = client.get("/profil/mot-de-passe/")
        assert response.status_code == 302
        assert "/login/" in response["Location"]


# ---------------------------------------------------------------------------
# GET — affichage du profil
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestProfileGet:
    def test_profile_returns_200(self, client, user):
        client.force_login(user)
        response = client.get("/profil/")
        assert response.status_code == 200

    def test_profile_prefills_first_name(self, client, user):
        client.force_login(user)
        response = client.get("/profil/")
        assert b"Camille" in response.content

    def test_profile_prefills_last_name(self, client, user):
        client.force_login(user)
        response = client.get("/profil/")
        assert b"Martin" in response.content

    def test_profile_prefills_email(self, client, user):
        client.force_login(user)
        response = client.get("/profil/")
        assert b"camille@example.com" in response.content

    def test_profile_shows_saved_banner_when_param(self, client, user):
        client.force_login(user)
        response = client.get("/profil/?saved=1")
        assert (
            b"succes" in response.content.lower()
            or b"enregistr" in response.content.lower()
        )

    def test_profile_no_banner_without_param(self, client, user):
        client.force_login(user)
        response = client.get("/profil/")
        # Sans param, pas de bandeau succès
        assert b"saved=1" not in response.content

    def test_profile_shows_year_if_registration_accepted(self, client, user):
        RegistrationRequest.objects.create(
            first_name="Camille",
            last_name="Martin",
            email="camille@example.com",
            year="P2",
            parcours="PASS",
            status=RegistrationRequest.ACCEPTED,
        )
        client.force_login(user)
        response = client.get("/profil/")
        assert b"P2" in response.content

    def test_profile_no_year_if_no_registration(self, client, user):
        client.force_login(user)
        response = client.get("/profil/")
        # Pas de RegistrationRequest → pas d'erreur (juste absence de la section)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST — mise à jour du profil
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestProfilePost:
    def test_post_updates_first_name(self, client, user):
        client.force_login(user)
        client.post(
            "/profil/",
            {
                "first_name": "Nouvelle",
                "last_name": "Martin",
                "email": "camille@example.com",
            },
        )
        user.refresh_from_db()
        assert user.first_name == "Nouvelle"

    def test_post_updates_last_name(self, client, user):
        client.force_login(user)
        client.post(
            "/profil/",
            {
                "first_name": "Camille",
                "last_name": "Dupont",
                "email": "camille@example.com",
            },
        )
        user.refresh_from_db()
        assert user.last_name == "Dupont"

    def test_post_updates_email(self, client, user):
        client.force_login(user)
        client.post(
            "/profil/",
            {
                "first_name": "Camille",
                "last_name": "Martin",
                "email": "new@example.com",
            },
        )
        user.refresh_from_db()
        assert user.email == "new@example.com"

    def test_post_valid_redirects_with_saved_param(self, client, user):
        client.force_login(user)
        response = client.post(
            "/profil/",
            {
                "first_name": "Camille",
                "last_name": "Martin",
                "email": "camille@example.com",
            },
        )
        assert response.status_code == 302
        assert "saved=1" in response["Location"]

    def test_post_duplicate_email_shows_error(self, client, user, other_user):
        client.force_login(user)
        response = client.post(
            "/profil/",
            {
                "first_name": "Camille",
                "last_name": "Martin",
                "email": other_user.email,  # email déjà pris
            },
        )
        assert response.status_code == 200
        user.refresh_from_db()
        assert user.email == "camille@example.com"  # inchangé

    def test_post_empty_email_shows_error(self, client, user):
        client.force_login(user)
        response = client.post(
            "/profil/",
            {
                "first_name": "Camille",
                "last_name": "Martin",
                "email": "",
            },
        )
        assert response.status_code == 200  # re-affiche le formulaire


# ---------------------------------------------------------------------------
# Changement de mot de passe
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestPasswordChange:
    def test_password_change_page_returns_200(self, client, user):
        client.force_login(user)
        response = client.get("/profil/mot-de-passe/")
        assert response.status_code == 200

    def test_password_change_link_in_profile(self, client, user):
        client.force_login(user)
        response = client.get("/profil/")
        assert b"mot-de-passe" in response.content


# ---------------------------------------------------------------------------
# Photo de profil
# ---------------------------------------------------------------------------


def _make_image_file(name="test.png", fmt="PNG"):
    """Génère une image PNG minimale en mémoire."""
    buf = io.BytesIO()
    img = Image.new("RGB", (10, 10), color=(255, 0, 0))
    img.save(buf, format=fmt)
    buf.seek(0)
    buf.name = name
    return buf


@pytest.mark.django_db
class TestProfilePhoto:
    def test_upload_photo_saves_to_profile(self, client, user, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        client.force_login(user)
        img = _make_image_file()
        client.post(
            "/profil/",
            {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "photo": img,
            },
        )
        profile = UserProfile.objects.get(user=user)
        assert bool(profile.photo)

    def test_photo_too_large_shows_error(self, client, user):
        client.force_login(user)
        # Crée un faux fichier de 3 Mo (> 2 Mo limite)
        large = io.BytesIO(b"x" * (3 * 1024 * 1024))
        large.name = "big.png"
        response = client.post(
            "/profil/",
            {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "photo": large,
            },
        )
        assert response.status_code == 200  # formulaire re-affiché

    def test_profile_shows_avatar_placeholder_when_no_photo(self, client, user):
        client.force_login(user)
        response = client.get("/profil/")
        # Vérifie qu'un avatar de substitution est présent (initiale ou SVG)
        assert response.status_code == 200
        content = response.content.decode()
        assert "rounded-circle" in content
