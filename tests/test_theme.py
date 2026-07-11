"""Tests pour le mode sombre (issue #97)."""

import re

import pytest
from django.contrib.auth.models import User

from qcm.models import UserProfile


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="etudiant",
        password="motdepasse123",  # pragma: allowlist secret
        first_name="Camille",
        last_name="Martin",
        email="camille@example.com",
    )


@pytest.mark.django_db
class TestUserProfileThemeField:
    def test_theme_defaults_to_empty_string(self, user):
        profile = UserProfile.objects.create(user=user)
        assert profile.theme == ""

    def test_theme_accepts_light_and_dark(self, user):
        profile = UserProfile.objects.create(user=user, theme="dark")
        profile.refresh_from_db()
        assert profile.theme == "dark"


@pytest.mark.django_db
class TestThemeToggleView:
    def test_requires_login(self, client):
        response = client.post("/profil/theme/", {"theme": "dark"})
        assert response.status_code == 302
        assert response["Location"].startswith("/login/")

    def test_post_dark_persists_on_profile(self, client, user):
        client.force_login(user)
        response = client.post("/profil/theme/", {"theme": "dark"})
        assert response.status_code == 204
        assert UserProfile.objects.get(user=user).theme == "dark"

    def test_post_light_persists_on_profile(self, client, user):
        UserProfile.objects.create(user=user, theme="dark")
        client.force_login(user)
        response = client.post("/profil/theme/", {"theme": "light"})
        assert response.status_code == 204
        assert UserProfile.objects.get(user=user).theme == "light"

    def test_creates_profile_if_missing(self, client, user):
        assert not UserProfile.objects.filter(user=user).exists()
        client.force_login(user)
        client.post("/profil/theme/", {"theme": "dark"})
        assert UserProfile.objects.get(user=user).theme == "dark"

    def test_invalid_theme_value_returns_400(self, client, user):
        client.force_login(user)
        response = client.post("/profil/theme/", {"theme": "purple"})
        assert response.status_code == 400
        assert not UserProfile.objects.filter(user=user, theme="purple").exists()

    def test_missing_theme_value_returns_400(self, client, user):
        client.force_login(user)
        response = client.post("/profil/theme/", {})
        assert response.status_code == 400


@pytest.mark.django_db
class TestThemeAttributeOnHtmlTag:
    def test_saved_dark_theme_rendered_on_html_tag(self, client, user):
        UserProfile.objects.create(user=user, theme="dark")
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()
        assert '<html lang="fr" data-bs-theme="dark">' in content

    def test_no_saved_theme_renders_empty_attribute(self, client, user):
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()
        assert '<html lang="fr" data-bs-theme="">' in content


@pytest.mark.django_db
class TestThemeToggleButtons:
    def test_navbar_has_toggle_buttons(self, client, user):
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()
        assert "theme-btn-to-dark" in content
        assert "theme-btn-to-light" in content

    def test_toggle_buttons_post_to_theme_endpoint(self, client, user):
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()
        assert re.search(r'hx-post="[^"]*/profil/theme/"', content)


@pytest.mark.django_db
class TestHomeDashboardDarkMode:
    """La page d'accueil ne doit pas avoir de couleurs figées non adaptatives."""

    def test_course_cards_do_not_use_fixed_white_background(self, client, user):
        from qcm.models import Course, Semester, StudyYear, UserEnrollment

        sy = StudyYear.objects.create(name="P2", order=2)
        sem = Semester.objects.create(study_year=sy, name="S1", order=1)
        course = Course.objects.create(
            name="P2 - La cellule", short_name="cell", moodle_id=11, semester=sem
        )
        UserEnrollment.objects.create(user=user, course=course)
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()
        assert "bg-white" not in content

    def test_quick_action_buttons_keep_outline_style_in_html(self, client, user):
        # Le remplissage pastel est purement du CSS scopé à
        # [data-bs-theme="dark"] .qcm-cta-btn (voir base.html) : en mode clair
        # le rendu ne doit pas changer, donc les classes outline d'origine
        # doivent rester présentes dans le HTML, avec en plus le marqueur
        # qcm-cta-btn qui active le remplissage pastel uniquement en sombre.
        client.force_login(user)
        response = client.get("/")
        content = response.content.decode()

        expected = {
            "/entrainement/": "btn-outline-primary",
            "/statistiques/": "btn-outline-warning",
            "/historique/": "btn-outline-secondary",
        }
        for href, outline_class in expected.items():
            match = re.search(rf'href="{re.escape(href)}" class="([^"]*)"', content)
            assert match is not None, f"Bouton vers {href} introuvable"
            classes = match.group(1).split()
            assert outline_class in classes
            assert "qcm-cta-btn" in classes

    def test_stats_page_does_not_use_fixed_light_table_classes(self, client, user):
        from qcm.models import (
            Answer,
            Course,
            Question,
            QuizSession,
            QuizSessionQuestion,
            Semester,
            StudyYear,
            UserAnswer,
            UserEnrollment,
        )

        sy = StudyYear.objects.create(name="P2", order=2)
        sem = Semester.objects.create(study_year=sy, name="S1", order=1)
        course = Course.objects.create(
            name="P2 - La cellule", short_name="cell", moodle_id=12, semester=sem
        )
        UserEnrollment.objects.create(user=user, course=course)
        q1 = Question.objects.create(
            text="Q1", course=course, qtype="multichoice", moodle_id=700
        )
        a1 = Answer.objects.create(text="A", question=q1, fraction=1.0, is_correct=True)
        session = QuizSession.objects.create(user=user, course=course, mode="training")
        QuizSessionQuestion.objects.create(session=session, question=q1, order=1)
        UserAnswer.objects.create(
            session=session, question=q1, answer=a1, is_correct=True
        )

        client.force_login(user)
        response = client.get("/statistiques/")
        content = response.content.decode()
        assert "Par cours" in content, "précondition : le tableau doit être rendu"
        assert "table-light" not in content
        assert "table-secondary" not in content

    def test_history_page_does_not_use_fixed_light_table_class(self, client, user):
        from qcm.models import Course, QuizSession, Semester, StudyYear

        sy = StudyYear.objects.create(name="P2", order=2)
        sem = Semester.objects.create(study_year=sy, name="S1", order=1)
        course = Course.objects.create(
            name="P2 - La cellule", short_name="cell", moodle_id=13, semester=sem
        )
        QuizSession.objects.create(user=user, course=course, mode="training")

        client.force_login(user)
        response = client.get("/historique/")
        content = response.content.decode()
        assert "<thead" in content, "précondition : le tableau doit être rendu"
        assert "table-light" not in content
