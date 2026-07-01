"""Tests RED pour le filtrage dynamique des tags (issue #10)."""

import pytest
from django.contrib.auth.models import User

from qcm.models import (
    Answer,
    Course,
    Question,
    Semester,
    StudyYear,
    Tag,
    TagCategory,
)


@pytest.fixture
def study_year(db):
    return StudyYear.objects.create(name="P2", order=2)


@pytest.fixture
def semester(study_year):
    return Semester.objects.create(study_year=study_year, name="S1", order=1)


@pytest.fixture
def course_tissu(semester):
    return Course.objects.create(
        name="P2 - tissu sanguin et système immunitaire",
        short_name="immuno",
        moodle_id=14,
        semester=semester,
    )


@pytest.fixture
def course_cellule(semester):
    return Course.objects.create(
        name="P2 - La cellule",
        short_name="cell",
        moodle_id=11,
        semester=semester,
    )


@pytest.fixture
def cat_annee(db):
    return TagCategory.objects.create(name="Annales", tag_type="annee", order=0)


@pytest.fixture
def cat_sous_tissu(course_tissu):
    return TagCategory.objects.create(
        name="Sous-chapitres tissu sanguin",
        tag_type="souscategorie",
        course=course_tissu,
        order=1,
    )


@pytest.fixture
def tag_annale_2024(cat_annee):
    return Tag.objects.create(name="annale 2024", moodle_id=52, category=cat_annee)


@pytest.fixture
def tag_immuno(cat_sous_tissu):
    return Tag.objects.create(name="immuno", moodle_id=15, category=cat_sous_tissu)


@pytest.fixture
def tag_cellule(course_cellule, db):
    cat = TagCategory.objects.create(
        name="Sous-chapitres cellule",
        tag_type="souscategorie",
        course=course_cellule,
        order=2,
    )
    return Tag.objects.create(name="cellule eucaryote", moodle_id=20, category=cat)


@pytest.fixture
def question_tissu(course_tissu, tag_annale_2024, tag_immuno):
    q = Question.objects.create(
        text="<p>Question tissu</p>",
        course=course_tissu,
        qtype="multichoice",
        moodle_id=600,
    )
    Answer.objects.create(
        text="<p>Réponse</p>", question=q, fraction=1.0, is_correct=True
    )
    q.tags.set([tag_annale_2024, tag_immuno])
    return q


@pytest.fixture
def question_cellule(course_cellule, tag_cellule):
    q = Question.objects.create(
        text="<p>Question cellule</p>",
        course=course_cellule,
        qtype="multichoice",
        moodle_id=601,
    )
    Answer.objects.create(
        text="<p>Réponse</p>", question=q, fraction=1.0, is_correct=True
    )
    q.tags.set([tag_cellule])
    return q


# ---------------------------------------------------------------------------
# Tests du modèle TagCategory
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTagCategory:
    def test_create(self, cat_annee):
        assert cat_annee.pk is not None
        assert cat_annee.tag_type == "annee"
        assert cat_annee.course is None

    def test_souscategorie_linked_to_course(self, cat_sous_tissu, course_tissu):
        assert cat_sous_tissu.course == course_tissu

    def test_str(self, cat_annee):
        assert str(cat_annee) == "Annales"

    def test_tag_has_category(self, tag_immuno, cat_sous_tissu):
        assert tag_immuno.category == cat_sous_tissu


@pytest.fixture
def client(client, db):
    user = User.objects.create_user(
        username="tester",
        password="pass",  # pragma: allowlist secret
    )
    client.force_login(user)
    return client


