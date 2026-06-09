"""Service d'attribution des trophées utilisateur."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpRequest

from .models import Errata, LoginEvent, QuizSession, Trophy, UserAnswer, UserTrophy


def _count_questions(user_id: int) -> int:
    """Nombre de (session, question) distincts répondus par l'utilisateur."""
    return (
        UserAnswer.objects.filter(session__user_id=user_id)
        .values("session_id", "question_id")
        .distinct()
        .count()
    )


def _count_correct(user_id: int) -> int:
    """Nombre de (session, question) distincts répondus correctement."""
    return (
        UserAnswer.objects.filter(session__user_id=user_id, is_correct=True)
        .values("session_id", "question_id")
        .distinct()
        .count()
    )


def _count_questions_tag(user_id: int, tag_id: int) -> int:
    """Nombre de (session, question) distincts répondus pour un tag donné."""
    return (
        UserAnswer.objects.filter(
            session__user_id=user_id,
            question__tags__id=tag_id,
        )
        .values("session_id", "question_id")
        .distinct()
        .count()
    )


def _count_correct_tag(user_id: int, tag_id: int) -> int:
    """Nombre de (session, question) correctes pour un tag donné."""
    return (
        UserAnswer.objects.filter(
            session__user_id=user_id,
            is_correct=True,
            question__tags__id=tag_id,
        )
        .values("session_id", "question_id")
        .distinct()
        .count()
    )


def _count_completed_sessions(user_id: int) -> int:
    """Nombre de sessions ≥ 10 questions où toutes les questions ont été répondues."""
    sessions = QuizSession.objects.filter(user_id=user_id)
    completed = 0
    for s in sessions.prefetch_related("session_questions", "user_answers"):
        total = s.session_questions.count()
        if total < 10:
            continue
        answered = s.user_answers.values("question_id").distinct().count()
        if answered >= total:
            completed += 1
    return completed


def _count_zero_score_questions(user_id: int) -> int:
    """Nombre de (session, question) distincts où le score effectif est 0."""
    from collections import defaultdict

    pairs: dict = defaultdict(list)
    for ua in UserAnswer.objects.filter(session__user_id=user_id).select_related(
        "answer"
    ):
        pairs[(ua.session_id, ua.question_id)].append(ua)

    count = 0
    for q_answers in pairs.values():
        raw_score = sum(ua.effective_fraction for ua in q_answers)
        score = max(0.0, min(1.0, raw_score))
        if score < 1e-9:
            count += 1
    return count


def _count_zero_score_questions_tag(user_id: int, tag_id: int) -> int:
    """Nombre de (session, question) distincts avec score nul pour un tag donné."""
    from collections import defaultdict

    pairs: dict = defaultdict(list)
    for ua in UserAnswer.objects.filter(
        session__user_id=user_id,
        question__tags__id=tag_id,
    ).select_related("answer"):
        pairs[(ua.session_id, ua.question_id)].append(ua)

    count = 0
    for q_answers in pairs.values():
        raw_score = sum(ua.effective_fraction for ua in q_answers)
        score = max(0.0, min(1.0, raw_score))
        if score < 1e-9:
            count += 1
    return count


def _count_logins(user_id: int) -> int:
    """Nombre total de connexions enregistrées pour l'utilisateur."""
    return LoginEvent.objects.filter(user_id=user_id).count()


def _max_consecutive_login_days(user_id: int) -> int:
    """Durée maximale de la série de jours de connexion consécutifs."""
    dates = sorted(
        set(
            LoginEvent.objects.filter(user_id=user_id).values_list(
                "logged_at__date", flat=True
            )
        )
    )
    if not dates:
        return 0
    max_streak = current_streak = 1
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i - 1]).days
        if gap == 1:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        elif gap > 1:
            current_streak = 1
    return max_streak


def _count_accepted_erratas(user_id: int) -> int:
    """Nombre d'erratas signalés par l'utilisateur et acceptés par l'admin."""
    return Errata.objects.filter(reported_by_id=user_id, status=Errata.ACCEPTED).count()


