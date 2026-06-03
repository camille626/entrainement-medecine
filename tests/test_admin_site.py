"""Tests RED pour l'interface admin web (issue #15)."""

import pytest
from django.contrib.auth.models import User

from qcm.models import (
    Answer,
    Category,
    Course,
    CoursePackage,
    Question,
    RegistrationRequest,
    Semester,
    StudyYear,
    UserEnrollment,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="admin_test",
        password="admin_pass",  # pragma: allowlist secret
        is_staff=True,
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username="user_test",
        password="user_pass",  # pragma: allowlist secret
    )


@pytest.fixture
def study_year(db):
    return StudyYear.objects.create(name="P2", order=1)


@pytest.fixture
def semester(study_year):
    return Semester.objects.create(name="S1", study_year=study_year, order=1)


@pytest.fixture
def course(semester):
    return Course.objects.create(
        name="P2 - La cellule",
        short_name="cell",
        moodle_id=11,
        semester=semester,
    )


@pytest.fixture
def category(course):
    return Category.objects.create(
        name="Membrane plasmique", course=course, moodle_id=100
    )


@pytest.fixture
def question(category):
    q = Question.objects.create(
        text="<p>Question test admin</p>",
        category=category,
        qtype="multichoice",
    )
    Answer.objects.create(text="Bonne", question=q, fraction=1.0, is_correct=True)
    Answer.objects.create(text="Mauvaise", question=q, fraction=0.0, is_correct=False)
    return q


@pytest.fixture
def pending_request(db):
    return RegistrationRequest.objects.create(
        first_name="Alice",
        last_name="Dupont",
        email="alice@medecine.fr",
        year="P2",
        parcours="PASS",
        status=RegistrationRequest.PENDING,
    )


@pytest.fixture
def course_package(db, course):
    pkg = CoursePackage.objects.create(name="P2 PASS", year="P2", parcours="PASS")
    pkg.courses.add(course)
    return pkg


# ── Accès — protection staff ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminSiteAccess:
    def test_dashboard_requires_staff(self, client, regular_user):
        """Un utilisateur non-staff est redirigé hors du tableau de bord."""
        client.force_login(regular_user)
        response = client.get("/admin-site/")
        assert response.status_code == 302

    def test_dashboard_accessible_to_staff(self, client, staff_user):
        """Un staff peut accéder au tableau de bord."""
        client.force_login(staff_user)
        response = client.get("/admin-site/")
        assert response.status_code == 200

    def test_anonymous_redirected(self, client):
        """Un visiteur anonyme est redirigé vers la page de login."""
        response = client.get("/admin-site/")
        assert response.status_code == 302

    def test_registrations_requires_staff(self, client, regular_user):
        client.force_login(regular_user)
        response = client.get("/admin-site/demandes/")
        assert response.status_code == 302

    def test_users_requires_staff(self, client, regular_user):
        client.force_login(regular_user)
        response = client.get("/admin-site/utilisateurs/")
        assert response.status_code == 302

    def test_questions_requires_staff(self, client, regular_user):
        client.force_login(regular_user)
        response = client.get("/admin-site/questions/")
        assert response.status_code == 302


# ── Tableau de bord ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminDashboard:
    def test_dashboard_shows_pending_count(self, client, staff_user, pending_request):
        """Le tableau de bord affiche le nombre de demandes en attente."""
        client.force_login(staff_user)
        response = client.get("/admin-site/")
        assert response.status_code == 200
        assert b"1" in response.content or "pending" in str(response.context)

    def test_dashboard_shows_user_count(self, client, staff_user, regular_user):
        """Le tableau de bord affiche le nombre d'utilisateurs."""
        client.force_login(staff_user)
        response = client.get("/admin-site/")
        assert response.status_code == 200
        assert response.context["user_count"] >= 2


# ── Demandes d'inscription ────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminRegistrations:
    def test_list_shows_pending_requests(self, client, staff_user, pending_request):
        """La liste affiche les demandes en attente."""
        client.force_login(staff_user)
        response = client.get("/admin-site/demandes/")
        assert response.status_code == 200
        assert b"alice@medecine.fr" in response.content

    def test_accept_creates_user(
        self, client, staff_user, pending_request, course_package
    ):
        """Accepter une demande crée un compte utilisateur."""
        client.force_login(staff_user)
        response = client.post(f"/admin-site/demandes/{pending_request.pk}/accepter/")
        assert response.status_code == 302
        assert User.objects.filter(email="alice@medecine.fr").exists()

    def test_accept_sets_status_accepted(
        self, client, staff_user, pending_request, course_package
    ):
        """Accepter une demande met son statut à ACCEPTED."""
        client.force_login(staff_user)
        client.post(f"/admin-site/demandes/{pending_request.pk}/accepter/")
        pending_request.refresh_from_db()
        assert pending_request.status == RegistrationRequest.ACCEPTED

    def test_accept_enrolls_user_in_courses(
        self, client, staff_user, pending_request, course_package, course
    ):
        """Accepter une demande inscrit l'utilisateur aux cours du package correspondant."""
        client.force_login(staff_user)
        client.post(f"/admin-site/demandes/{pending_request.pk}/accepter/")
        user = User.objects.get(email="alice@medecine.fr")
        assert UserEnrollment.objects.filter(user=user, course=course).exists()

    def test_reject_sets_status_rejected(self, client, staff_user, pending_request):
        """Refuser une demande met son statut à REJECTED."""
        client.force_login(staff_user)
        client.post(
            f"/admin-site/demandes/{pending_request.pk}/refuser/",
            {"admin_note": "Justificatif insuffisant"},
        )
        pending_request.refresh_from_db()
        assert pending_request.status == RegistrationRequest.REJECTED

    def test_reject_does_not_create_user(self, client, staff_user, pending_request):
        """Refuser une demande ne crée pas d'utilisateur."""
        client.force_login(staff_user)
        client.post(f"/admin-site/demandes/{pending_request.pk}/refuser/", {})
        assert not User.objects.filter(email="alice@medecine.fr").exists()