# ---------------------------------------------------------------------------
# Tests de l'endpoint /entrainement/tags/
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTagsView:
    def test_no_courses_returns_200(self, client):
        response = client.get("/entrainement/tags/")
        assert response.status_code == 200

    def test_no_courses_shows_placeholder(self, client):
        response = client.get("/entrainement/tags/")
        content = response.content.decode()
        assert "cours" in content.lower()

    def test_with_course_shows_annale_tags(
        self, client, course_tissu, question_tissu, tag_annale_2024
    ):
        response = client.get(f"/entrainement/tags/?courses={course_tissu.pk}")
        assert response.status_code == 200
        assert b"annale 2024" in response.content

    def test_souscategorie_shown_for_matching_course(
        self, client, course_tissu, question_tissu, tag_immuno
    ):
        response = client.get(f"/entrainement/tags/?courses={course_tissu.pk}")
        assert b"immuno" in response.content

    def test_souscategorie_hidden_for_other_course(
        self, client, course_cellule, question_tissu, question_cellule, tag_immuno
    ):
        response = client.get(f"/entrainement/tags/?courses={course_cellule.pk}")
        assert b"immuno" not in response.content

    def test_annale_tags_shown_for_any_course(
        self, client, course_cellule, question_cellule, tag_annale_2024
    ):
        # annale 2024 is linked to tissu questions, but should still appear
        # because annale tags are "global" (shown for any selected course)
        # We need at least one annale tag to exist
        response = client.get(f"/entrainement/tags/?courses={course_cellule.pk}")
        assert response.status_code == 200
        assert b"annale 2024" in response.content

    def test_tags_for_other_course_hidden(
        self, client, course_tissu, question_tissu, tag_cellule
    ):
        response = client.get(f"/entrainement/tags/?courses={course_tissu.pk}")
        assert b"cellule eucaryote" not in response.content

    def test_uncategorized_tags_not_shown(
        self, client, course_tissu, question_tissu, db
    ):
        # Create an uncategorized tag linked to a question in tissu
        uncategorized = Tag.objects.create(name="tag sans cat", moodle_id=999)
        question_tissu.tags.add(uncategorized)
        response = client.get(f"/entrainement/tags/?courses={course_tissu.pk}")
        assert b"tag sans cat" not in response.content


# ---------------------------------------------------------------------------
# Tests de l'endpoint /entrainement/chapters/
# ---------------------------------------------------------------------------


@pytest.fixture
def cat_chapitre_tissu(course_tissu):
    return TagCategory.objects.create(
        name="Chapitres tissu sanguin",
        tag_type="chapitre",
        course=course_tissu,
        order=2,
    )


@pytest.fixture
def tag_chapitre(cat_chapitre_tissu):
    return Tag.objects.create(
        name="érythropoïèse", moodle_id=73, category=cat_chapitre_tissu
    )


@pytest.mark.django_db
class TestChaptersView:
    def test_no_ec_tags_returns_200(self, client):
        response = client.get("/entrainement/chapters/")
        assert response.status_code == 200

    def test_no_ec_tags_returns_empty(self, client):
        response = client.get("/entrainement/chapters/")
        assert b"chapitre" not in response.content.lower()

    def test_ec_tag_shows_chapter_tags(self, client, tag_immuno, tag_chapitre):
        # Link chapter to EC via parent_ec
        tag_chapitre.parent_ec = tag_immuno
        tag_chapitre.save()
        response = client.get(f"/entrainement/chapters/?tags={tag_immuno.pk}")
        assert response.status_code == 200
        assert "érythropoïèse".encode() in response.content

    def test_ec_tag_other_course_no_chapters(self, client, tag_cellule, tag_chapitre):
        # tag_chapitre has no parent_ec → never appears
        response = client.get(f"/entrainement/chapters/?tags={tag_cellule.pk}")
        assert "érythropoïèse".encode() not in response.content

    def test_chapter_not_shown_for_wrong_ec(
        self, client, tag_immuno, tag_chapitre, cat_sous_tissu, db
    ):
        tag_hemato = Tag.objects.create(
            name="hemato", moodle_id=998, category=cat_sous_tissu
        )
        tag_chapitre.parent_ec = tag_immuno  # linked to immuno, NOT hemato
        tag_chapitre.save()
        response = client.get(f"/entrainement/chapters/?tags={tag_hemato.pk}")
        assert "érythropoïèse".encode() not in response.content
