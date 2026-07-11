"""Tests pour la navbar et le dashboard (issue #27)."""

import re

import pytest
from django.contrib.auth.models import User


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="camille",
        password="pass",  # pragma: allowlist secret
        first_name="Camille",
        last_name="Martin",
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="admin",
        password="pass",  # pragma: allowlist secret
        is_staff=True,
        first_name="Admin",
    )


@pytest.mark.django_db
class TestNavbar:
    def test_navbar_has_accueil_tab(self, client, user):
        client.force_login(user)
        response = client.get("/")
        assert b"Accueil" in response.content

    def test_navbar_has_entrainement_tab(self, client, user):
        client.force_login(user)
        response = client.get("/")
        assert (
            b"ntra\xc3\xaenement" in response.content
            or b"Entrainement" in response.content
        )

    def test_navbar_has_statistics_tab(self, client, user):
        client.force_login(user)
        response = client.get("/")
        assert b"Statistiques" in response.content

    def test_navbar_has_history_tab(self, client, user):
        client.force_login(user)
        response = client.get("/")
        assert b"Historique" in response.content

    def test_admin_tab_visible_for_staff(self, client, staff_user):
        client.force_login(staff_user)
        response = client.get("/")
        assert b"Admin" in response.content

    def test_admin_tab_hidden_for_regular_user(self, client, user):
        client.force_login(user)
        response = client.get("/")
        # Admin tab should not appear in main nav for non-staff
        content = response.content.decode()
        # The word "Admin" in nav should not be present as a nav link
        assert 'id="nav-admin"' not in content

    def test_user_dropdown_shows_name(self, client, user):
        client.force_login(user)
        response = client.get("/")
        assert b"Camille" in response.content


@pytest.mark.django_db
class TestNavbarResponsive:
    """Tests pour le menu hamburger responsive (issue #78)."""

    def test_navbar_uses_breakpoint_expand_class(self, client, user):
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()
        assert "navbar-expand-lg" in content

    def test_navbar_does_not_use_bare_expand_class(self, client, user):
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()
        # "navbar-expand" seul (sans breakpoint) ne doit plus apparaître comme
        # classe isolée sur la balise <nav> : seul "navbar-expand-lg" doit rester.
        assert "navbar-expand navbar-light" not in content
        assert 'class="navbar navbar-expand ' not in content

    def test_navbar_has_toggler_button(self, client, user):
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()
        assert "navbar-toggler" in content
        assert 'data-bs-toggle="collapse"' in content

    def test_navbar_toggler_target_matches_collapse_container(self, client, user):
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()

        match = re.search(r'data-bs-target="#([\w-]+)"', content)
        assert match is not None, "Le bouton toggler doit avoir un data-bs-target"
        target_id = match.group(1)

        assert f'id="{target_id}"' in content
        container_match = re.search(
            rf'<div class="([^"]*)"\s+id="{target_id}">'
            rf'|<div class="([^"]*)" id="{target_id}"[^>]*>',
            content,
        )
        assert container_match is not None, f"Conteneur #{target_id} introuvable"
        container_classes = (container_match.group(1) or "").split()
        assert "collapse" in container_classes
        assert "navbar-collapse" in container_classes

    def test_nav_links_use_navbar_nav_class_for_vertical_stacking(self, client, user):
        # La classe "navbar-nav" (native Bootstrap 5) fait passer la liste de
        # liens en flex-direction: column sous le breakpoint navbar-expand-lg,
        # donc les options s'affichent les unes en dessous des autres une fois
        # le menu hamburger déplié sur mobile.
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()

        match = re.search(r'<ul class="([^"]*)"\s+id="mainNav">', content)
        assert match is not None, "Liste de liens #mainNav introuvable"
        classes = match.group(1).split()
        assert "navbar-nav" in classes

    def test_nav_links_are_centered(self, client, user):
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()

        match = re.search(r'<ul class="([^"]*)"\s+id="mainNav">', content)
        assert match is not None, "Liste de liens #mainNav introuvable"
        classes = match.group(1).split()
        assert "align-items-center" in classes

    def test_notif_bell_and_user_dropdown_stay_outside_collapsible_menu(
        self, client, user
    ):
        # La cloche de notifications et le dropdown utilisateur ne sont pas
        # des liens de navigation : ils doivent rester visibles en permanence,
        # juste à gauche du bouton hamburger, et non repliés dans le menu.
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()

        toggler_idx = content.index("navbar-toggler")
        collapse_idx = content.index('id="mainNavCollapse"')
        notif_idx = content.index("notif-bell-zone")

        assert notif_idx < toggler_idx < collapse_idx

    def test_user_block_has_spacing_before_toggler(self, client, user):
        # Le bloc notifications/profil ne doit pas être collé au hamburger :
        # une marge (me-*) le sépare visuellement du bouton toggler.
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()

        match = re.search(r'<div class="([^"]*order-lg-3[^"]*)">', content)
        assert match is not None, "Bloc utilisateur (order-lg-3) introuvable"
        classes = match.group(1).split()
        assert any(cls.startswith("me-") for cls in classes), (
            "Le bloc utilisateur doit avoir une marge droite (me-*) "
            "pour ne pas coller au hamburger"
        )


@pytest.mark.django_db
class TestDashboard:
    def test_dashboard_shows_greeting(self, client, user):
        client.force_login(user)
        response = client.get("/")
        assert b"Camille" in response.content
        assert b"onjour" in response.content

    def test_dashboard_has_quick_start_button(self, client, user):
        client.force_login(user)
        response = client.get("/")
        assert (
            b"session" in response.content.lower()
            or b"ntra\xc3\xaenement" in response.content
        )

    def test_dashboard_shows_enrolled_courses(self, client, user):
        from qcm.models import Course, Semester, StudyYear, UserEnrollment

        sy = StudyYear.objects.create(name="P2", order=2)
        sem = Semester.objects.create(study_year=sy, name="S1", order=1)
        course = Course.objects.create(
            name="P2 - La cellule", short_name="cell", moodle_id=11, semester=sem
        )
        UserEnrollment.objects.create(user=user, course=course)
        client.force_login(user)
        response = client.get("/")
        assert b"La cellule" in response.content
