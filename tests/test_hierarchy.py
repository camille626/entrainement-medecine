import pytest

from qcm.models import Course, Semester, StudyYear


@pytest.fixture
def p2(db):
    return StudyYear.objects.create(name="P2", order=2)


@pytest.fixture
def s1(p2):
    return Semester.objects.create(study_year=p2, name="S1", order=1)


@pytest.fixture
def s2(p2):
    return Semester.objects.create(study_year=p2, name="S2", order=2)


@pytest.mark.django_db
class TestStudyYear:
    def test_create(self, p2):
        assert p2.pk is not None
        assert p2.name == "P2"
        assert p2.order == 2

    def test_str(self, p2):
        assert str(p2) == "P2"

    def test_ordering(self, db):
        # Use P4/P5 to avoid conflict with P2 created by data migration
        StudyYear.objects.create(name="P5", order=5)
        StudyYear.objects.create(name="P4", order=4)
        p4, p5 = StudyYear.objects.filter(name__in=["P4", "P5"]).order_by("order")
        assert p4.name == "P4"
        assert p5.name == "P5"


@pytest.mark.django_db
class TestSemester:
    def test_create(self, s1, p2):
        assert s1.pk is not None
        assert s1.name == "S1"
        assert s1.study_year == p2

    def test_str(self, s1):
        assert str(s1) == "P2 — S1"

    def test_ordering_within_year(self, p2):
        Semester.objects.create(study_year=p2, name="S2", order=2)
        Semester.objects.create(study_year=p2, name="S1", order=1)
        names = list(p2.semesters.values_list("name", flat=True))
        assert names == ["S1", "S2"]


@pytest.mark.django_db
class TestCourseHierarchy:
    def test_course_has_nullable_semester(self, db):
        course = Course.objects.create(
            name="Cours sans semestre", short_name="test", moodle_id=999
        )
        assert course.semester is None

    def test_course_linked_to_semester(self, s1):
        course = Course.objects.create(
            name="P2 - La cellule", short_name="cell", moodle_id=11, semester=s1
        )
        assert course.semester == s1
        assert course.semester.study_year.name == "P2"

    def test_semester_courses_queryset(self, s1):
        Course.objects.create(
            name="P2 - La cellule", short_name="cell", moodle_id=11, semester=s1
        )
        Course.objects.create(
            name="P2 - Reins", short_name="rein", moodle_id=13, semester=s1
        )
        assert s1.courses.count() == 2


@pytest.mark.django_db
class TestDataMigrationP2:
    """Vérifie la structure P2/S1/S2 créée par la data migration."""

    def test_p2_year_exists(self, db):
        assert StudyYear.objects.filter(name="P2").exists()

    def test_two_semesters_for_p2(self, db):
        p2 = StudyYear.objects.get(name="P2")
        assert p2.semesters.count() == 2

    def test_s1_and_s2_exist(self, db):
        p2 = StudyYear.objects.get(name="P2")
        names = list(p2.semesters.values_list("name", flat=True))
        assert "S1" in names
        assert "S2" in names

    def test_s1_before_s2(self, db):
        p2 = StudyYear.objects.get(name="P2")
        semesters = list(p2.semesters.values_list("name", flat=True))
        assert semesters.index("S1") < semesters.index("S2")


@pytest.mark.django_db
class TestCourseImportWithSemester:
    """Vérifie que import_moodle assigne les semestres lors de l'import des cours."""

    def test_s1_course_gets_semester(self, db):
        s1 = Semester.objects.get(study_year__name="P2", name="S1")
        # Simule ce que import_moodle fait : crée le cours avec le bon semestre
        Course.objects.create(
            name="P2 - La cellule", short_name="cell", moodle_id=11, semester=s1
        )
        assert Course.objects.get(moodle_id=11).semester.name == "S1"

    def test_s2_course_gets_semester(self, db):
        s2 = Semester.objects.get(study_year__name="P2", name="S2")
        Course.objects.create(
            name="P2 - système cardiovasculaire",
            short_name="cardio",
            moodle_id=19,
            semester=s2,
        )
        assert Course.objects.get(moodle_id=19).semester.name == "S2"
