"""Tests pour les inscriptions aux cours (issue #28)."""

import pytest
from django.contrib.auth.models import User

from qcm.models import (
    Answer,
    Category,
    Course,
    Question,
    Semester,
    StudyYear,
    UserEnrollment,
)


@pytest.fixture
def study_year(db):
    return StudyYear.objects.create(name="P2", order=2)


@pytest.fixture
def semester_s1(study_year):
    return Semester.objects.create(study_year=study_year, name="S1", order=1)


@pytest.fixture
def semester_s2(study_year):
    return Semester.objects.create(study_year=study_year, name="S2", order=2)


@pytest.fixture
def course_cellule(semester_s1):
    return Course.objects.create(
        name="P2 - La cellule", short_name="cell", moodle_id=11, semester=semester_s1
    )


@pytest.fixture
def course_cardio(semester_s2):
    return Course.objects.create(
        name="P2 - Cardiovasculaire",
        short_name="cardio",
        moodle_id=19,
        semester=semester_s2,
    )


@pytest.fixture
def student(db):
    return User.objects.create_user(
        username="etudiant",
        password="pass",  # pragma: allowlist secret
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin",
        password="pass",  # pragma: allowlist secret
        is_staff=True,
    )


@pytest.fixture
def question(course_cellule):
    cat = Category.objects.create(name="Cat", course=course_cellule, moodle_id=999)
    q = Question.objects.create(
        text="Q", category=cat, qtype="multichoice", moodle_id=9999
    )
    Answer.objects.create(text="A", question=q, fraction=1.0, is_correct=True)
    return q


# ---------------------------------------------------------------------------
# Tests du modèle UserEnrollment
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUserEnrollment:
    def test_create_enrollment(self, student, course_cellule):
        enr = UserEnrollment.objects.create(user=student, course=course_cellule)
        assert enr.pk is not None
        assert enr.enrolled_at is not None

    def test_unique_enrollment(self, student, course_cellule):
        from django.db import IntegrityError

        UserEnrollment.objects.create(user=student, course=course_cellule)
        with pytest.raises(IntegrityError):
            UserEnrollment.objects.create(user=student, course=course_cellule)

    def test_str(self, student, course_cellule):
        enr = UserEnrollment.objects.create(user=student, course=course_cellule)
        assert student.username in str(enr) or course_cellule.name in str(enr)


# ---------------------------------------------------------------------------
# Tests filtrage des cours dans la configuration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCourseFilterInConfig:
    def test_unenrolled_user_sees_no_courses(self, client, student, course_cellule):
        client.force_login(student)
        response = client.get("/entrainement/")
        assert b"La cellule" not in response.content

    def test_enrolled_user_sees_their_courses(self, client, student, course_cellule):
        UserEnrollment.objects.create(user=student, course=course_cellule)
        client.force_login(student)
        response = client.get("/entrainement/")
        assert b"La cellule" in response.content

    def test_enrolled_user_doesnt_see_other_courses(
        self, client, student, course_cellule, course_cardio
    ):
        UserEnrollment.objects.create(user=student, course=course_cellule)
        client.force_login(student)
        response = client.get("/entrainement/")
        assert b"Cardiovasculaire" not in response.content

    def test_staff_user_sees_all_courses(
        self, client, admin_user, course_cellule, course_cardio
    ):
        client.force_login(admin_user)
        response = client.get("/entrainement/")
        assert b"La cellule" in response.content
        assert b"Cardiovasculaire" in response.content


# ---------------------------------------------------------------------------
# Tests de la session : seules les questions des cours inscrits sont sélectionnées
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestSessionEnrollmentFilter:
    def test_cannot_start_session_with_unenrolled_course(
        self, client, student, course_cellule, question
    ):
        client.force_login(student)
        client.post(
            "/entrainement/",
            {"courses": [course_cellule.pk], "mode": "training", "nb_questions": 1},
        )
        # Without enrollment, the course should not be in the form choices
        # so the form should be invalid and no session created
        from qcm.models import QuizSession

        assert QuizSession.objects.count() == 0
