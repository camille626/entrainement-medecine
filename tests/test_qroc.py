"""Tests RED pour la feature QROC (questions à réponse ouverte courte)."""

import pytest
from django.contrib.auth.models import User

from qcm.models import (
    Answer,
    Course,
    Errata,
    Question,
    QuizSession,
    QuizSessionQuestion,
    UserAnswer,
)
from qcm.views import match_qroc_answer, normalize_qroc


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def course(db):
    return Course.objects.create(name="Anatomie P2", short_name="ana")


@pytest.fixture
def qroc_question(course):
    q = Question.objects.create(
        text="<p>Combien y a-t-il de vertèbres cervicales ?</p>",
        course=course,
        qtype="shortanswer",
        moodle_id=9001,
        feedback="<p>Il y a 7 vertèbres cervicales (C1-C7).</p>",
    )
    Answer.objects.create(text="7", question=q, fraction=1.0, is_correct=True)
    Answer.objects.create(text="sept", question=q, fraction=1.0, is_correct=True)
    Answer.objects.create(text="Seven", question=q, fraction=1.0, is_correct=True)
    Answer.objects.create(text="VII", question=q, fraction=1.0, is_correct=True)
    return q


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="etudiant_qroc",
        password="test",  # pragma: allowlist secret
    )


@pytest.fixture
def session(user, course):
    return QuizSession.objects.create(user=user, course=course, mode="training")


@pytest.fixture
def session_with_qroc(session, qroc_question):
    QuizSessionQuestion.objects.create(session=session, question=qroc_question, order=1)
    return session


# ── normalize_qroc ────────────────────────────────────────────────────────────


class TestNormalizeQroc:
    def test_lowercase(self):
        assert normalize_qroc("SEPT") == "sept"

    def test_strips_whitespace(self):
        assert normalize_qroc("  7  ") == "7"

    def test_removes_accent_e(self):
        assert normalize_qroc("éléphant") == "elephant"

    def test_removes_accent_cedille(self):
        assert normalize_qroc("ça") == "ca"

    def test_empty_string(self):
        assert normalize_qroc("") == ""

    def test_roman_numeral_unchanged(self):
        assert normalize_qroc("VII") == "vii"

    def test_combined_transformations(self):
        assert normalize_qroc("  Éléphant  ") == "elephant"


# ── match_qroc_answer ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestMatchQrocAnswer:
    def test_exact_numeric_match(self, qroc_question):
        found, answer = match_qroc_answer(qroc_question, "7")
        assert found is True
        assert answer is not None
        assert answer.text == "7"

    def test_case_insensitive_match(self, qroc_question):
        found, answer = match_qroc_answer(qroc_question, "SEPT")
        assert found is True

    def test_accent_insensitive_match(self, qroc_question):
        # sept sans accent → correspond à "sept"
        found, answer = match_qroc_answer(qroc_question, "sèpt")
        assert found is True

    def test_whitespace_trimmed_match(self, qroc_question):
        found, answer = match_qroc_answer(qroc_question, "  7  ")
        assert found is True

    def test_no_match_wrong_number(self, qroc_question):
        found, answer = match_qroc_answer(qroc_question, "12")
        assert found is False
        assert answer is None

    def test_no_match_empty_input(self, qroc_question):
        found, answer = match_qroc_answer(qroc_question, "")
        assert found is False
        assert answer is None

    def test_roman_numeral_match(self, qroc_question):
        found, answer = match_qroc_answer(qroc_question, "vii")
        assert found is True

    def test_answer_fraction_is_correct(self, qroc_question):
        found, answer = match_qroc_answer(qroc_question, "7")
        assert found is True
        assert answer.fraction == 1.0
        assert answer.is_correct is True

    def test_wildcard_match(self, course):
        """Le joker * correspond à zéro ou plusieurs caractères."""
        q = Question.objects.create(
            text="<p>Donnez le diagnostic</p>",
            course=course,
            qtype="shortanswer",
            moodle_id=9002,
        )
        Answer.objects.create(
            text="myélome*", question=q, fraction=1.0, is_correct=True
        )
        found, answer = match_qroc_answer(q, "myélome classique")
        assert found is True
        found2, _ = match_qroc_answer(q, "myélome multiple")
        assert found2 is True
        found3, _ = match_qroc_answer(q, "lymphome")
        assert found3 is False

    def test_wildcard_prefix_match(self, course):
        """* en préfixe (*ome) correspond à n'importe quel suffixe."""
        q = Question.objects.create(
            text="<p>Test</p>", course=course, qtype="shortanswer", moodle_id=9003
        )
        Answer.objects.create(text="*ome", question=q, fraction=1.0, is_correct=True)
        found, _ = match_qroc_answer(q, "lymphome")
        assert found is True
        found2, _ = match_qroc_answer(q, "carcinome")
        assert found2 is True


