"""Tests for the trophy system."""

import pytest
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import IntegrityError
from django.test import RequestFactory

from qcm.models import (
    Answer,
    Course,
    Errata,
    LoginEvent,
    Question,
    QuizSession,
    QuizSessionQuestion,
    Trophy,
    UserAnswer,
    UserTrophy,
)
from qcm.trophies import award_login_trophies, check_and_award_trophies


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def course(db):
    return Course.objects.create(name="Immunologie", short_name="immuno")


@pytest.fixture
def question(course):
    return Question.objects.create(
        text="Question test",
        course=course,
        qtype="multichoice",
        moodle_id=9001,
    )


@pytest.fixture
def answer(question):
    return Answer.objects.create(
        text="Bonne réponse",
        question=question,
        fraction=1.0,
        is_correct=True,
    )


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="etudiant_trophee",
        password="test",  # pragma: allowlist secret
    )


@pytest.fixture
def session(user, course):
    return QuizSession.objects.create(user=user, course=course, mode="training")


@pytest.fixture
def fake_request(user):
    """Request avec Django messages activé."""
    factory = RequestFactory()
    request = factory.get("/")
    request.user = user
    # Activer le storage messages
    request.session = {}
    messages_storage = FallbackStorage(request)
    request._messages = messages_storage
    return request


def _add_answers(session, question, answer, count: int) -> None:
    """Helper : créer `count` sessions distinctes avec une UserAnswer chacune."""
    for i in range(count):
        s = QuizSession.objects.create(
            user=session.user, course=session.course, mode="training"
        )
        q = Question.objects.create(
            text=f"Q{i}",
            course=question.course,
            qtype="multichoice",
            moodle_id=90000 + i,
        )
        sq = QuizSessionQuestion.objects.create(session=s, question=q, order=1)
        UserAnswer.objects.create(session=s, question=q, answer=answer, is_correct=True)
        _ = sq


# ---------------------------------------------------------------------------
# Trophy model tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTrophyModel:
    def test_create_bronze_trophy(self, db):
        t = Trophy.objects.create(
            name="Curieux",
            description="10 questions réalisées",
            icon_emoji="🔍",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.QUESTIONS_COUNT,
            condition_value=10,
        )
        assert t.pk is not None
        assert t.rarity == Trophy.BRONZE

    def test_trophy_name_unique(self, db):
        Trophy.objects.create(
            name="Unique",
            description="desc",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.QUESTIONS_COUNT,
            condition_value=1,
        )
        with pytest.raises(IntegrityError):
            Trophy.objects.create(
                name="Unique",
                description="autre",
                rarity=Trophy.GOLD,
                condition_type=Trophy.QUESTIONS_COUNT,
                condition_value=1,
            )

    def test_str_representation(self, db):
        t = Trophy.objects.create(
            name="Test Trophée",
            description="desc",
            rarity=Trophy.SILVER,
            condition_type=Trophy.SESSIONS_COUNT,
            condition_value=5,
        )
        assert "Test Trophée" in str(t)


@pytest.mark.django_db
class TestUserTrophyModel:
    def test_create_user_trophy(self, user, db):
        t = Trophy.objects.create(
            name="T1",
            description="d",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.QUESTIONS_COUNT,
            condition_value=1,
        )
        ut = UserTrophy.objects.create(user=user, trophy=t)
        assert ut.pk is not None
        assert ut.unlocked_at is not None

    def test_unique_together(self, user, db):
        t = Trophy.objects.create(
            name="T2",
            description="d",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.QUESTIONS_COUNT,
            condition_value=1,
        )
        UserTrophy.objects.create(user=user, trophy=t)
        with pytest.raises(IntegrityError):
            UserTrophy.objects.create(user=user, trophy=t)