def _has_perfect_session(user_id: int) -> bool:
    """Retourne True si l'utilisateur a au moins une session complète à 100%."""
    sessions = QuizSession.objects.filter(user_id=user_id)
    for s in sessions:
        total = s.session_questions.count()
        if total == 0:
            continue
        answered_q_ids = set(
            s.user_answers.values_list("question_id", flat=True).distinct()
        )
        if len(answered_q_ids) < total:
            continue
        # Vérifie que chaque question a un score de 1.0 (fraction effective totale)
        session_perfect = True
        for qid in answered_q_ids:
            q_answers = list(
                s.user_answers.filter(question_id=qid).select_related("answer")
            )
            score = max(0.0, min(1.0, sum(ua.effective_fraction for ua in q_answers)))
            if score < 1.0 - 1e-9:
                session_perfect = False
                break
        if session_perfect:
            return True
    return False


def _condition_met(trophy: Trophy, user_id: int) -> bool:
    """Vérifie si la condition du trophée est remplie pour l'utilisateur."""
    ctype = trophy.condition_type
    val = trophy.condition_value

    if ctype == Trophy.QUESTIONS_COUNT:
        return _count_questions(user_id) >= val
    if ctype == Trophy.CORRECT_COUNT:
        return _count_correct(user_id) >= val
    if ctype == Trophy.QUESTIONS_COUNT_TAG:
        if trophy.condition_tag_id is None:
            return False
        return _count_questions_tag(user_id, trophy.condition_tag_id) >= val
    if ctype == Trophy.CORRECT_COUNT_TAG:
        if trophy.condition_tag_id is None:
            return False
        return _count_correct_tag(user_id, trophy.condition_tag_id) >= val
    if ctype == Trophy.PERFECT_SESSION:
        return _has_perfect_session(user_id)
    if ctype == Trophy.SESSIONS_COUNT:
        return _count_completed_sessions(user_id) >= val
    if ctype == Trophy.ERRATAS_ACCEPTED:
        return _count_accepted_erratas(user_id) >= val
    if ctype == Trophy.ZERO_SCORE_COUNT:
        return _count_zero_score_questions(user_id) >= val
    if ctype == Trophy.ZERO_SCORE_COUNT_TAG:
        if trophy.condition_tag_id is None:
            return False
        return _count_zero_score_questions_tag(user_id, trophy.condition_tag_id) >= val
    if ctype == Trophy.LOGIN_COUNT:
        return _count_logins(user_id) >= val
    if ctype == Trophy.CONSECUTIVE_DAYS:
        return _max_consecutive_login_days(user_id) >= val
    return False


def check_and_award_trophies(
    request: HttpRequest, session: QuizSession
) -> list[Trophy]:
    """
    Vérifie toutes les conditions de trophée pour l'utilisateur de la session.
    Crée les UserTrophy manquants et ajoute un message Django par nouveau trophée.
    Retourne la liste des trophées nouvellement débloqués.
    """
    user = session.user
    if user is None or not user.is_authenticated:
        return []

    already_earned = set(
        UserTrophy.objects.filter(user=user).values_list("trophy_id", flat=True)
    )
    all_trophies = Trophy.objects.exclude(pk__in=already_earned).select_related(
        "condition_tag"
    )

    newly_awarded: list[Trophy] = []
    for trophy in all_trophies:
        if _condition_met(trophy, user.pk):
            UserTrophy.objects.get_or_create(user=user, trophy=trophy)
            newly_awarded.append(trophy)
            messages.add_message(
                request,
                messages.INFO,
                f"{trophy.icon_emoji} {trophy.name}",
                extra_tags="trophy",
            )

    return newly_awarded


def award_login_trophies(request: HttpRequest, user: User) -> list[Trophy]:
    """Vérifie les trophées login_count et consecutive_days lors d'une connexion."""

    login_types = {Trophy.LOGIN_COUNT, Trophy.CONSECUTIVE_DAYS}
    already_earned = set(
        UserTrophy.objects.filter(user=user).values_list("trophy_id", flat=True)
    )
    candidates = Trophy.objects.filter(condition_type__in=login_types).exclude(
        pk__in=already_earned
    )
    newly_awarded: list[Trophy] = []
    for trophy in candidates:
        if _condition_met(trophy, user.pk):
            UserTrophy.objects.get_or_create(user=user, trophy=trophy)
            newly_awarded.append(trophy)
            messages.add_message(
                request,
                messages.INFO,
                f"{trophy.icon_emoji} {trophy.name}",
                extra_tags="trophy",
            )
    return newly_awarded