# ── Gestion des utilisateurs ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminUsers:
    def test_list_shows_users(self, client, staff_user, regular_user):
        """La liste des utilisateurs affiche tous les comptes."""
        client.force_login(staff_user)
        response = client.get("/admin-site/utilisateurs/")
        assert response.status_code == 200
        assert b"user_test" in response.content

    def test_toggle_deactivates_active_user(self, client, staff_user, regular_user):
        """Toggler un utilisateur actif le désactive."""
        assert regular_user.is_active is True
        client.force_login(staff_user)
        client.post(f"/admin-site/utilisateurs/{regular_user.pk}/toggle/")
        regular_user.refresh_from_db()
        assert regular_user.is_active is False

    def test_toggle_activates_inactive_user(self, client, staff_user, regular_user):
        """Toggler un utilisateur inactif le réactive."""
        regular_user.is_active = False
        regular_user.save()
        client.force_login(staff_user)
        client.post(f"/admin-site/utilisateurs/{regular_user.pk}/toggle/")
        regular_user.refresh_from_db()
        assert regular_user.is_active is True

    def test_cannot_deactivate_self(self, client, staff_user):
        """L'admin ne peut pas désactiver son propre compte."""
        client.force_login(staff_user)
        client.post(f"/admin-site/utilisateurs/{staff_user.pk}/toggle/")
        staff_user.refresh_from_db()
        assert staff_user.is_active is True


# ── Gestion des questions ─────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminQuestions:
    def test_list_accessible(self, client, staff_user):
        """La liste des questions est accessible."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/")
        assert response.status_code == 200

    def test_list_filtered_by_course(self, client, staff_user, question, course):
        """Le filtre par cours fonctionne."""
        client.force_login(staff_user)
        response = client.get(f"/admin-site/questions/?course={course.pk}")
        assert response.status_code == 200
        assert b"Question test admin" in response.content

    def test_add_question_page_accessible(self, client, staff_user):
        """La page d'ajout de question est accessible."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/ajouter/")
        assert response.status_code == 200

    def test_add_question_creates_question(self, client, staff_user, category):
        """Soumettre le formulaire crée une question avec ses réponses."""
        client.force_login(staff_user)
        response = client.post(
            "/admin-site/questions/ajouter/",
            {
                "text": "<p>Nouvelle question</p>",
                "category": category.pk,
                "qtype": "multichoice",
                "form-TOTAL_FORMS": "2",
                "form-INITIAL_FORMS": "0",
                "form-0-text": "Bonne réponse",
                "form-0-fraction": "1.0",
                "form-1-text": "Mauvaise réponse",
                "form-1-fraction": "0.0",
            },
        )
        assert response.status_code == 302
        assert Question.objects.filter(text="<p>Nouvelle question</p>").exists()

    def test_edit_question_page_accessible(self, client, staff_user, question):
        """La page de modification d'une question est accessible."""
        client.force_login(staff_user)
        response = client.get(f"/admin-site/questions/{question.pk}/modifier/")
        assert response.status_code == 200

    def test_edit_question_updates_text(self, client, staff_user, question, category):
        """Soumettre le formulaire de modification met à jour le texte."""
        client.force_login(staff_user)
        client.post(
            f"/admin-site/questions/{question.pk}/modifier/",
            {
                "text": "<p>Texte modifié</p>",
                "category": category.pk,
                "qtype": "multichoice",
                "form-TOTAL_FORMS": "2",
                "form-INITIAL_FORMS": "2",
                "form-0-id": question.answers.first().pk,
                "form-0-text": "Bonne réponse",
                "form-0-fraction": "1.0",
                "form-1-id": question.answers.last().pk,
                "form-1-text": "Mauvaise réponse",
                "form-1-fraction": "0.0",
            },
        )
        question.refresh_from_db()
        assert question.text == "<p>Texte modifié</p>"


# ── Gestion des cours ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminCourses:
    def test_courses_list_accessible(self, client, staff_user, course):
        """La liste des cours est accessible."""
        client.force_login(staff_user)
        response = client.get("/admin-site/cours/")
        assert response.status_code == 200
        assert b"P2 - La cellule" in response.content

    def test_assign_semester(self, client, staff_user, course, semester):
        """L'assignation d'un semestre à un cours fonctionne."""
        course.semester = None
        course.save()
        client.force_login(staff_user)
        client.post(
            f"/admin-site/cours/{course.pk}/",
            {"semester": semester.pk},
        )
        course.refresh_from_db()
        assert course.semester == semester