# ---------------------------------------------------------------------------
# check_and_award_trophies service tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCheckAndAwardTrophies:
    def test_awards_questions_count_trophy(
        self, user, session, question, answer, fake_request
    ):
        """Un trophée questions_count se débloque quand le seuil est atteint."""
        t = Trophy.objects.create(
            name="Curieux",
            description="10 questions",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.QUESTIONS_COUNT,
            condition_value=2,
        )
        # Créer 2 UserAnswers dans 2 sessions distinctes
        _add_answers(session, question, answer, 2)

        newly = check_and_award_trophies(fake_request, session)
        assert t in newly
        assert UserTrophy.objects.filter(user=user, trophy=t).exists()

    def test_no_award_below_threshold(
        self, user, session, question, answer, fake_request
    ):
        """Pas de trophée si le seuil n'est pas encore atteint."""
        Trophy.objects.create(
            name="Marathonien",
            description="1000 questions",
            rarity=Trophy.GOLD,
            condition_type=Trophy.QUESTIONS_COUNT,
            condition_value=1000,
        )
        _add_answers(session, question, answer, 1)

        newly = check_and_award_trophies(fake_request, session)
        assert newly == []

    def test_no_duplicate_trophy(self, user, session, question, answer, fake_request):
        """Appeler check 2 fois ne duplique pas le trophée."""
        t = Trophy.objects.create(
            name="Dup Test",
            description="desc",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.QUESTIONS_COUNT,
            condition_value=1,
        )
        _add_answers(session, question, answer, 1)

        check_and_award_trophies(fake_request, session)
        check_and_award_trophies(fake_request, session)

        assert UserTrophy.objects.filter(user=user, trophy=t).count() == 1

    def test_awards_correct_count_trophy(
        self, user, session, question, answer, fake_request
    ):
        """Un trophée correct_count compte les réponses correctes."""
        t = Trophy.objects.create(
            name="Chirurgical",
            description="2 bonnes réponses",
            rarity=Trophy.SILVER,
            condition_type=Trophy.CORRECT_COUNT,
            condition_value=2,
        )
        _add_answers(session, question, answer, 2)

        newly = check_and_award_trophies(fake_request, session)
        assert t in newly

    def test_awards_sessions_count_trophy(
        self, user, session, question, answer, fake_request
    ):
        """Un trophée sessions_count compte les sessions ≥ 10 questions complétées."""
        t = Trophy.objects.create(
            name="Première Victoire",
            description="1 session",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.SESSIONS_COUNT,
            condition_value=1,
        )
        # Créer une session complète avec 10 questions (seuil minimum)
        for i in range(10):
            q = Question.objects.create(
                text=f"Q session {i}",
                course=question.course,
                qtype="multichoice",
                moodle_id=70000 + i,
            )
            QuizSessionQuestion.objects.create(session=session, question=q, order=i + 1)
            UserAnswer.objects.create(
                session=session, question=q, answer=answer, is_correct=True
            )

        newly = check_and_award_trophies(fake_request, session)
        assert t in newly

    def test_sessions_count_ignores_short_sessions(
        self, user, session, question, answer, fake_request
    ):
        """Une session de moins de 10 questions ne compte pas."""
        Trophy.objects.create(
            name="Première Victoire Courte",
            description="1 session",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.SESSIONS_COUNT,
            condition_value=1,
        )
        # Session avec seulement 5 questions
        for i in range(5):
            q = Question.objects.create(
                text=f"Q courte {i}",
                course=question.course,
                qtype="multichoice",
                moodle_id=71000 + i,
            )
            QuizSessionQuestion.objects.create(session=session, question=q, order=i + 1)
            UserAnswer.objects.create(
                session=session, question=q, answer=answer, is_correct=True
            )

        newly = check_and_award_trophies(fake_request, session)
        assert newly == []

    def test_awards_perfect_session_trophy(
        self, user, session, question, answer, fake_request
    ):
        """Un trophée perfect_session se débloque sur une session 100%."""
        t = Trophy.objects.create(
            name="Perfectionniste",
            description="20/20",
            rarity=Trophy.SILVER,
            condition_type=Trophy.PERFECT_SESSION,
            condition_value=1,
        )
        sq = QuizSessionQuestion.objects.create(
            session=session, question=question, order=1
        )
        UserAnswer.objects.create(
            session=session, question=question, answer=answer, is_correct=True
        )
        _ = sq

        newly = check_and_award_trophies(fake_request, session)
        assert t in newly

    def test_perfect_session_not_awarded_if_wrong(
        self, user, session, question, answer, fake_request
    ):
        """perfect_session ne se débloque pas si au moins une réponse est fausse."""
        wrong_answer = Answer.objects.create(
            text="Mauvaise", question=question, fraction=0.0, is_correct=False
        )
        t = Trophy.objects.create(
            name="Perfectionniste2",
            description="20/20",
            rarity=Trophy.SILVER,
            condition_type=Trophy.PERFECT_SESSION,
            condition_value=1,
        )
        sq = QuizSessionQuestion.objects.create(
            session=session, question=question, order=1
        )
        UserAnswer.objects.create(
            session=session, question=question, answer=wrong_answer, is_correct=False
        )
        _ = sq

        newly = check_and_award_trophies(fake_request, session)
        assert t not in newly

    def test_message_added_for_new_trophy(
        self, user, session, question, answer, fake_request
    ):
        """Un message Django est ajouté lors du déblocage d'un trophée."""
        Trophy.objects.create(
            name="Message Test",
            description="desc",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.QUESTIONS_COUNT,
            condition_value=1,
        )
        _add_answers(session, question, answer, 1)

        check_and_award_trophies(fake_request, session)

        msgs = list(get_messages(fake_request))
        trophy_msgs = [m for m in msgs if "trophy" in m.tags]
        assert len(trophy_msgs) == 1
        assert "Message Test" in trophy_msgs[0].message

    def test_already_earned_not_re_awarded(
        self, user, session, question, answer, fake_request
    ):
        """Un trophée déjà gagné n'est pas ré-attribué."""
        t = Trophy.objects.create(
            name="Déjà gagné",
            description="desc",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.QUESTIONS_COUNT,
            condition_value=1,
        )
        UserTrophy.objects.create(user=user, trophy=t)
        _add_answers(session, question, answer, 5)

        newly = check_and_award_trophies(fake_request, session)
        assert t not in newly

    def test_perfect_session_not_awarded_if_partial_credit(
        self, user, session, question, fake_request
    ):
        """perfect_session ne se débloque pas si une question n'a qu'un crédit partiel.

        Cas typique : question à 2 bonnes réponses (0.5 chacune), user n'en sélectionne qu'une.
        is_correct=True mais score effectif = 0.5, pas 1.0.
        """
        partial_answer = Answer.objects.create(
            text="Réponse partielle A",
            question=question,
            fraction=0.5,
            is_correct=True,
        )
        Answer.objects.create(
            text="Réponse partielle B",
            question=question,
            fraction=0.5,
            is_correct=True,
        )
        t = Trophy.objects.create(
            name="Perfectionniste Partiel",
            description="20/20",
            rarity=Trophy.SILVER,
            condition_type=Trophy.PERFECT_SESSION,
            condition_value=1,
        )
        sq = QuizSessionQuestion.objects.create(
            session=session, question=question, order=1
        )
        # User sélectionne uniquement la réponse A (score 0.5, pas 1.0)
        UserAnswer.objects.create(
            session=session, question=question, answer=partial_answer, is_correct=True
        )
        _ = sq

        newly = check_and_award_trophies(fake_request, session)
        assert t not in newly

    def test_awards_erratas_accepted_trophy(
        self, user, session, question, fake_request
    ):
        """Un trophée erratas_accepted se débloque quand le seuil d'erratas acceptés est atteint."""
        t = Trophy.objects.create(
            name="Vision d'Aigle",
            description="5 erratas acceptés",
            rarity=Trophy.SILVER,
            condition_type=Trophy.ERRATAS_ACCEPTED,
            condition_value=3,
        )
        for _ in range(3):
            Errata.objects.create(
                question=question,
                reported_by=user,
                error_type=Errata.OTHER,
                status=Errata.ACCEPTED,
            )

        newly = check_and_award_trophies(fake_request, session)
        assert t in newly

    def test_erratas_pending_not_counted(self, user, session, question, fake_request):
        """Les erratas en attente ou refusés ne comptent pas."""
        Trophy.objects.create(
            name="Vision d'Aigle 2",
            description="3 erratas acceptés",
            rarity=Trophy.SILVER,
            condition_type=Trophy.ERRATAS_ACCEPTED,
            condition_value=3,
        )
        for _ in range(3):
            Errata.objects.create(
                question=question,
                reported_by=user,
                error_type=Errata.OTHER,
                status=Errata.PENDING,
            )

        newly = check_and_award_trophies(fake_request, session)
        assert newly == []

    def test_awards_zero_score_count_trophy(
        self, user, session, question, fake_request
    ):
        """Un trophée zero_score_count se débloque sur les questions à 0 point."""
        wrong_answer = Answer.objects.create(
            text="Mauvaise réponse",
            question=question,
            fraction=0.0,
            is_correct=False,
        )
        t = Trophy.objects.create(
            name="Dazed and Confused",
            description="50 questions à 0 point",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.ZERO_SCORE_COUNT,
            condition_value=2,
        )
        # Créer 2 (session, question) distincts avec score = 0
        for i in range(2):
            s = QuizSession.objects.create(
                user=session.user, course=session.course, mode="training"
            )
            q = Question.objects.create(
                text=f"Q zero {i}",
                course=question.course,
                qtype="multichoice",
                moodle_id=80000 + i,
            )
            QuizSessionQuestion.objects.create(session=s, question=q, order=1)
            UserAnswer.objects.create(
                session=s, question=q, answer=wrong_answer, is_correct=False
            )

        newly = check_and_award_trophies(fake_request, session)
        assert t in newly

    def test_awards_zero_score_count_tag_trophy(
        self, user, session, question, fake_request
    ):
        """Un trophée zero_score_count_tag se débloque sur les questions 0 point d'un tag."""
        from qcm.models import Tag, TagCategory

        tag_cat = TagCategory.objects.create(
            name="EC", tag_type="ec", course=session.course
        )
        tag = Tag.objects.create(name="ECG", course=session.course, category=tag_cat)
        question.tags.add(tag)

        wrong_answer = Answer.objects.create(
            text="Mauvaise ECG",
            question=question,
            fraction=0.0,
            is_correct=False,
        )
        t = Trophy.objects.create(
            name="ST+",
            description="0 pts sur 2 questions ECG",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.ZERO_SCORE_COUNT_TAG,
            condition_value=2,
            condition_tag=tag,
        )
        for i in range(2):
            s = QuizSession.objects.create(
                user=session.user, course=session.course, mode="training"
            )
            q = Question.objects.create(
                text=f"Q ECG {i}",
                course=question.course,
                qtype="multichoice",
                moodle_id=60000 + i,
            )
            q.tags.add(tag)
            QuizSessionQuestion.objects.create(session=s, question=q, order=1)
            UserAnswer.objects.create(
                session=s, question=q, answer=wrong_answer, is_correct=False
            )

        newly = check_and_award_trophies(fake_request, session)
        assert t in newly

    def test_zero_score_count_tag_not_triggered_by_other_tags(
        self, user, session, question, answer, fake_request
    ):
        """zero_score_count_tag ne se débloque pas sur des questions d'un autre tag."""
        from qcm.models import Tag, TagCategory

        tag_cat = TagCategory.objects.create(
            name="EC2", tag_type="ec", course=session.course
        )
        ecg_tag = Tag.objects.create(
            name="ECG2", course=session.course, category=tag_cat
        )

        t = Trophy.objects.create(
            name="ST+ other",
            description="0 pts sur 1 question ECG",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.ZERO_SCORE_COUNT_TAG,
            condition_value=1,
            condition_tag=ecg_tag,
        )
        # Créer une question sans le tag ECG, avec score 0
        wrong_answer = Answer.objects.create(
            text="Mauvaise hors tag",
            question=question,
            fraction=0.0,
            is_correct=False,
        )
        s = QuizSession.objects.create(
            user=session.user, course=session.course, mode="training"
        )
        q = Question.objects.create(
            text="Q sans tag ECG",
            course=question.course,
            qtype="multichoice",
            moodle_id=60099,
        )
        QuizSessionQuestion.objects.create(session=s, question=q, order=1)
        UserAnswer.objects.create(
            session=s, question=q, answer=wrong_answer, is_correct=False
        )

        newly = check_and_award_trophies(fake_request, session)
        assert t not in newly

    def test_zero_score_not_counted_if_partial_credit(
        self, user, session, question, fake_request
    ):
        """Une question avec un score partiel (> 0) ne compte pas pour zero_score_count."""
        partial_answer = Answer.objects.create(
            text="Partielle",
            question=question,
            fraction=0.5,
            is_correct=True,
        )
        Trophy.objects.create(
            name="Dazed Zero",
            description="1 question à 0 point",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.ZERO_SCORE_COUNT,
            condition_value=1,
        )
        s = QuizSession.objects.create(
            user=session.user, course=session.course, mode="training"
        )
        q = Question.objects.create(
            text="Q partielle",
            course=question.course,
            qtype="multichoice",
            moodle_id=80099,
        )
        QuizSessionQuestion.objects.create(session=s, question=q, order=1)
        UserAnswer.objects.create(
            session=s, question=q, answer=partial_answer, is_correct=True
        )

        newly = check_and_award_trophies(fake_request, session)
        assert newly == []


