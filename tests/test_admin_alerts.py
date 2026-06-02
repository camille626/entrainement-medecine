"""Tests pour les alertes admin en navbar (issue #26)."""

from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import User

from qcm.models import (
    Answer,
    Category,
    Course,
    Errata,
    Question,
    RegistrationRequest,
    Semester,
    StudyYear,
)


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="admin",
        password="pass",  # pragma: allowlist secret
        is_staff=True,
    )


@pytest.fixture
def regular_user(db):
    return User.objects.create_user(
        username="student",
        password="pass",  # pragma: allowlist secret
        is_staff=False,
    )


@pytest.fixture
def question(db, staff_user):
    year = StudyYear.objects.create(name="P2", order=1)
    semester = Semester.objects.create(name="S1", study_year=year, order=1)
    course = Course.objects.create(name="Cours test", moodle_id=9999)
    semester.courses.add(course)
    category = Category.objects.create(name="Cat test", course=course, moodle_id=8888)
    q = Question.objects.create(text="Question test", category=category, moodle_id=7777)
    Answer.objects.create(text="A", question=q, fraction=1.0, is_correct=True)
    return q


# ── Context processor ────────────────────────────────────────────────────────


class TestAdminAlertsContextProcessor:
    def _make_request(self, user):
        req = MagicMock()
        req.user = user
        return req

    def test_non_staff_gets_zero_counts(self, regular_user, db):
        from qcm.context_processors import notifications

        result = notifications(self._make_request(regular_user))
        assert result["admin_alert_count"] == 0
        assert result["admin_pending_erratas"] == 0
        assert result["admin_pending_registrations"] == 0

    def test_staff_gets_zero_when_nothing_pending(self, staff_user, db):
        from qcm.context_processors import notifications

        result = notifications(self._make_request(staff_user))
        assert result["admin_alert_count"] == 0

    def test_staff_counts_pending_erratas(self, staff_user, question, db):
        from qcm.context_processors import notifications

        Errata.objects.create(
            question=question,
            reported_by=staff_user,
            error_type=Errata.POINTS,
            description="test",
            status=Errata.PENDING,
        )
        result = notifications(self._make_request(staff_user))
        assert result["admin_pending_erratas"] == 1
        assert result["admin_alert_count"] == 1

    def test_staff_counts_pending_registrations(self, staff_user, db):
        from qcm.context_processors import notifications

        RegistrationRequest.objects.create(
            first_name="Alice",
            last_name="Dupont",
            email="alice@test.com",
            year="PASS",
            parcours="",
            status=RegistrationRequest.PENDING,
        )
        result = notifications(self._make_request(staff_user))
        assert result["admin_pending_registrations"] == 1
        assert result["admin_alert_count"] == 1

    def test_staff_alert_count_is_sum(self, staff_user, question, db):
        from qcm.context_processors import notifications

        Errata.objects.create(
            question=question,
            reported_by=staff_user,
            error_type=Errata.POINTS,
            description="test",
            status=Errata.PENDING,
        )
        RegistrationRequest.objects.create(
            first_name="Bob",
            last_name="Martin",
            email="bob@test.com",
            year="PASS",
            parcours="",
            status=RegistrationRequest.PENDING,
        )
        result = notifications(self._make_request(staff_user))
        assert result["admin_pending_erratas"] == 1
        assert result["admin_pending_registrations"] == 1
        assert result["admin_alert_count"] == 2

    def test_accepted_erratas_not_counted(self, staff_user, question, db):
        from qcm.context_processors import notifications

        Errata.objects.create(
            question=question,
            reported_by=staff_user,
            error_type=Errata.POINTS,
            description="test",
            status=Errata.ACCEPTED,
        )
        result = notifications(self._make_request(staff_user))
        assert result["admin_pending_erratas"] == 0


# ── Navbar HTML ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestAdminAlertsNavbar:
    def test_badge_visible_for_staff_with_pending_erratas(
        self, client, staff_user, question
    ):
        Errata.objects.create(
            question=question,
            reported_by=staff_user,
            error_type=Errata.POINTS,
            description="test",
            status=Errata.PENDING,
        )
        client.force_login(staff_user)
        response = client.get("/")
        assert response.status_code == 200
        assert b"admin-alert-badge" in response.content

    def test_badge_not_visible_for_regular_user(self, client, regular_user, question):
        Errata.objects.create(
            question=question,
            reported_by=regular_user,
            error_type=Errata.POINTS,
            description="test",
            status=Errata.PENDING,
        )
        client.force_login(regular_user)
        response = client.get("/")
        assert response.status_code == 200
        assert b"admin-alert-badge" not in response.content

    def test_badge_not_visible_when_nothing_pending(self, client, staff_user):
        client.force_login(staff_user)
        response = client.get("/")
        assert response.status_code == 200
        assert b"admin-alert-badge" not in response.content