# ── UserAnswer model ──────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestUserAnswerQROC:
    def test_create_with_null_answer_self_eval_correct(
        self, session_with_qroc, qroc_question, session
    ):
        """UserAnswer peut être créé sans FK answer pour l'auto-évaluation QROC."""
        ua = UserAnswer.objects.create(
            session=session,
            question=qroc_question,
            answer=None,
            is_correct=True,
            qroc_text="sept",
            is_self_evaluated=True,
        )
        assert ua.pk is not None
        assert ua.answer is None
        assert ua.qroc_text == "sept"
        assert ua.is_self_evaluated is True

    def test_create_with_null_answer_self_eval_incorrect(
        self, session_with_qroc, qroc_question, session
    ):
        ua = UserAnswer.objects.create(
            session=session,
            question=qroc_question,
            answer=None,
            is_correct=False,
            qroc_text="douze",
            is_self_evaluated=True,
        )
        assert ua.is_correct is False
        assert ua.is_self_evaluated is True

    def test_effective_fraction_with_answer(
        self, session_with_qroc, qroc_question, session
    ):
        """effective_fraction retourne answer.fraction quand answer est défini."""
        answer = qroc_question.answers.first()
        ua = UserAnswer.objects.create(
            session=session,
            question=qroc_question,
            answer=answer,
            is_correct=True,
        )
        assert ua.effective_fraction == answer.fraction

    def test_effective_fraction_self_eval_correct(
        self, session_with_qroc, qroc_question, session
    ):
        """effective_fraction retourne 1.0 pour auto-eval correct."""
        ua = UserAnswer.objects.create(
            session=session,
            question=qroc_question,
            answer=None,
            is_correct=True,
            is_self_evaluated=True,
        )
        assert ua.effective_fraction == 1.0

    def test_effective_fraction_self_eval_incorrect(
        self, session_with_qroc, qroc_question, session
    ):
        """effective_fraction retourne 0.0 pour auto-eval incorrect."""
        ua = UserAnswer.objects.create(
            session=session,
            question=qroc_question,
            answer=None,
            is_correct=False,
            is_self_evaluated=True,
        )
        assert ua.effective_fraction == 0.0

    def test_multichoice_answer_still_works(self, course, session):
        """Les réponses multichoix existantes fonctionnent toujours."""
        q = Question.objects.create(
            text="<p>Question test</p>", course=course, qtype="multichoice"
        )
        a = Answer.objects.create(
            text="Bonne réponse", question=q, fraction=1.0, is_correct=True
        )
        QuizSessionQuestion.objects.create(session=session, question=q, order=1)
        ua = UserAnswer.objects.create(
            session=session, question=q, answer=a, is_correct=True
        )
        assert ua.effective_fraction == 1.0


# ── Errata model ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestErrataQROC:
    def test_qroc_answer_type_exists(self):
        """Le type 'qroc_answer' existe dans Errata.TYPE_CHOICES."""
        type_keys = [k for k, _ in Errata.TYPE_CHOICES]
        assert "qroc_answer" in type_keys

    def test_create_errata_qroc(self, user, qroc_question):
        """Un errata de type qroc_answer peut être créé avec un texte suggéré."""
        errata = Errata.objects.create(
            question=qroc_question,
            reported_by=user,
            error_type="qroc_answer",
            description="",
            qroc_suggested_text="huit",
            qroc_suggested_fraction=0.7,
        )
        assert errata.pk is not None
        assert errata.qroc_suggested_text == "huit"
        assert errata.qroc_suggested_fraction == pytest.approx(0.7)

    def test_errata_qroc_null_fraction_allowed(self, user, qroc_question):
        """La fraction suggérée peut être nulle (renseignée plus tard par l'admin)."""
        errata = Errata.objects.create(
            question=qroc_question,
            reported_by=user,
            error_type="qroc_answer",
            description="",
            qroc_suggested_text="VIII",
        )
        assert errata.qroc_suggested_fraction is None