# ---------------------------------------------------------------------------
# Login-based trophy tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLoginTrophies:
    def test_login_count_trophy(self, user, fake_request):
        """Un trophée login_count se débloque après N connexions."""
        t = Trophy.objects.create(
            name="Premier Pas",
            description="3 connexions",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.LOGIN_COUNT,
            condition_value=3,
        )
        for _ in range(3):
            LoginEvent.objects.create(user=user)

        newly = award_login_trophies(fake_request, user)
        assert t in newly

    def test_login_count_not_awarded_below_threshold(self, user, fake_request):
        """Pas de trophée si le nombre de connexions est insuffisant."""
        Trophy.objects.create(
            name="Assidu Connexion",
            description="10 connexions",
            rarity=Trophy.SILVER,
            condition_type=Trophy.LOGIN_COUNT,
            condition_value=10,
        )
        LoginEvent.objects.create(user=user)

        newly = award_login_trophies(fake_request, user)
        assert newly == []

    def test_consecutive_days_trophy(self, user, fake_request):
        """Un trophée consecutive_days se débloque sur une série de jours consécutifs."""
        from datetime import timedelta

        from django.utils import timezone

        t = Trophy.objects.create(
            name="Série de 3",
            description="3 jours consécutifs",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.CONSECUTIVE_DAYS,
            condition_value=3,
        )
        now = timezone.now()
        for delta in range(3):
            e = LoginEvent.objects.create(user=user)
            LoginEvent.objects.filter(pk=e.pk).update(
                logged_at=now - timedelta(days=2 - delta)
            )

        newly = award_login_trophies(fake_request, user)
        assert t in newly

    def test_consecutive_days_broken_streak(self, user, fake_request):
        """Une série interrompue ne déclenche pas le trophée si le seuil n'est pas atteint."""
        from datetime import timedelta

        from django.utils import timezone

        Trophy.objects.create(
            name="Série de 5",
            description="5 jours consécutifs",
            rarity=Trophy.SILVER,
            condition_type=Trophy.CONSECUTIVE_DAYS,
            condition_value=5,
        )
        now = timezone.now()
        # Connexions J, J-1, J-3 (trou au J-2 → max streak = 2)
        for delta in [0, 1, 3]:
            e = LoginEvent.objects.create(user=user)
            LoginEvent.objects.filter(pk=e.pk).update(
                logged_at=now - timedelta(days=delta)
            )

        newly = award_login_trophies(fake_request, user)
        assert newly == []

    def test_award_login_trophy_does_not_duplicate(self, user, fake_request):
        """Appeler award_login_trophies 2 fois ne duplique pas le trophée."""
        t = Trophy.objects.create(
            name="Fidèle",
            description="1 connexion",
            rarity=Trophy.BRONZE,
            condition_type=Trophy.LOGIN_COUNT,
            condition_value=1,
        )
        LoginEvent.objects.create(user=user)

        award_login_trophies(fake_request, user)
        award_login_trophies(fake_request, user)

        assert UserTrophy.objects.filter(user=user, trophy=t).count() == 1
