"""Tests pour la navbar et le dashboard (issue #27)."""

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