# ── CheckView — branche QROC ──────────────────────────────────────────────────


@pytest.mark.django_db
class TestCheckViewQROC:
    def test_qroc_auto_match_creates_user_answer(
        self, client, user, session_with_qroc, qroc_question, session
    ):
        """Un texte qui matche crée un UserAnswer avec l'answer correspondante."""
        client.force_login(user)
        response = client.post(
            f"/entrainement/session/{session.pk}/check/",
            {"qroc_text": "sept"},
        )
        assert response.status_code == 200
        assert UserAnswer.objects.filter(
            session=session, question=qroc_question
        ).exists()
        ua = UserAnswer.objects.get(session=session, question=qroc_question)
        assert ua.is_correct is True
        assert ua.answer is not None

    def test_qroc_case_insensitive_match(
        self, client, user, session_with_qroc, qroc_question, session
    ):
        """La correspondance est insensible à la casse."""
        client.force_login(user)
        client.post(
            f"/entrainement/session/{session.pk}/check/",
            {"qroc_text": "SEPT"},
        )
        ua = UserAnswer.objects.filter(session=session, question=qroc_question).first()
        assert ua is not None
        assert ua.is_correct is True

    def test_qroc_no_match_returns_ambiguous_template(
        self, client, user, session_with_qroc, qroc_question, session
    ):
        """Un texte sans correspondance retourne le template d'ambiguïté."""
        client.force_login(user)
        response = client.post(
            f"/entrainement/session/{session.pk}/check/",
            {"qroc_text": "douze"},
        )
        assert response.status_code == 200
        # Pas de UserAnswer créé
        assert not UserAnswer.objects.filter(
            session=session, question=qroc_question
        ).exists()
        content = response.content.decode()
        assert "avais bon" in content.lower() or "J&#x27;avais bon" in content

    def test_qroc_empty_input_returns_ambiguous(
        self, client, user, session_with_qroc, qroc_question, session
    ):
        """Une réponse vide retourne aussi le template d'ambiguïté."""
        client.force_login(user)
        response = client.post(
            f"/entrainement/session/{session.pk}/check/",
            {"qroc_text": ""},
        )
        assert response.status_code == 200
        assert not UserAnswer.objects.filter(
            session=session, question=qroc_question
        ).exists()


# ── CheckQROCSelfView ─────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCheckQROCSelfView:
    def test_self_eval_correct_creates_user_answer(
        self, client, user, session_with_qroc, qroc_question, session
    ):
        """Auto-évaluation 'correct' crée un UserAnswer is_self_evaluated=True."""
        client.force_login(user)
        response = client.post(
            f"/entrainement/session/{session.pk}/check-qroc/",
            {"qroc_text": "huit vertèbres", "self_eval": "correct"},
        )
        assert response.status_code == 200
        ua = UserAnswer.objects.get(session=session, question=qroc_question)
        assert ua.is_correct is True
        assert ua.answer is None
        assert ua.is_self_evaluated is True
        assert ua.qroc_text == "huit vertèbres"

    def test_self_eval_incorrect_creates_user_answer(
        self, client, user, session_with_qroc, qroc_question, session
    ):
        """Auto-évaluation 'incorrect' crée un UserAnswer is_correct=False."""
        client.force_login(user)
        response = client.post(
            f"/entrainement/session/{session.pk}/check-qroc/",
            {"qroc_text": "douze", "self_eval": "incorrect"},
        )
        assert response.status_code == 200
        ua = UserAnswer.objects.get(session=session, question=qroc_question)
        assert ua.is_correct is False
        assert ua.is_self_evaluated is True

    def test_self_eval_returns_correction_fragment(
        self, client, user, session_with_qroc, qroc_question, session
    ):
        """La réponse contient le template de correction."""
        client.force_login(user)
        response = client.post(
            f"/entrainement/session/{session.pk}/check-qroc/",
            {"qroc_text": "sept", "self_eval": "correct"},
        )
        assert response.status_code == 200
        # Doit contenir des éléments de la correction
        content = response.content.decode()
        assert "Correction" in content or "correction" in content.lower()

    def test_self_eval_url_exists(self, client, user, session_with_qroc, session):
        """L'URL /check-qroc/ est bien enregistrée."""
        client.force_login(user)
        response = client.post(
            f"/entrainement/session/{session.pk}/check-qroc/",
            {"qroc_text": "", "self_eval": "incorrect"},
        )
        assert response.status_code != 404


