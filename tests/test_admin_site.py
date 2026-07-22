"""Tests RED pour l'interface admin web (issue #15)."""

import pytest
from django.contrib.auth.models import User

from qcm.models import (
    Answer,
    Course,
    CoursePackage,
    ImageDragItem,
    ImageDropZone,
    ImageDropZoneLabel,
    Question,
    QuestionImage,
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
def question(course):
    q = Question.objects.create(
        text="<p>Question test admin</p>",
        course=course,
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

    def test_list_shows_new_legend_question_button(self, client, staff_user):
        """Un bouton dédié permet de créer une question légende interactive."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/")
        assert b"/admin-site/questions/ajouter/?qtype=ddimageortext" in response.content

    def test_list_filtered_by_course(self, client, staff_user, question, course):
        """Le filtre par cours fonctionne."""
        client.force_login(staff_user)
        response = client.get(f"/admin-site/questions/?course={course.pk}")
        assert response.status_code == 200
        assert b"Question test admin" in response.content

    def test_list_shows_qtype_filter_options(self, client, staff_user):
        """Le filtre par type de question propose les qtypes existants."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/")
        content = response.content.decode()
        assert 'name="qtype"' in content
        assert "Légende interactive" in content

    def test_list_filtered_by_qtype(self, client, staff_user, question, ddi_question):
        """Le filtre par type de question (qtype) n'affiche que les questions du type choisi."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/?qtype=ddimageortext")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Question test admin" not in content
        assert "Légender l" in content

    def test_add_question_page_accessible(self, client, staff_user):
        """La page d'ajout de question est accessible."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/ajouter/")
        assert response.status_code == 200

    def test_add_question_creates_question(self, client, staff_user, course):
        """Soumettre le formulaire crée une question avec ses réponses."""
        client.force_login(staff_user)
        response = client.post(
            "/admin-site/questions/ajouter/",
            {
                "text": "<p>Nouvelle question</p>",
                "course": course.pk,
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

    def test_edit_question_updates_text(self, client, staff_user, question, course):
        """Soumettre le formulaire de modification met à jour le texte."""
        client.force_login(staff_user)
        client.post(
            f"/admin-site/questions/{question.pk}/modifier/",
            {
                "text": "<p>Texte modifié</p>",
                "course": course.pk,
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

    def test_list_filtered_by_tags_include(self, client, staff_user, question, course):
        """Le filtre 'tags' (inclusion multi-sélection) ne montre que les questions taguées."""
        from qcm.models import Tag

        tag = Tag.objects.create(name="hemato")
        question.tags.add(tag)
        other = Question.objects.create(
            text="Question sans tag hemato", course=course, qtype="multichoice"
        )
        client.force_login(staff_user)
        response = client.get(f"/admin-site/questions/?tags={tag.pk}")
        content = response.content.decode()
        assert "Question test admin" in content
        assert other.text not in content

    def test_list_filtered_by_tags_include_is_ored(self, client, staff_user, course):
        """Sélectionner plusieurs tags à inclure retourne les questions ayant au moins un des tags."""
        from qcm.models import Tag

        tag_a = Tag.objects.create(name="tag-a")
        tag_b = Tag.objects.create(name="tag-b")
        q_a = Question.objects.create(
            text="Question avec tag A", course=course, qtype="multichoice"
        )
        q_a.tags.add(tag_a)
        q_b = Question.objects.create(
            text="Question avec tag B", course=course, qtype="multichoice"
        )
        q_b.tags.add(tag_b)
        q_none = Question.objects.create(
            text="Question sans tag A ni B", course=course, qtype="multichoice"
        )
        client.force_login(staff_user)
        response = client.get(f"/admin-site/questions/?tags={tag_a.pk}&tags={tag_b.pk}")
        content = response.content.decode()
        assert q_a.text in content
        assert q_b.text in content
        assert q_none.text not in content

    def test_list_filtered_by_exclude_tags(self, client, staff_user, question, course):
        """Le filtre 'exclude_tags' exclut les questions portant un des tags sélectionnés."""
        from qcm.models import Tag

        tag = Tag.objects.create(name="a-exclure")
        question.tags.add(tag)
        other = Question.objects.create(
            text="Question sans le tag exclu", course=course, qtype="multichoice"
        )
        client.force_login(staff_user)
        response = client.get(f"/admin-site/questions/?exclude_tags={tag.pk}")
        content = response.content.decode()
        assert "Question test admin" not in content
        assert other.text in content

    def test_list_filtered_by_exclude_courses(
        self, client, staff_user, question, course
    ):
        """Le filtre 'exclude_courses' exclut toutes les questions des cours sélectionnés."""
        other_course = Course.objects.create(name="Autre cours", short_name="autre")
        other = Question.objects.create(
            text="Question d'un autre cours", course=other_course, qtype="multichoice"
        )
        client.force_login(staff_user)
        response = client.get(f"/admin-site/questions/?exclude_courses={course.pk}")
        content = response.content.decode()
        assert "Question test admin" not in content
        assert other.text in content

    def test_tags_dropdown_scoped_to_selected_course(
        self, client, staff_user, question, course
    ):
        """Quand un cours est sélectionné, seuls les tags de ce cours apparaissent dans le filtre par tag."""
        from qcm.models import Tag

        other_course = Course.objects.create(name="Autre cours 2", short_name="autre2")
        tag_this_course = Tag.objects.create(name="tag-du-cours")
        question.tags.add(tag_this_course)
        other_question = Question.objects.create(
            text="Q autre cours", course=other_course, qtype="multichoice"
        )
        tag_other_course = Tag.objects.create(name="tag-autre-cours")
        other_question.tags.add(tag_other_course)

        client.force_login(staff_user)
        response = client.get(f"/admin-site/questions/?course={course.pk}")
        content = response.content.decode()
        assert "tag-du-cours" in content
        assert "tag-autre-cours" not in content

    def test_list_filtered_no_chapitre(self, client, staff_user, question, course):
        """Le filtre 'sans tag chapitre' exclut les questions ayant un tag chapitre."""
        from qcm.models import Tag, TagCategory

        cat = TagCategory.objects.create(
            name="Chapitres", tag_type=TagCategory.CHAPITRE
        )
        tag = Tag.objects.create(name="chap1", category=cat)
        question.tags.add(tag)
        untagged = Question.objects.create(
            text="Question sans tag chapitre", course=course, qtype="multichoice"
        )
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/?no_chapitre=1")
        content = response.content.decode()
        assert "Question test admin" not in content
        assert untagged.text in content

    def test_list_filtered_no_ec(self, client, staff_user, question, course):
        """Le filtre 'sans tag EC' exclut les questions ayant un tag EC (souscategorie)."""
        from qcm.models import Tag, TagCategory

        cat = TagCategory.objects.create(name="EC", tag_type=TagCategory.SOUSCATEGORIE)
        tag = Tag.objects.create(name="semio", category=cat)
        question.tags.add(tag)
        untagged = Question.objects.create(
            text="Question sans tag EC", course=course, qtype="multichoice"
        )
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/?no_ec=1")
        content = response.content.decode()
        assert "Question test admin" not in content
        assert untagged.text in content

    def test_list_shows_last_modified_column(self, client, staff_user, question):
        """La liste affiche la date de dernière modification de chaque question."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/")
        content = response.content.decode()
        assert question.updated_at.strftime("%d/%m/%Y") in content

    def test_list_sortable_by_last_modified(self, client, staff_user, question, course):
        """Le tri par dernière modification (desc) place la question la plus récente en premier."""
        from datetime import timedelta

        from django.utils import timezone

        older = Question.objects.create(
            text="Question plus ancienne", course=course, qtype="multichoice"
        )
        Question.objects.filter(pk=older.pk).update(
            updated_at=timezone.now() - timedelta(days=5)
        )
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/?sort=-updated_at")
        content = response.content.decode()
        assert content.index("Question test admin") < content.index(
            "Question plus ancienne"
        )

    def test_delete_list_form_carries_current_filters_as_back_url(
        self, client, staff_user, question, course
    ):
        """Le formulaire de suppression depuis la liste conserve les filtres actuels."""
        client.force_login(staff_user)
        response = client.get(
            f"/admin-site/questions/?course={course.pk}&qtype=multichoice"
        )
        content = response.content.decode()
        assert (
            f'value="/admin-site/questions/?course={course.pk}&amp;qtype=multichoice"'
            in content
        )

    def test_delete_redirects_to_posted_back_url(self, client, staff_user, question):
        """La suppression redirige vers back_url si fourni, en conservant les filtres."""
        client.force_login(staff_user)
        back_url = "/admin-site/questions/?course=9&qtype=ddimageortext"
        response = client.post(
            f"/admin-site/questions/{question.pk}/supprimer/",
            {"back_url": back_url},
        )
        assert response.status_code == 302
        assert response["Location"] == back_url
        assert not Question.objects.filter(pk=question.pk).exists()

    def test_delete_without_back_url_defaults_to_list(
        self, client, staff_user, question
    ):
        """Sans back_url, la suppression redirige vers la liste non filtrée (comportement historique)."""
        client.force_login(staff_user)
        response = client.post(f"/admin-site/questions/{question.pk}/supprimer/")
        assert response.status_code == 302
        assert response["Location"] == "/admin-site/questions/"

    def test_bulk_delete_requires_staff(self, client, regular_user, question):
        """Un utilisateur non-staff est redirigé, la question n'est pas supprimée."""
        client.force_login(regular_user)
        response = client.post(
            "/admin-site/questions/supprimer-multiple/",
            {"pks": [str(question.pk)]},
        )
        assert response.status_code == 302
        assert Question.objects.filter(pk=question.pk).exists()

    def test_bulk_delete_requires_login(self, client, question):
        """Un utilisateur anonyme est redirigé vers la connexion."""
        response = client.post(
            "/admin-site/questions/supprimer-multiple/",
            {"pks": [str(question.pk)]},
        )
        assert response.status_code == 302
        assert Question.objects.filter(pk=question.pk).exists()

    def test_bulk_delete_removes_selected_questions(self, client, staff_user, course):
        """POST avec plusieurs pks supprime toutes les questions sélectionnées, et seulement elles."""
        q1 = Question.objects.create(
            text="A supprimer 1", course=course, qtype="multichoice"
        )
        q2 = Question.objects.create(
            text="A supprimer 2", course=course, qtype="multichoice"
        )
        q3 = Question.objects.create(
            text="A garder", course=course, qtype="multichoice"
        )
        client.force_login(staff_user)
        response = client.post(
            "/admin-site/questions/supprimer-multiple/",
            {"pks": [str(q1.pk), str(q2.pk)]},
        )
        assert response.status_code == 302
        assert not Question.objects.filter(pk=q1.pk).exists()
        assert not Question.objects.filter(pk=q2.pk).exists()
        assert Question.objects.filter(pk=q3.pk).exists()

    def test_bulk_delete_with_empty_selection_is_noop(
        self, client, staff_user, question
    ):
        """Sans pks, aucune suppression n'a lieu, la redirection reste normale (pas d'erreur 500)."""
        client.force_login(staff_user)
        response = client.post("/admin-site/questions/supprimer-multiple/", {})
        assert response.status_code == 302
        assert Question.objects.filter(pk=question.pk).exists()

    def test_bulk_delete_ignores_invalid_pks(self, client, staff_user, question):
        """Des pks non numériques ou inexistants sont ignorés sans lever d'erreur."""
        client.force_login(staff_user)
        response = client.post(
            "/admin-site/questions/supprimer-multiple/",
            {"pks": ["abc", "999999", str(question.pk)]},
        )
        assert response.status_code == 302
        assert not Question.objects.filter(pk=question.pk).exists()

    def test_bulk_delete_redirects_to_posted_back_url(
        self, client, staff_user, question
    ):
        """La suppression en masse redirige vers back_url si fourni, en conservant les filtres."""
        client.force_login(staff_user)
        back_url = "/admin-site/questions/?course=9&qtype=ddimageortext"
        response = client.post(
            "/admin-site/questions/supprimer-multiple/",
            {"pks": [str(question.pk)], "back_url": back_url},
        )
        assert response.status_code == 302
        assert response["Location"] == back_url

    def test_bulk_delete_without_back_url_defaults_to_list(
        self, client, staff_user, question
    ):
        """Sans back_url, la redirection va vers la liste non filtrée."""
        client.force_login(staff_user)
        response = client.post(
            "/admin-site/questions/supprimer-multiple/",
            {"pks": [str(question.pk)]},
        )
        assert response.status_code == 302
        assert response["Location"] == "/admin-site/questions/"

    def test_list_renders_row_checkboxes(self, client, staff_user, question):
        """Chaque ligne de la liste affiche une checkbox de sélection nommée 'pks'."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/")
        content = response.content.decode()
        assert f'name="pks" value="{question.pk}"' in content
        assert 'class="form-check-input q-select-checkbox"' in content

    def test_list_renders_select_all_checkbox(self, client, staff_user, question):
        """La liste affiche une checkbox 'tout sélectionner' pour la page courante."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/")
        content = response.content.decode()
        assert 'id="selectAllQuestions"' in content

    def test_list_renders_bulk_delete_action_bar(self, client, staff_user, question):
        """La barre d'action bulk (compteur + bouton) est présente dans le HTML."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/")
        content = response.content.decode()
        assert 'id="bulkDeleteBtn"' in content
        assert 'id="bulkSelectedCount"' in content

    def test_list_bulk_delete_form_targets_bulk_delete_url(
        self, client, staff_user, question
    ):
        """Le formulaire de confirmation bulk pointe vers la route de suppression en masse."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/")
        content = response.content.decode()
        assert "/admin-site/questions/supprimer-multiple/" in content

    def test_list_includes_shift_click_range_selection_script(
        self, client, staff_user, question
    ):
        """Le JS de sélection par plage (shift+clic) est présent dans la page."""
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/")
        content = response.content.decode()
        assert "e.shiftKey" in content
        assert "lastClickedIndex" in content

    def test_edit_page_shows_delete_button(self, client, staff_user, question):
        """La page de modification propose un bouton de suppression."""
        client.force_login(staff_user)
        response = client.get(f"/admin-site/questions/{question.pk}/modifier/")
        content = response.content.decode()
        assert f"/admin-site/questions/{question.pk}/supprimer/" in content

    def test_edit_page_delete_form_carries_back_url(self, client, staff_user, question):
        """Le formulaire de suppression de la page d'édition conserve le back_url d'origine."""
        from urllib.parse import quote

        client.force_login(staff_user)
        back_url = "/admin-site/questions/?course=9&qtype=multichoice"
        response = client.get(
            f"/admin-site/questions/{question.pk}/modifier/?back={quote(back_url, safe='')}"
        )
        content = response.content.decode()
        assert (
            'value="/admin-site/questions/?course=9&amp;qtype=multichoice"' in content
        )

    def test_delete_from_edit_page_deletes_question(self, client, staff_user, question):
        """Soumettre la suppression depuis la page d'édition supprime bien la question."""
        client.force_login(staff_user)
        back_url = "/admin-site/questions/?qtype=multichoice"
        response = client.post(
            f"/admin-site/questions/{question.pk}/supprimer/",
            {"back_url": back_url},
        )
        assert response.status_code == 302
        assert response["Location"] == back_url
        assert not Question.objects.filter(pk=question.pk).exists()


# ── Gestion des questions ddimageortext (légende interactive) ─────────────────


@pytest.fixture
def bg_image_file():
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile("fond.png", b"fake-image-bytes", content_type="image/png")


@pytest.fixture
def ddi_question(course):
    return Question.objects.create(
        text="<p>Légender l'oeil</p>",
        course=course,
        qtype=Question.DDIMAGEORTEXT,
    )


@pytest.fixture
def ddi_zones(ddi_question):
    return [
        ImageDropZone.objects.create(
            question=ddi_question,
            no=1,
            xleft=100,
            ytop=50,
            correct_drag_no=0,
            correct_label="sclérotique",
        ),
        ImageDropZone.objects.create(
            question=ddi_question,
            no=2,
            xleft=200,
            ytop=100,
            correct_drag_no=0,
            correct_label="rétine",
        ),
    ]


@pytest.mark.django_db
class TestAdminQuestionsDDImageOrText:
    def test_add_page_select_includes_ddimageortext_option(self, client, staff_user):
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/ajouter/")
        assert b"ddimageortext" in response.content

    def test_add_page_preselects_qtype_from_query_param(self, client, staff_user):
        client.force_login(staff_user)
        response = client.get("/admin-site/questions/ajouter/?qtype=ddimageortext")
        assert response.status_code == 200
        # Le select doit marquer ddimageortext comme sélectionné par défaut
        content = response.content.decode()
        idx = content.index('value="ddimageortext"')
        assert "selected" in content[idx : idx + 60]

    def test_create_ddimageortext_question_with_image_zones_and_drag_items(
        self, client, staff_user, course, bg_image_file
    ):
        client.force_login(staff_user)
        response = client.post(
            "/admin-site/questions/ajouter/",
            {
                "text": "<p>Légender l'oeil</p>",
                "course": course.pk,
                "qtype": "ddimageortext",
                "new_bg_image_file": bg_image_file,
                "dragform-TOTAL_FORMS": "2",
                "dragform-INITIAL_FORMS": "0",
                "dragform-0-label": "sclérotique",
                "dragform-1-label": "rétine",
                "zoneform-TOTAL_FORMS": "2",
                "zoneform-INITIAL_FORMS": "0",
                "zoneform-0-xleft": "100",
                "zoneform-0-ytop": "50",
                "zoneform-0-correct_label": "sclérotique",
                "zoneform-0-alts": "sclere; sclerotic",
                "zoneform-1-xleft": "200",
                "zoneform-1-ytop": "100",
                "zoneform-1-correct_label": "rétine",
                "zoneform-1-alts": "",
            },
        )
        assert response.status_code == 302
        question = Question.objects.get(text="<p>Légender l'oeil</p>")
        assert question.qtype == Question.DDIMAGEORTEXT
        assert question.images.filter(moodle_filename="background").count() == 1
        assert ImageDragItem.objects.filter(question=question).count() == 2
        zones = ImageDropZone.objects.filter(question=question).order_by("no")
        assert zones.count() == 2
        assert list(zones.values_list("no", flat=True)) == [1, 2]
        zone1 = zones.get(no=1)
        assert zone1.correct_label == "sclérotique"
        alt_texts = set(zone1.accepted_labels.values_list("text", flat=True))
        assert alt_texts == {"sclere", "sclerotic"}
        zone2 = zones.get(no=2)
        assert zone2.accepted_labels.count() == 0

    def test_edit_ddimageortext_adds_zone_assigns_next_no(
        self, client, staff_user, course, ddi_question, ddi_zones
    ):
        client.force_login(staff_user)
        client.post(
            f"/admin-site/questions/{ddi_question.pk}/modifier/",
            {
                "text": ddi_question.text,
                "course": course.pk,
                "qtype": "ddimageortext",
                "dragform-TOTAL_FORMS": "0",
                "dragform-INITIAL_FORMS": "0",
                "zoneform-TOTAL_FORMS": "3",
                "zoneform-INITIAL_FORMS": "2",
                "zoneform-0-id": ddi_zones[0].pk,
                "zoneform-0-xleft": "100",
                "zoneform-0-ytop": "50",
                "zoneform-0-correct_label": "sclérotique",
                "zoneform-0-alts": "",
                "zoneform-1-id": ddi_zones[1].pk,
                "zoneform-1-xleft": "200",
                "zoneform-1-ytop": "100",
                "zoneform-1-correct_label": "rétine",
                "zoneform-1-alts": "",
                "zoneform-2-xleft": "300",
                "zoneform-2-ytop": "150",
                "zoneform-2-correct_label": "choroide",
                "zoneform-2-alts": "",
            },
        )
        zones = ImageDropZone.objects.filter(question=ddi_question).order_by("no")
        assert list(zones.values_list("no", flat=True)) == [1, 2, 3]
        assert zones.get(no=3).correct_label == "choroide"

    def test_edit_ddimageortext_deletes_zone(
        self, client, staff_user, course, ddi_question, ddi_zones
    ):
        client.force_login(staff_user)
        client.post(
            f"/admin-site/questions/{ddi_question.pk}/modifier/",
            {
                "text": ddi_question.text,
                "course": course.pk,
                "qtype": "ddimageortext",
                "dragform-TOTAL_FORMS": "0",
                "dragform-INITIAL_FORMS": "0",
                "zoneform-TOTAL_FORMS": "2",
                "zoneform-INITIAL_FORMS": "2",
                "zoneform-0-id": ddi_zones[0].pk,
                "zoneform-0-xleft": "100",
                "zoneform-0-ytop": "50",
                "zoneform-0-correct_label": "sclérotique",
                "zoneform-0-alts": "",
                "zoneform-1-id": ddi_zones[1].pk,
                "zoneform-1-xleft": "200",
                "zoneform-1-ytop": "100",
                "zoneform-1-correct_label": "rétine",
                "zoneform-1-alts": "",
                "zoneform-1-DELETE": "on",
            },
        )
        assert not ImageDropZone.objects.filter(pk=ddi_zones[1].pk).exists()
        assert ImageDropZone.objects.filter(pk=ddi_zones[0].pk).exists()

    def test_edit_ddimageortext_updates_alt_labels(
        self, client, staff_user, course, ddi_question, ddi_zones
    ):
        ImageDropZoneLabel.objects.create(zone=ddi_zones[0], text="ancien")
        client.force_login(staff_user)
        client.post(
            f"/admin-site/questions/{ddi_question.pk}/modifier/",
            {
                "text": ddi_question.text,
                "course": course.pk,
                "qtype": "ddimageortext",
                "dragform-TOTAL_FORMS": "0",
                "dragform-INITIAL_FORMS": "0",
                "zoneform-TOTAL_FORMS": "2",
                "zoneform-INITIAL_FORMS": "2",
                "zoneform-0-id": ddi_zones[0].pk,
                "zoneform-0-xleft": "100",
                "zoneform-0-ytop": "50",
                "zoneform-0-correct_label": "sclérotique",
                "zoneform-0-alts": "nouveau1; nouveau2",
                "zoneform-1-id": ddi_zones[1].pk,
                "zoneform-1-xleft": "200",
                "zoneform-1-ytop": "100",
                "zoneform-1-correct_label": "rétine",
                "zoneform-1-alts": "",
            },
        )
        ddi_zones[0].refresh_from_db()
        alt_texts = set(ddi_zones[0].accepted_labels.values_list("text", flat=True))
        assert alt_texts == {"nouveau1", "nouveau2"}

    def test_edit_ddimageortext_replaces_background_image(
        self, client, staff_user, course, ddi_question, ddi_zones, bg_image_file
    ):
        QuestionImage.objects.create(
            question=ddi_question, moodle_filename="background", file=bg_image_file
        )
        from django.core.files.uploadedfile import SimpleUploadedFile

        client.force_login(staff_user)
        new_file = SimpleUploadedFile(
            "nouveau.png", b"new-bytes", content_type="image/png"
        )
        client.post(
            f"/admin-site/questions/{ddi_question.pk}/modifier/",
            {
                "text": ddi_question.text,
                "course": course.pk,
                "qtype": "ddimageortext",
                "new_bg_image_file": new_file,
                "dragform-TOTAL_FORMS": "0",
                "dragform-INITIAL_FORMS": "0",
                "zoneform-TOTAL_FORMS": "2",
                "zoneform-INITIAL_FORMS": "2",
                "zoneform-0-id": ddi_zones[0].pk,
                "zoneform-0-xleft": "100",
                "zoneform-0-ytop": "50",
                "zoneform-0-correct_label": "sclérotique",
                "zoneform-0-alts": "",
                "zoneform-1-id": ddi_zones[1].pk,
                "zoneform-1-xleft": "200",
                "zoneform-1-ytop": "100",
                "zoneform-1-correct_label": "rétine",
                "zoneform-1-alts": "",
            },
        )
        assert (
            QuestionImage.objects.filter(
                question=ddi_question, moodle_filename="background"
            ).count()
            == 1
        )

    def test_edit_page_shows_image_imported_from_moodle(
        self, client, staff_user, ddi_question, bg_image_file
    ):
        """Une image importée de Moodle (nom de fichier arbitraire, pas 'background') doit s'afficher en édition."""
        QuestionImage.objects.create(
            question=ddi_question,
            moodle_filename="oeil 150815.png",
            file=bg_image_file,
        )
        client.force_login(staff_user)
        response = client.get(f"/admin-site/questions/{ddi_question.pk}/modifier/")
        assert response.context["existing_bg_image"] is not None

    def test_replace_background_image_removes_old_moodle_named_image(
        self, client, staff_user, course, ddi_question, ddi_zones, bg_image_file
    ):
        """Remplacer l'image de fond doit supprimer l'ancienne, même si elle vient de l'import Moodle."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        QuestionImage.objects.create(
            question=ddi_question,
            moodle_filename="oeil 150815.png",
            file=bg_image_file,
        )
        client.force_login(staff_user)
        new_file = SimpleUploadedFile(
            "nouveau.png", b"new-bytes", content_type="image/png"
        )
        client.post(
            f"/admin-site/questions/{ddi_question.pk}/modifier/",
            {
                "text": ddi_question.text,
                "course": course.pk,
                "qtype": "ddimageortext",
                "new_bg_image_file": new_file,
                "dragform-TOTAL_FORMS": "0",
                "dragform-INITIAL_FORMS": "0",
                "zoneform-TOTAL_FORMS": "2",
                "zoneform-INITIAL_FORMS": "2",
                "zoneform-0-id": ddi_zones[0].pk,
                "zoneform-0-xleft": "100",
                "zoneform-0-ytop": "50",
                "zoneform-0-correct_label": "sclérotique",
                "zoneform-0-alts": "",
                "zoneform-1-id": ddi_zones[1].pk,
                "zoneform-1-xleft": "200",
                "zoneform-1-ytop": "100",
                "zoneform-1-correct_label": "rétine",
                "zoneform-1-alts": "",
            },
        )
        images = QuestionImage.objects.filter(question=ddi_question)
        assert images.count() == 1
        assert images.first().moodle_filename == "background"


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