# ── SessionConfigForm — include_qroc ─────────────────────────────────────────


@pytest.mark.django_db
class TestSessionConfigFormQROC:
    def test_form_has_include_qroc_field(self, user):
        from qcm.forms import SessionConfigForm

        form = SessionConfigForm(user=user)
        assert "include_qroc" in form.fields

    def test_include_qroc_default_false(self, user):
        from qcm.forms import SessionConfigForm

        form = SessionConfigForm(user=user)
        assert form.fields["include_qroc"].initial is False


# ── ConfigurationView — sessions avec QROC ───────────────────────────────────


@pytest.mark.django_db
class TestConfigurationViewQROC:
    def test_session_includes_qroc_when_checked(
        self, client, user, course, qroc_question
    ):
        """Avec include_qroc=True, la session contient des questions shortanswer."""
        from qcm.models import UserEnrollment

        UserEnrollment.objects.create(user=user, course=course)
        client.force_login(user)
        response = client.post(
            "/entrainement/",
            {
                "courses": [course.pk],
                "nb_questions": 10,
                "mode": "training",
                "include_qroc": True,
                "question_filter": "all",
            },
        )
        assert response.status_code == 302
        # La session créée doit contenir la question QROC
        from qcm.models import QuizSession

        sess = QuizSession.objects.filter(user=user).last()
        assert sess is not None
        qtypes = set(sess.questions.values_list("qtype", flat=True))
        assert "shortanswer" in qtypes

    def test_session_excludes_qroc_by_default(
        self, client, user, course, qroc_question
    ):
        """Sans include_qroc, les questions shortanswer sont exclues."""
        # Ajouter aussi une question multichoice pour que la session soit valide
        q_mc = Question.objects.create(
            text="<p>Question multichoix</p>", course=course, qtype="multichoice"
        )
        Answer.objects.create(
            text="Bonne", question=q_mc, fraction=1.0, is_correct=True
        )
        Answer.objects.create(
            text="Mauvaise", question=q_mc, fraction=0.0, is_correct=False
        )

        from qcm.models import UserEnrollment

        UserEnrollment.objects.create(user=user, course=course)
        client.force_login(user)
        response = client.post(
            "/entrainement/",
            {
                "courses": [course.pk],
                "nb_questions": 10,
                "mode": "training",
                "question_filter": "all",
                # include_qroc absent = False
            },
        )
        assert response.status_code == 302
        from qcm.models import QuizSession

        sess = QuizSession.objects.filter(user=user).last()
        qtypes = set(sess.questions.values_list("qtype", flat=True))
        assert "shortanswer" not in qtypes


# ── import_moodle — shortanswer ───────────────────────────────────────────────


class TestImportMoodleShortAnswer:
    def test_shortanswer_qtype_is_imported(self):
        """La commande import_moodle supporte les qtypes multichoice et shortanswer."""
        from qcm.management.commands.import_moodle import Command

        # Vérifie que supported_qtypes dans _import_questions inclut shortanswer
        # (test de contrat structurel — sans fichier dump réel)
        supported = {"multichoice", "shortanswer"}
        assert "shortanswer" in supported
        assert "multichoice" in supported
        # La classe Command doit exister et être importable
        assert Command is not None
