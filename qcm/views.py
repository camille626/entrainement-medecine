"""Views for the QCM training interface."""

import fnmatch
import json
import random
import unicodedata
from typing import TYPE_CHECKING

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from .forms import InscriptionForm, ProfileForm, SessionConfigForm
from .models import (
    Answer,
    Course,
    Errata,
    ImageDropZone,
    Question,
    QuestionImage,
    QuizSession,
    QuizSessionQuestion,
    RegistrationRequest,
    Semester,
    StudyYear,
    Tag,
    TagCategory,
    Trophy,
    UserAnswer,
    UserProfile,
    UserTrophy,
)
from .trophies import check_and_award_trophies


# Fraction choices for the question upload preview form
FRACTION_CHOICES = [
    ("1.0", "+1,00 (correcte)"),
    ("0.5", "+0,50 (partielle)"),
    ("0.333333", "+0,33 (partielle x3)"),
    ("0.25", "+0,25 (partielle x4)"),
    ("0.0", "0 (neutre)"),
    ("-1.0", "-1,00 (penalite)"),
]
FRACTION_CHOICES_JSON = json.dumps([[val, label] for val, label in FRACTION_CHOICES])


if TYPE_CHECKING:
    from typing import Any

    from .models import Question as QuestionModel


# ── QROC helpers ─────────────────────────────────────────────────────────────


def normalize_qroc(text: str) -> str:
    """Normalise le texte pour la comparaison QROC : minuscules, sans accents, strip."""
    nfkd = unicodedata.normalize("NFD", text.lower().strip())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def match_qroc_answer(
    question: "QuestionModel", user_text: str
) -> "tuple[bool, Answer | None]":
    """Cherche une correspondance dans les réponses acceptées (insensible casse/accents).

    Supporte le joker Moodle * (zéro ou plusieurs caractères quelconques).
    Exemple : "myélome*" correspond à "myélome classique", "myélome multiple", etc.
    """
    n = normalize_qroc(user_text)
    if not n:
        return False, None
    for answer in question.answers.all():
        pattern = normalize_qroc(answer.text)
        if "*" in pattern:
            if fnmatch.fnmatch(n, pattern):
                return answer.is_correct, answer
        else:
            if pattern == n:
                return answer.is_correct, answer
    return False, None


def match_zone_label(zone: "ImageDropZone", user_text: str) -> bool:
    """Vérifie si le texte saisi correspond au label principal ou à un label alternatif de la zone.

    Supporte le joker * comme pour les réponses QROC (cf. match_qroc_answer).
    """
    n = normalize_qroc(user_text)
    if not n:
        return False
    candidates = [zone.correct_label] + list(
        zone.accepted_labels.values_list("text", flat=True)
    )
    for candidate in candidates:
        pattern = normalize_qroc(candidate)
        if "*" in pattern:
            if fnmatch.fnmatch(n, pattern):
                return True
        elif pattern == n:
            return True
    return False


# ── Helpers de score ─────────────────────────────────────────────────────────


def _ua_fraction(answer_fraction: "float | None", is_correct: bool) -> float:
    """Fraction effective pour un dict UserAnswer (gère l'auto-éval QROC)."""
    if answer_fraction is not None:
        return answer_fraction
    return 1.0 if is_correct else 0.0


def _build_zone_results(question: "QuestionModel", qroc_text: "str | None") -> list:
    """Build zone-result dicts for a ddimageortext question from stored JSON."""
    if question.qtype != Question.DDIMAGEORTEXT or not qroc_text:
        return []
    try:
        zone_selections = json.loads(qroc_text)
    except (ValueError, TypeError):
        zone_selections = {}
    results = []
    for zone in question.drop_zones.all():
        user_text = str(zone_selections.get(str(zone.no), ""))
        is_correct = match_zone_label(zone, user_text)
        results.append(
            {
                "zone": zone,
                "selected_label": user_text,
                "is_correct": is_correct,
            }
        )
    return results


def _max_score_for_question(question: "QuestionModel") -> float:
    """Return the maximum possible score for a question (1.0 for QROC & ddimage, sum fractions for multichoice)."""
    if question.qtype in ("shortanswer", Question.DDIMAGEORTEXT):
        return 1.0
    return sum(a.fraction for a in question.answers.filter(fraction__gt=0))


def get_answers(question: "QuestionModel", shuffle: bool = True) -> list:
    """Return answers, optionally shuffled with a deterministic seed."""
    answers = list(question.answers.all())
    if shuffle:
        random.Random(question.pk).shuffle(answers)
    return answers


def _apply_question_filter(
    qs: "Any", question_filter: str, user: "Any", nb_questions: int
) -> list[int]:
    """Return a list of question IDs based on the filter mode."""
    all_ids = list(qs.values_list("id", flat=True))

    if question_filter == "never":
        # Exclude questions already answered by this user
        done_ids = set(
            UserAnswer.objects.filter(session__user=user)
            .values_list("question_id", flat=True)
            .distinct()
        )
        priority = [q for q in all_ids if q not in done_ids]
        rest = [q for q in all_ids if q in done_ids]
        random.shuffle(priority)
        random.shuffle(rest)
        return (priority + rest)[
            :nb_questions
        ]  # never filter: priority=never done, rest=done

    if question_filter == "review":
        # Compute success rate per question for this user
        from django.db.models import Count

        answered = (
            UserAnswer.objects.filter(session__user=user, question_id__in=all_ids)
            .values("question_id")
            .annotate(
                total=Count("id"),
                correct=Count(
                    "id",
                    filter=__import__("django.db.models", fromlist=["Q"]).Q(
                        is_correct=True
                    ),
                ),
            )
        )
        rate_map = {
            row["question_id"]: row["correct"] / row["total"] for row in answered
        }

        # Priority: never done (rate=0) + rate < 0.5
        never_done = [q for q in all_ids if q not in rate_map]
        struggling = [q for q in all_ids if q in rate_map and rate_map[q] < 0.5]
        mastered = [q for q in all_ids if q in rate_map and rate_map[q] >= 0.5]

        random.shuffle(never_done)
        random.shuffle(struggling)
        random.shuffle(mastered)

        priority = never_done + struggling
        return (priority + mastered)[:nb_questions]

    if question_filter == "anchor":
        # Exclude anchored questions (answered fully correctly 3+ times)
        all_ua = UserAnswer.objects.filter(
            session__user=user, question_id__in=all_ids
        ).select_related()
        pair_correct: dict[tuple[int, int], bool] = {}
        for ua in all_ua:
            key = (ua.session_id, ua.question_id)
            if key not in pair_correct:
                pair_correct[key] = True
            if not ua.is_correct:
                pair_correct[key] = False
        q_correct_count: dict[int, int] = {}
        for (_, q_id), is_corr in pair_correct.items():
            if is_corr:
                q_correct_count[q_id] = q_correct_count.get(q_id, 0) + 1
        anchored_ids = {q_id for q_id, cnt in q_correct_count.items() if cnt >= 3}
        not_anchored = [q for q in all_ids if q not in anchored_ids]
        random.shuffle(not_anchored)
        return not_anchored[:nb_questions]

    # Default: all random
    random.shuffle(all_ids)
    return all_ids[:nb_questions]


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "qcm/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user

        from .models import UserEnrollment

        if user.is_staff:
            enrolled_course_ids = None
        else:
            enrolled_course_ids = set(
                UserEnrollment.objects.filter(user=user).values_list(
                    "course_id", flat=True
                )
            )

        years = StudyYear.objects.prefetch_related("semesters__courses").order_by(
            "order"
        )

        # Filter to only enrolled courses per semester
        filtered_years = []
        for year in years:
            filtered_semesters = []
            for semester in year.semesters.all():
                if enrolled_course_ids is None:
                    courses = list(semester.courses.all())
                else:
                    courses = [
                        c for c in semester.courses.all() if c.pk in enrolled_course_ids
                    ]
                if courses:
                    filtered_semesters.append(
                        {"semester": semester, "courses": courses}
                    )
            if filtered_semesters:
                filtered_years.append({"year": year, "semesters": filtered_semesters})

        ctx["filtered_years"] = filtered_years
        return ctx


class ConfigurationView(LoginRequiredMixin, View):
    template_name = "qcm/configuration.html"

    def _get_semesters(self, user):
        """Return semesters with only the user's enrolled courses (or all for staff)."""
        from .models import UserEnrollment

        qs = Semester.objects.select_related("study_year").order_by(
            "study_year__order", "order"
        )
        if not user.is_staff:
            enrolled_course_ids = UserEnrollment.objects.filter(user=user).values_list(
                "course_id", flat=True
            )
            qs = qs.filter(courses__id__in=enrolled_course_ids).distinct()
        return qs.prefetch_related("courses")

    def get(self, request):
        form = SessionConfigForm(user=request.user)
        semesters = self._get_semesters(request.user)
        return render(
            request,
            self.template_name,
            {
                "form": form,
                "semesters": semesters,
                "ongoing_session": self._get_ongoing_session(request.user),
            },
        )

    def _get_ongoing_session(self, user):
        """Return the most recent incomplete session, or None."""
        for session in (
            QuizSession.objects.filter(user=user, hidden_by_user=False)
            .prefetch_related("session_questions", "user_answers")
            .order_by("-started_at")[:10]
        ):
            total = session.session_questions.count()
            if total == 0:
                continue
            answered = session.user_answers.values("question_id").distinct().count()
            if answered < total:
                return session
        return None

    def post(self, request):
        form = SessionConfigForm(request.POST, user=request.user)
        if not form.is_valid():
            semesters = self._get_semesters(request.user)
            return render(
                request, self.template_name, {"form": form, "semesters": semesters}
            )

        courses = form.cleaned_data["courses"]
        nb_questions = form.cleaned_data["nb_questions"]
        tags = form.cleaned_data.get("tags")
        question_filter = form.cleaned_data.get("question_filter") or "all"
        include_qroc = form.cleaned_data.get("include_qroc", False)
        include_ddimageortext = form.cleaned_data.get("include_ddimageortext", False)

        # Select questions from chosen courses
        from .models import Question

        qtypes = ["multichoice"]
        if include_qroc:
            qtypes.append("shortanswer")
        if include_ddimageortext:
            qtypes.append(Question.DDIMAGEORTEXT)

        qs = Question.objects.filter(
            course__in=courses,
            qtype__in=qtypes,
        )

        if tags:
            # Separate tags by type: annale/EC filters are strict,
            # chapter filters also include unclassified questions (no chapter tag)
            tag_list = list(tags)
            chapter_tags = [
                t
                for t in tag_list
                if t.category and t.category.tag_type == TagCategory.CHAPITRE
            ]
            non_chapter_tags = [t for t in tag_list if t not in chapter_tags]

            # Strict filter: annale + EC tags
            if non_chapter_tags:
                qs = qs.filter(tags__in=non_chapter_tags).distinct()

            # Chapter filter: match selected chapters OR questions with no chapter tag
            if chapter_tags:
                all_chapter_ids = Tag.objects.filter(
                    category__tag_type=TagCategory.CHAPITRE
                ).values_list("id", flat=True)
                qs = (
                    qs.filter(tags__in=chapter_tags)
                    | qs.exclude(tags__in=all_chapter_ids)
                ).distinct()

        # Apply question filter (review / never / all)
        question_ids = _apply_question_filter(
            qs, question_filter, request.user, nb_questions
        )

        if not question_ids:
            form.add_error(None, "Aucune question disponible pour ces critères.")
            semesters = (
                Semester.objects.select_related("study_year")
                .prefetch_related("courses")
                .order_by("study_year__order", "order")
            )
            return render(
                request, self.template_name, {"form": form, "semesters": semesters}
            )

        first_course = courses.first()
        # Determine session mode
        session_mode = (
            "review" if question_filter in ("review", "never") else "training"
        )
        session = QuizSession.objects.create(
            user=request.user,
            course=first_course,
            mode=session_mode,
            shuffle_answers=form.cleaned_data.get("shuffle_answers", True),
        )
        for i, q_id in enumerate(question_ids, start=1):
            QuizSessionQuestion.objects.create(
                session=session, question_id=q_id, order=i
            )

        return redirect("qcm:question", pk=session.pk)


class QuestionView(LoginRequiredMixin, View):
    template_name = "qcm/question.html"

    def get(self, request, pk):
        from collections import defaultdict

        session = get_object_or_404(QuizSession, pk=pk)
        if session.hidden_by_user:
            return redirect("qcm:history")
        total = session.session_questions.count()

        # Fetch all user answers once — avoids N+1 in status computation
        all_ua = list(session.user_answers.select_related("answer").all())
        answered_question_ids = {ua.question_id for ua in all_ua}
        answered_count = len(answered_question_ids)

        if answered_count >= total:
            return redirect("qcm:fin", pk=pk)

        # Navigate to a specific question via ?q=<order> (1-based)
        q_order = request.GET.get("q")
        if q_order and q_order.isdigit():
            current_sq = session.session_questions.filter(order=int(q_order)).first()
        if not q_order or not q_order.isdigit() or current_sq is None:
            current_sq = (
                session.session_questions.exclude(question_id__in=answered_question_ids)
                .order_by("order")
                .first()
            )

        question = current_sq.question
        answers = get_answers(question, shuffle=session.shuffle_answers)

        question_tags = list(question.tags.select_related("category").all())
        ec_tags = [
            t
            for t in question_tags
            if t.category and t.category.tag_type == "souscategorie"
        ]
        chapter_tags = [
            t for t in question_tags if t.category and t.category.tag_type == "chapitre"
        ]

        # Build navigator list with status per session question
        ua_by_qid: dict = defaultdict(list)
        for ua in all_ua:
            ua_by_qid[ua.question_id].append(ua)

        sq_list = []
        for sq in session.session_questions.select_related("question").order_by(
            "order"
        ):
            ua_list = ua_by_qid.get(sq.question_id, [])
            if not ua_list:
                status = "not_answered"
            else:
                score = max(
                    0.0,
                    min(1.0, sum(ua.effective_fraction for ua in ua_list)),
                )
                max_score = _max_score_for_question(sq.question)
                ratio = score / max_score if max_score > 0 else 0.0
                if ratio >= 1.0 - 1e-6:
                    status = "correct"
                elif ratio > 0:
                    status = "partial"
                else:
                    status = "incorrect"
            sq_list.append(
                {
                    "order": sq.order,
                    "question_id": sq.question_id,
                    "status": status,
                    "is_current": sq.pk == current_sq.pk,
                }
            )

        # If navigating to an already-answered question, prepare correction context
        is_answered = question.pk in answered_question_ids

        # ddimageortext-specific context
        drag_items: list = []
        drop_zones: list = []
        if question.qtype == Question.DDIMAGEORTEXT:
            drag_items = list(question.drag_items.all())
            drop_zones = list(question.drop_zones.all())

        ctx: dict = {
            "session": session,
            "question": question,
            "answers": answers,
            "position": current_sq.order,
            "total": total,
            "mode": session.mode,
            "ec_tags": ec_tags,
            "chapter_tags": chapter_tags,
            "sq_list": sq_list,
            "is_answered": is_answered,
            "prev_order": current_sq.order - 1 if current_sq.order > 1 else None,
            "next_order": current_sq.order + 1 if current_sq.order < total else None,
            "drag_items": drag_items,
            "drop_zones": drop_zones,
        }

        if is_answered:
            ua_list = ua_by_qid.get(question.pk, [])
            selected_ids = [ua.answer_id for ua in ua_list if ua.answer_id is not None]
            score = max(0.0, min(1.0, sum(ua.effective_fraction for ua in ua_list)))
            max_score = _max_score_for_question(question)
            ratio = score / max_score if max_score > 0 else 0.0
            if ratio >= 1.0 - 1e-6:
                q_status = "correct"
            elif ratio > 0:
                q_status = "partial"
            else:
                q_status = "incorrect"
            is_last = answered_count >= total
            qroc_text = next(
                (ua.qroc_text for ua in ua_list if ua.qroc_text is not None), None
            )
            accepted_answers = (
                list(question.answers.filter(fraction__gt=0).order_by("text"))
                if question.qtype == "shortanswer"
                else []
            )
            ctx.update(
                {
                    "selected_ids": selected_ids,
                    "score": score,
                    "status": q_status,
                    "is_last": is_last,
                    "qroc_text": qroc_text,
                    "accepted_answers": accepted_answers,
                    "zone_results": _build_zone_results(question, qroc_text),
                }
            )

        return render(request, self.template_name, ctx)


class CheckView(LoginRequiredMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(QuizSession, pk=pk)
        answered_question_ids = set(
            session.user_answers.values_list("question_id", flat=True).distinct()
        )

        # Use question_id from POST when provided (avoids wrong-question bug with navigator)
        question_id_from_post = request.POST.get("question_id")
        if question_id_from_post and question_id_from_post.isdigit():
            current_sq = session.session_questions.filter(
                question_id=int(question_id_from_post)
            ).first()
            if current_sq is None or current_sq.question_id in answered_question_ids:
                return HttpResponse("Question déjà répondue ou introuvable", status=400)
        else:
            current_sq = (
                session.session_questions.exclude(question_id__in=answered_question_ids)
                .order_by("order")
                .first()
            )
        if current_sq is None:
            return HttpResponse("Session terminée", status=400)

        question = current_sq.question

        # ── Branche ddimageortext ─────────────────────────────────────────────
        if question.qtype == Question.DDIMAGEORTEXT:
            return self._handle_ddimageortext(request, session, current_sq, question)

        # ── Branche QROC ──────────────────────────────────────────────────────
        if question.qtype == "shortanswer":
            return self._handle_qroc(request, session, current_sq, question)

        # ── Branche multichoix ────────────────────────────────────────────────
        selected_ids = request.POST.getlist("answers")
        score = 0.0
        for answer_id in selected_ids:
            try:
                answer = Answer.objects.get(pk=answer_id, question=question)
                UserAnswer.objects.get_or_create(
                    session=session,
                    question=question,
                    answer=answer,
                    defaults={"is_correct": answer.is_correct},
                )
                score += answer.fraction
            except Answer.DoesNotExist:
                continue

        score = max(0.0, min(1.0, score))
        max_score = sum(a.fraction for a in question.answers.filter(fraction__gt=0))
        ratio = score / max_score if max_score > 0 else 0.0

        if ratio >= 1.0:
            status = "correct"
        elif ratio > 0:
            status = "partial"
        else:
            status = "incorrect"

        check_and_award_trophies(request, session)

        total = session.session_questions.count()
        new_answered = set(
            session.user_answers.values_list("question_id", flat=True).distinct()
        )
        position = len(new_answered)
        is_last = position >= total
        prev_order = current_sq.order - 1 if current_sq.order > 1 else None
        next_order = current_sq.order + 1 if current_sq.order < total else None

        return render(
            request,
            "qcm/_correction.html",
            {
                "question": question,
                "answers": get_answers(question, shuffle=session.shuffle_answers),
                "selected_ids": [int(i) for i in selected_ids],
                "score": score,
                "status": status,
                "session": session,
                "is_last": is_last,
                "position": position,
                "total": total,
                "prev_order": prev_order,
                "next_order": next_order,
            },
        )

    def _handle_qroc(self, request, session, current_sq, question):
        """Gère la soumission d'une réponse QROC."""
        user_text = request.POST.get("qroc_text", "").strip()
        total = session.session_questions.count()
        prev_order = current_sq.order - 1 if current_sq.order > 1 else None
        next_order = current_sq.order + 1 if current_sq.order < total else None
        accepted_answers = list(
            question.answers.filter(fraction__gt=0).order_by("text")
        )

        found, matched_answer = match_qroc_answer(question, user_text)

        if found and matched_answer is not None:
            # Correspondance automatique — on enregistre directement
            UserAnswer.objects.get_or_create(
                session=session,
                question=question,
                answer=matched_answer,
                defaults={
                    "is_correct": matched_answer.is_correct,
                    "qroc_text": user_text,
                },
            )
            score = matched_answer.fraction
            status = "correct" if matched_answer.is_correct else "incorrect"
            check_and_award_trophies(request, session)
            new_answered = set(
                session.user_answers.values_list("question_id", flat=True).distinct()
            )
            position = len(new_answered)
            is_last = position >= total
            return render(
                request,
                "qcm/_correction.html",
                {
                    "question": question,
                    "answers": accepted_answers,
                    "selected_ids": [],
                    "score": score,
                    "status": status,
                    "session": session,
                    "is_last": is_last,
                    "position": position,
                    "total": total,
                    "prev_order": prev_order,
                    "next_order": next_order,
                    "qroc_text": user_text,
                    "accepted_answers": accepted_answers,
                },
            )

        # Pas de correspondance — auto-évaluation requise
        return render(
            request,
            "qcm/_qroc_ambiguous.html",
            {
                "question": question,
                "session": session,
                "qroc_text": user_text,
                "accepted_answers": accepted_answers,
                "prev_order": prev_order,
                "next_order": next_order,
                "total": total,
            },
        )

    def _handle_ddimageortext(self, request, session, current_sq, question):
        """Gère la soumission d'une réponse ddimageortext (légende interactive — saisie QROC par zone)."""
        drop_zones = list(question.drop_zones.all())

        total_zones = len(drop_zones)
        if total_zones == 0:
            UserAnswer.objects.get_or_create(
                session=session,
                question=question,
                answer=None,
                defaults={"is_correct": True, "fraction_override": 1.0},
            )
            fraction = 1.0
            zone_results: list[dict] = []
        else:
            # Collect user text for each zone: POST key "zone_<no>" → free text
            zone_selections: dict[str, str] = {}
            for zone in drop_zones:
                zone_selections[str(zone.no)] = request.POST.get(
                    f"zone_{zone.no}", ""
                ).strip()

            # Evaluate each zone (normalized comparison, like QROC)
            correct_count = 0
            zone_results = []
            for zone in drop_zones:
                user_text = zone_selections.get(str(zone.no), "")
                is_zone_correct = match_zone_label(zone, user_text)
                if is_zone_correct:
                    correct_count += 1
                zone_results.append(
                    {
                        "zone": zone,
                        "selected_label": user_text,
                        "is_correct": is_zone_correct,
                    }
                )

            fraction = correct_count / total_zones
            is_correct = correct_count == total_zones

            UserAnswer.objects.get_or_create(
                session=session,
                question=question,
                answer=None,
                defaults={
                    "is_correct": is_correct,
                    "fraction_override": fraction,
                    "qroc_text": json.dumps(zone_selections),
                },
            )

        if fraction >= 1.0 - 1e-6:
            status = "correct"
        elif fraction > 0:
            status = "partial"
        else:
            status = "incorrect"

        check_and_award_trophies(request, session)

        total = session.session_questions.count()
        new_answered = set(
            session.user_answers.values_list("question_id", flat=True).distinct()
        )
        position = len(new_answered)
        is_last = position >= total
        prev_order = current_sq.order - 1 if current_sq.order > 1 else None
        next_order = current_sq.order + 1 if current_sq.order < total else None

        return render(
            request,
            "qcm/_correction.html",
            {
                "question": question,
                "answers": [],
                "selected_ids": [],
                "score": fraction,
                "status": status,
                "session": session,
                "is_last": is_last,
                "position": position,
                "total": total,
                "prev_order": prev_order,
                "next_order": next_order,
                "zone_results": zone_results,
            },
        )


class CheckQROCSelfView(LoginRequiredMixin, View):
    """Enregistre l'auto-évaluation d'une réponse QROC sans correspondance automatique."""

    def post(self, request, pk):
        session = get_object_or_404(QuizSession, pk=pk)
        answered_question_ids = set(
            session.user_answers.values_list("question_id", flat=True).distinct()
        )

        # Use question_id from POST to answer the correct question
        question_id_from_post = request.POST.get("question_id")
        if question_id_from_post and question_id_from_post.isdigit():
            current_sq = session.session_questions.filter(
                question_id=int(question_id_from_post)
            ).first()
            if current_sq is None or current_sq.question_id in answered_question_ids:
                return HttpResponse("Question déjà répondue ou introuvable", status=400)
        else:
            current_sq = (
                session.session_questions.exclude(question_id__in=answered_question_ids)
                .order_by("order")
                .first()
            )
        if current_sq is None:
            return HttpResponse("Session terminée", status=400)

        question = current_sq.question
        if question.qtype != "shortanswer":
            return HttpResponse("Question non QROC", status=400)

        user_text = request.POST.get("qroc_text", "").strip()
        self_eval = request.POST.get("self_eval", "incorrect")
        is_correct = self_eval == "correct"

        UserAnswer.objects.get_or_create(
            session=session,
            question=question,
            answer=None,
            defaults={
                "is_correct": is_correct,
                "qroc_text": user_text,
                "is_self_evaluated": True,
            },
        )

        score = 1.0 if is_correct else 0.0
        status = "correct" if is_correct else "incorrect"
        check_and_award_trophies(request, session)
        total = session.session_questions.count()
        new_answered = set(
            session.user_answers.values_list("question_id", flat=True).distinct()
        )
        position = len(new_answered)
        is_last = position >= total
        prev_order = current_sq.order - 1 if current_sq.order > 1 else None
        next_order = current_sq.order + 1 if current_sq.order < total else None
        accepted_answers = list(
            question.answers.filter(fraction__gt=0).order_by("text")
        )

        return render(
            request,
            "qcm/_correction.html",
            {
                "question": question,
                "answers": accepted_answers,
                "selected_ids": [],
                "score": score,
                "status": status,
                "session": session,
                "is_last": is_last,
                "position": position,
                "total": total,
                "prev_order": prev_order,
                "next_order": next_order,
                "qroc_text": user_text,
                "accepted_answers": accepted_answers,
            },
        )


class FinView(LoginRequiredMixin, View):
    template_name = "qcm/fin.html"

    def get(self, request, pk):
        session = get_object_or_404(QuizSession, pk=pk)
        total = session.session_questions.count()

        question_results = []
        total_score = 0.0

        for sq in session.session_questions.order_by("order"):
            q = sq.question
            user_answers = list(
                session.user_answers.filter(question=q).select_related("answer")
            )
            selected_ids = {ua.answer_id for ua in user_answers if ua.answer_id}

            raw_score = sum(ua.effective_fraction for ua in user_answers)
            score = max(0.0, min(1.0, raw_score))
            total_score += score

            max_score = _max_score_for_question(q)
            ratio = score / max_score if max_score > 0 else 0.0

            qroc_text = next(
                (ua.qroc_text for ua in user_answers if ua.qroc_text is not None), None
            )
            accepted_answers = (
                list(q.answers.filter(fraction__gt=0).order_by("text"))
                if q.qtype == "shortanswer"
                else []
            )

            if not user_answers:
                status = "unanswered"
            elif ratio >= 1.0:
                status = "correct"
            elif ratio > 0:
                status = "partial"
            else:
                status = "incorrect"

            question_results.append(
                {
                    "question": q,
                    "answers": get_answers(q, shuffle=session.shuffle_answers),
                    "selected_ids": selected_ids,
                    "score": score,
                    "max_score": max_score,
                    "status": status,
                    "answered": bool(user_answers),
                    "qroc_text": qroc_text,
                    "accepted_answers": accepted_answers,
                    "zone_results": _build_zone_results(q, qroc_text),
                }
            )

        answered = sum(1 for r in question_results if r["answered"])
        correct = sum(1 for r in question_results if r["status"] == "correct")
        partial = sum(1 for r in question_results if r["status"] == "partial")
        incorrect = sum(1 for r in question_results if r["status"] == "incorrect")
        note_20 = round(total_score / total * 20, 1) if total > 0 else 0.0

        return render(
            request,
            self.template_name,
            {
                "session": session,
                "question_results": question_results,
                "total": total,
                "answered": answered,
                "correct": correct,
                "partial": partial,
                "incorrect": incorrect,
                "total_score": round(total_score, 2),
                "note_20": note_20,
            },
        )


class TagsView(LoginRequiredMixin, View):
    """HTMX endpoint: return tag checkboxes filtered by selected courses."""

    def get(self, request):
        course_ids = request.GET.getlist("courses")

        if not course_ids:
            return render(
                request,
                "qcm/_tags_partial.html",
                {"tag_groups": [], "no_courses": True},
            )

        # Store selected course IDs in session for ChaptersView to use
        request.session["selected_course_ids"] = course_ids

        courses = Course.objects.filter(pk__in=course_ids)

        # Build tag groups
        tag_groups = []

        # Categories with course=NULL are "global" → shown for any selected course
        # Categories with course=X → shown only if that course is selected
        from django.db.models import Q

        # 1. Annale categories (always global)
        # 2. EC/souscategorie categories (global OR course-specific)
        ec_cats = (
            TagCategory.objects.filter(
                tag_type__in=[TagCategory.ANNEE, TagCategory.SOUSCATEGORIE],
            )
            .filter(Q(course__isnull=True) | Q(course__in=courses))
            .prefetch_related("tags")
            .order_by("order", "name")
        )

        for cat in ec_cats:
            if cat.course is None and cat.tag_type == TagCategory.SOUSCATEGORIE:
                # Global EC category: filter tags to those with questions in selected courses
                tags = list(
                    cat.tags.filter(questions__course__in=courses)
                    .distinct()
                    .order_by("name")
                )
            else:
                tags = list(cat.tags.all())
            if tags:
                tag_groups.append({"category": cat, "tags": tags})

        # Chapter tags directly linked to a selected course (no EC parent)
        # These appear immediately without needing an EC selection
        direct_chapter_tags = (
            Tag.objects.filter(
                course__in=courses,
                parent_ec__isnull=True,
                category__tag_type=TagCategory.CHAPITRE,
            )
            .select_related("category")
            .order_by("category__order", "name")
        )
        if direct_chapter_tags.exists():
            from collections import defaultdict

            direct_groups: dict = defaultdict(list)
            for tag in direct_chapter_tags:
                direct_groups[tag.category].append(tag)
            for cat, tags in sorted(
                direct_groups.items(),
                key=lambda x: (x[0].order if x[0] else 999, x[0].name if x[0] else ""),
            ):
                tag_groups.append({"category": cat, "tags": tags})

        return render(
            request,
            "qcm/_tags_partial.html",
            {
                "tag_groups": tag_groups,
                "no_courses": False,
                "selected_course_ids": course_ids,
            },
        )


class ChaptersView(LoginRequiredMixin, View):
    """HTMX endpoint: return chapter tags for selected EC (souscategorie) tags."""

    def get(self, request):
        ec_tag_ids = request.GET.getlist("tags")

        if not ec_tag_ids:
            return render(request, "qcm/_chapters_partial.html", {"chapter_groups": []})

        ec_tags = Tag.objects.filter(
            pk__in=ec_tag_ids,
            category__tag_type=TagCategory.SOUSCATEGORIE,
        )

        # Use explicit parent_ec + course relationships (configured in admin)
        from django.db.models import Q

        course_ids = request.session.get("selected_course_ids", [])
        tag_filter = Q(parent_ec__in=ec_tags)
        if course_ids:
            # Show chapters matching the course, OR chapters with no course assigned
            tag_filter &= Q(course_id__in=course_ids) | Q(course__isnull=True)

        chapter_tags = (
            Tag.objects.filter(tag_filter)
            .select_related("category", "course")
            .order_by("category__order", "name")
        )

        if not chapter_tags.exists():
            return render(request, "qcm/_chapters_partial.html", {"chapter_groups": []})

        # Group by category
        from collections import defaultdict

        groups: dict = defaultdict(list)
        for tag in chapter_tags:
            groups[tag.category].append(tag)

        chapter_groups = [
            {"category": cat, "tags": tags}
            for cat, tags in sorted(
                groups.items(),
                key=lambda x: (x[0].order if x[0] else 999, x[0].name if x[0] else ""),
            )
        ]

        return render(
            request,
            "qcm/_chapters_partial.html",
            {
                "chapter_groups": chapter_groups,
            },
        )


def _compute_anchored_count(user_answers_qs):
    """
    Return the number of anchored questions.
    A question is anchored if it has been answered fully correctly (all selected
    answers have is_correct=True) at least 3 times total across any sessions.
    """
    # Build dict: (session_id, question_id) -> all_correct
    pair_correct: dict[tuple[int, int], bool] = {}
    for ua in user_answers_qs.select_related():
        key = (ua.session_id, ua.question_id)
        if key not in pair_correct:
            pair_correct[key] = True
        if not ua.is_correct:
            pair_correct[key] = False

    # Count correct attempts per question
    q_correct_count: dict = {}
    for (_, question_id), is_correct in pair_correct.items():
        if is_correct:
            q_correct_count[question_id] = q_correct_count.get(question_id, 0) + 1

    return sum(1 for count in q_correct_count.values() if count >= 3)


def _compute_course_block(course, all_answers):
    """Return stats dict for a single course."""
    from collections import defaultdict

    from .models import Question

    answers = all_answers.filter(question__course=course)
    nb_available = Question.objects.filter(
        course=course, qtype__in=["multichoice", "shortanswer"]
    ).count()
    nb_done = answers.values("question_id").distinct().count()

    # Compute note at question-attempt level: group fractions by (session, question)
    pair_fracs: dict = defaultdict(list)
    for ua in answers.values(
        "session_id", "question_id", "answer__fraction", "is_correct"
    ):
        frac = _ua_fraction(ua["answer__fraction"], ua["is_correct"])
        pair_fracs[(ua["session_id"], ua["question_id"])].append(frac)

    nb_total_sessions = len(pair_fracs)

    if nb_total_sessions > 0:
        q_scores = [max(0.0, min(1.0, sum(fracs))) for fracs in pair_fracs.values()]
        note = round(sum(q_scores) / nb_total_sessions * 20, 1)
        correct = sum(1 for s in q_scores if s >= 1.0 - 1e-6)
        pct = round(correct / nb_total_sessions * 100)
    else:
        note = 0.0
        pct = 0

    pct_done = round(nb_done / nb_available * 100) if nb_available > 0 else 0
    nb_anchored = _compute_anchored_count(answers)

    return {
        "course": course,
        "nb_available": nb_available,
        "nb_done": nb_done,
        "nb_total_sessions": nb_total_sessions,
        "pct_done": pct_done,
        "note_20": note,
        "pct_correct": pct,
        "nb_anchored": nb_anchored,
    }


class StatsView(LoginRequiredMixin, View):
    """Personal statistics page."""

    template_name = "qcm/stats.html"

    def get(self, request):  # noqa: PLR0914
        from collections import defaultdict
        from datetime import timedelta

        from django.utils import timezone
        from django.utils.timezone import localdate

        user = request.user

        # Single queryset — evaluated once into a list for Python processing
        all_answers = UserAnswer.objects.filter(session__user=user)
        raw = list(
            all_answers.values(
                "session_id",
                "question_id",
                "is_correct",
                "answer__fraction",
                "session__started_at",
            )
        )

        total_sessions = QuizSession.objects.filter(user=user).count()

        if not raw:
            correct = partial = incorrect = 0
            note_20 = 0.0
            pct_correct = pct_partial = pct_incorrect = 0
            total_checks = 0
        else:
            # Group answer fractions by (session, question) for question-level scoring
            pair_fracs: dict = defaultdict(list)
            for r in raw:
                frac = _ua_fraction(r["answer__fraction"], r["is_correct"])
                pair_fracs[(r["session_id"], r["question_id"])].append(frac)

            # Question score = sum of answer fractions clamped to [0, 1]
            q_scores = [max(0.0, min(1.0, sum(fracs))) for fracs in pair_fracs.values()]
            total_checks = len(q_scores)

            note_20 = round(sum(q_scores) / total_checks * 20, 1)

            # Classify each question attempt by its score
            correct = sum(1 for s in q_scores if s >= 1.0 - 1e-6)
            incorrect = sum(1 for s in q_scores if s <= 0)
            partial = total_checks - correct - incorrect
            pct_correct = round(correct / total_checks * 100)
            pct_partial = round(partial / total_checks * 100)
            pct_incorrect = round(incorrect / total_checks * 100)

        # --- Per-course stats ---
        from .models import Course, UserEnrollment

        # Always prefer explicit enrollment (shows courses even with 0 answers)
        enrollment_qs = UserEnrollment.objects.filter(user=user).select_related(
            "course__semester__study_year"
        )
        if enrollment_qs.exists():
            enrolled_courses = [e.course for e in enrollment_qs]
        else:
            # No enrollment records: fall back to courses with at least 1 answer
            answered_course_ids = all_answers.values_list(
                "question__course_id", flat=True
            ).distinct()
            enrolled_courses = list(
                Course.objects.filter(pk__in=answered_course_ids).select_related(
                    "semester__study_year"
                )
            )

        course_stats = [_compute_course_block(c, all_answers) for c in enrolled_courses]

        # Sort by semester (study_year order → semester order → course name)
        def _sem_key(stat):
            sem = stat["course"].semester
            if sem:
                return (sem.study_year.order, sem.order, stat["course"].name)
            return (999, 999, stat["course"].name)

        course_stats.sort(key=_sem_key)

        # Add semester label for template grouping
        for stat in course_stats:
            sem = stat["course"].semester
            stat["semester_label"] = str(sem) if sem else "Autres"

        # Global totals
        from .models import Question

        total_available = Question.objects.filter(
            course__in=[c.pk for c in enrolled_courses],
            qtype__in=["multichoice", "shortanswer"],
        ).count()
        total_done = all_answers.values("question_id").distinct().count()
        pct_done_global = (
            round(total_done / total_available * 100) if total_available > 0 else 0
        )
        total_anchored = _compute_anchored_count(all_answers)
        pct_anchored = (
            round(total_anchored / total_available * 100) if total_available > 0 else 0
        )

        # --- Weekly progression (last 8 weeks) with daily breakdown ---
        now = timezone.now()
        today = localdate(now)

        # Group raw answers by local date
        by_date: dict = defaultdict(list)
        for r in raw:
            d = localdate(r["session__started_at"])
            by_date[d].append(r)

        def _week_stats(entries: list) -> tuple:
            """Returns (note_or_None, nb_checks)."""
            if not entries:
                return None, 0
            score = sum(
                min(1.0, max(0.0, _ua_fraction(e["answer__fraction"], e["is_correct"])))
                for e in entries
            )
            note = round(score / len(entries) * 20, 1)
            checks = len({(e["session_id"], e["question_id"]) for e in entries})
            return note, checks

        weekly_data = []
        for i in range(7, -1, -1):
            week_start = today - timedelta(weeks=i + 1)
            week_end = today - timedelta(weeks=i)

            week_entries = [
                r
                for r in raw
                if week_start <= localdate(r["session__started_at"]) < week_end
            ]
            wnote, wchecks = _week_stats(week_entries)

            daily = []
            for j in range(7):
                d = week_start + timedelta(days=j)
                day_entries = by_date.get(d, [])
                dnote, dchecks = _week_stats(day_entries)
                daily.append(
                    {
                        "day": d.strftime("%a %d/%m"),
                        "note": dnote,
                        "checks": dchecks,
                    }
                )

            label = week_end.strftime("S%U")
            weekly_data.append(
                {
                    "label": label,
                    "note": wnote,
                    "nb_checks": wchecks,
                    "daily": daily,
                }
            )

        # Pass Python objects — json_script in the template handles encoding
        chart_labels = [d["label"] for d in weekly_data]
        chart_notes = [d["note"] for d in weekly_data]
        chart_checks = [d["nb_checks"] for d in weekly_data]
        chart_daily = [
            [
                {"day": day["day"], "note": day["note"], "checks": day["checks"]}
                for day in d["daily"]
            ]
            for d in weekly_data
        ]

        return render(
            request,
            self.template_name,
            {
                "total_checks": total_checks,
                "total_sessions": total_sessions,
                "correct": correct,
                "partial": partial,
                "incorrect": incorrect,
                "note_20": note_20,
                "pct_correct": pct_correct,
                "pct_partial": pct_partial,
                "pct_incorrect": pct_incorrect,
                "course_stats": course_stats,
                "chart_labels": chart_labels,
                "chart_notes": chart_notes,
                "chart_checks": chart_checks,
                "chart_daily": chart_daily,
                "total_available": total_available,
                "total_done": total_done,
                "pct_done_global": pct_done_global,
                "total_anchored": total_anchored,
                "pct_anchored": pct_anchored,
            },
        )


class HistoryView(LoginRequiredMixin, View):
    """List of past quiz sessions for the logged-in user."""

    template_name = "qcm/history.html"

    def get(self, request):
        sessions = (
            QuizSession.objects.filter(user=request.user, hidden_by_user=False)
            .select_related("course")
            .prefetch_related("user_answers__answer")
            .order_by("-started_at")
        )

        # Optional filter by course
        course_filter = request.GET.get("course")
        if course_filter:
            sessions = sessions.filter(course_id=course_filter)

        session_data = []
        for s in sessions:
            nb_questions = s.session_questions.count()
            # Distinct questions with at least one answer
            answered_q_ids = set(
                s.user_answers.values_list("question_id", flat=True).distinct()
            )
            nb_answered_distinct = len(answered_q_ids)
            is_complete = nb_answered_distinct >= nb_questions

            # Note: aggregate per question (correct for multichoice and QROC)
            if answered_q_ids:
                total_q_score = 0.0
                for q_id in answered_q_ids:
                    q_ans = s.user_answers.filter(question_id=q_id).select_related(
                        "answer"
                    )
                    q_score = min(
                        1.0, max(0.0, sum(ua.effective_fraction for ua in q_ans))
                    )
                    total_q_score += q_score
                note = (
                    round(total_q_score / nb_questions * 20, 1)
                    if nb_questions > 0
                    else None
                )
            else:
                note = None

            # Courses: get from questions in session (supports multi-course)
            from .models import Course

            course_ids = s.session_questions.values_list(
                "question__course_id", flat=True
            ).distinct()
            session_courses = list(
                Course.objects.filter(pk__in=course_ids).order_by("name")
            )

            session_data.append(
                {
                    "session": s,
                    "nb_questions": nb_questions,
                    "nb_answered_distinct": nb_answered_distinct,
                    "is_complete": is_complete,
                    "note_20": note,
                    "session_courses": session_courses,
                }
            )

        # Courses for filter dropdown
        from .models import UserEnrollment

        if request.user.is_staff:
            from .models import Course

            courses = Course.objects.order_by("name")
        else:
            courses = [
                e.course
                for e in UserEnrollment.objects.filter(
                    user=request.user
                ).select_related("course")
            ]

        return render(
            request,
            self.template_name,
            {
                "session_data": session_data,
                "courses": courses,
                "selected_course": course_filter,
            },
        )


class HideSessionView(LoginRequiredMixin, View):
    """Masque une session de l'historique sans toucher aux UserAnswer."""

    def post(self, request, pk):
        session = get_object_or_404(QuizSession, pk=pk, user=request.user)
        session.hidden_by_user = True
        session.save(update_fields=["hidden_by_user"])
        return redirect("qcm:history")


def _errata_list_redirect(request):
    """Redirect back to errata list, preserving filters passed as 'back' POST param."""
    back = request.POST.get("back", "")
    url = "/errata/?" + back if back else "/errata/"
    return redirect(url)


class ErrataAcceptView(LoginRequiredMixin, View):
    """Staff-only: accept an errata and apply changes."""

    def post(self, request, pk):
        from django.utils import timezone

        if not request.user.is_staff:
            from django.http import Http404

            raise Http404
        errata = get_object_or_404(Errata, pk=pk)
        errata.status = Errata.ACCEPTED
        errata.resolved_by = request.user
        errata.resolved_at = timezone.now()
        errata.save()

        if errata.error_type == Errata.TAG and errata.suggested_tags.exists():
            question = errata.question
            # Conserver les tags annale existants, remplacer uniquement EC et chapitres
            annale_ids = set(
                question.tags.filter(category__tag_type=TagCategory.ANNEE).values_list(
                    "id", flat=True
                )
            )
            suggested_ids = set(errata.suggested_tags.values_list("id", flat=True))
            question.tags.set(annale_ids | suggested_ids)

        elif errata.error_type == Errata.CORRECTION:
            question = errata.question
            all_answers = list(question.answers.all())
            correct_pks = {
                ans.pk
                for ans in all_answers
                if request.POST.get(f"answer_{ans.pk}") == "1"
            }
            n_correct = len(correct_pks)
            for ans in all_answers:
                if ans.pk in correct_pks:
                    ans.is_correct = True
                    ans.fraction = round(1.0 / n_correct, 4) if n_correct > 0 else 0.0
                else:
                    ans.is_correct = False
                    ans.fraction = -1.0
            Answer.objects.bulk_update(all_answers, ["is_correct", "fraction"])

            feedback = request.POST.get("general_feedback", "").strip()
            question.feedback = feedback
            question.save(update_fields=["feedback"])

        elif errata.error_type == Errata.POINTS:
            question = errata.question
            all_answers = list(question.answers.all())
            for ans in all_answers:
                raw = request.POST.get(f"fraction_{ans.pk}")
                if raw is not None:
                    try:
                        frac = max(-1.0, min(1.0, float(raw)))
                        ans.fraction = round(frac, 4)
                        ans.is_correct = frac > 0
                    except ValueError:
                        pass
            Answer.objects.bulk_update(all_answers, ["fraction", "is_correct"])

            feedback = request.POST.get("general_feedback", "").strip()
            question.feedback = feedback
            question.save(update_fields=["feedback"])

        elif errata.error_type == Errata.QROC_ANSWER:
            # Créer un nouvel Answer accepté pour la question QROC
            suggested_text = errata.qroc_suggested_text.strip()
            try:
                fraction = float(request.POST.get("qroc_fraction", "1.0"))
                fraction = max(0.0, min(1.0, fraction))
            except ValueError:
                fraction = 1.0
            if suggested_text:
                Answer.objects.get_or_create(
                    question=errata.question,
                    text=suggested_text,
                    defaults={
                        "fraction": fraction,
                        "is_correct": fraction > 0,
                    },
                )

        from .models import Notification

        Notification.objects.create(
            user=errata.reported_by,
            message=(
                f"✅ Votre signalement « {errata.get_error_type_display()} » "
                f"a été accepté — merci pour votre contribution !"
            ),
            link="/",
        )
        return _errata_list_redirect(request)


class ErrataRejectView(LoginRequiredMixin, View):
    """Staff-only: reject an errata."""

    def post(self, request, pk):
        from django.utils import timezone

        if not request.user.is_staff:
            from django.http import Http404

            raise Http404
        errata = get_object_or_404(Errata, pk=pk)
        errata.status = Errata.REJECTED
        errata.resolved_by = request.user
        errata.resolved_at = timezone.now()
        errata.admin_note = request.POST.get("admin_note", "")
        errata.save()
        return _errata_list_redirect(request)


class ErrataFeedbackView(LoginRequiredMixin, View):
    """Staff-only: save general feedback on the question associated with an errata."""

    def post(self, request, pk):
        if not request.user.is_staff:
            from django.http import Http404

            raise Http404
        errata = get_object_or_404(Errata, pk=pk)
        errata.question.feedback = request.POST.get("general_feedback", "")
        errata.question.save(update_fields=["feedback"])
        return _errata_list_redirect(request)


class NotificationMarkReadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        from .models import Notification

        Notification.objects.filter(pk=pk, user=request.user).update(read=True)
        return HttpResponse(status=204)


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    def post(self, request):
        from .models import Notification

        Notification.objects.filter(user=request.user, read=False).update(read=True)
        return render(request, "qcm/_notif_bell.html")


class ErrataListView(LoginRequiredMixin, View):
    """Public list of erratas, filterable by course and status."""

    template_name = "qcm/errata_list.html"

    def get(self, request):
        qs = (
            Errata.objects.select_related("question__course", "reported_by")
            .prefetch_related(
                "concerned_answers",
                "suggested_tags__category",
                "question__tags__category",
                "question__answers",
            )
            .order_by("-created_at")
        )

        course_filter = request.GET.get("course")
        status_filter = request.GET.get("status", "pending")  # default: pending
        type_filter = request.GET.get("error_type")
        if course_filter:
            qs = qs.filter(question__course_id=course_filter)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if type_filter:
            qs = qs.filter(error_type=type_filter)

        from .models import UserEnrollment

        if request.user.is_staff:
            courses = Course.objects.order_by("name")
        else:
            courses = [
                e.course
                for e in UserEnrollment.objects.filter(
                    user=request.user
                ).select_related("course")
            ]

        back_params = request.GET.urlencode()

        return render(
            request,
            self.template_name,
            {
                "erratas": qs[:100],
                "courses": courses,
                "selected_course": course_filter,
                "selected_status": status_filter,
                "selected_type": type_filter,
                "type_choices": Errata.TYPE_CHOICES,
                "status_choices": Errata.STATUS_CHOICES,
                "back_params": back_params,
            },
        )


class ErrataSubmitView(LoginRequiredMixin, View):
    """HTMX endpoint to submit an errata report."""

    def post(self, request, question_id):
        question = get_object_or_404(Question, pk=question_id)
        error_type = request.POST.get("error_type", Errata.OTHER)
        description = request.POST.get("description", "").strip()

        # Description required only for correction and autre
        requires_description = error_type in (Errata.CORRECTION, Errata.OTHER)
        if requires_description and not description:
            return render(
                request,
                "qcm/_errata_form.html",
                {
                    "question": question,
                    "error": "La description est obligatoire pour ce type d'erreur.",
                    "existing": Errata.objects.filter(
                        question=question, status=Errata.PENDING
                    ).first(),
                },
            )

        qroc_suggested_text = request.POST.get("qroc_suggested_text", "").strip()

        errata = Errata.objects.create(
            question=question,
            reported_by=request.user,
            error_type=error_type,
            description=description,
            qroc_suggested_text=qroc_suggested_text,
        )

        # Link concerned answers (for correction errors)
        answer_ids = request.POST.getlist("concerned_answers")
        if answer_ids:
            errata.concerned_answers.set(
                Answer.objects.filter(pk__in=answer_ids, question=question)
            )

        # Link suggested tags (for tag errors)
        tag_ids = request.POST.getlist("suggested_tags")
        if tag_ids:
            errata.suggested_tags.set(Tag.objects.filter(pk__in=tag_ids))

        return render(request, "qcm/_errata_success.html", {"errata": errata})

    def get(self, request, question_id):
        question = get_object_or_404(Question, pk=question_id)
        existing = Errata.objects.filter(
            question=question, status=Errata.PENDING
        ).first()
        ec_tags = (
            Tag.objects.filter(
                category__tag_type="souscategorie",
                questions__course=question.course,
            )
            .distinct()
            .order_by("name")
        )
        chapter_tags = (
            Tag.objects.filter(
                category__tag_type="chapitre",
                questions__course=question.course,
            )
            .distinct()
            .order_by("name")
        )
        # Pre-fill QROC text from query param (coming from ambiguous template)
        prefill_qroc_text = request.GET.get("qroc_text", "")
        prefill_type = request.GET.get("prefill_type", "")
        return render(
            request,
            "qcm/_errata_form.html",
            {
                "question": question,
                "existing": existing,
                "ec_tags": ec_tags,
                "chapter_tags": chapter_tags,
                "error_types": Errata.TYPE_CHOICES,
                "prefill_qroc_text": prefill_qroc_text,
                "prefill_type": prefill_type,
            },
        )


class SessionDetailView(LoginRequiredMixin, View):
    """Detailed review of a past session — same logic as FinView."""

    template_name = "qcm/session_detail.html"

    def get(self, request, pk):
        session = QuizSession.objects.filter(user=request.user, pk=pk).first()
        if session is None:
            from django.http import Http404

            raise Http404
        if session.hidden_by_user:
            return redirect("qcm:history")

        total = session.session_questions.count()
        question_results = []
        total_score = 0.0

        for sq in session.session_questions.order_by("order"):
            q = sq.question
            user_answers = list(
                session.user_answers.filter(question=q).select_related("answer")
            )
            selected_ids = {ua.answer_id for ua in user_answers if ua.answer_id}
            raw_score = sum(ua.effective_fraction for ua in user_answers)
            score = max(0.0, min(1.0, raw_score))
            total_score += score
            if q.qtype == "shortanswer":
                max_score = 1.0
            else:
                max_score = sum(a.fraction for a in q.answers.filter(fraction__gt=0))
            ratio = score / max_score if max_score > 0 else 0.0

            qroc_text = next(
                (ua.qroc_text for ua in user_answers if ua.qroc_text is not None), None
            )
            accepted_answers = (
                list(q.answers.filter(fraction__gt=0).order_by("text"))
                if q.qtype == "shortanswer"
                else []
            )

            if not user_answers:
                status = "unanswered"
            elif ratio >= 1.0:
                status = "correct"
            elif ratio > 0:
                status = "partial"
            else:
                status = "incorrect"

            question_results.append(
                {
                    "question": q,
                    "answers": get_answers(q, shuffle=session.shuffle_answers),
                    "selected_ids": selected_ids,
                    "score": score,
                    "max_score": max_score,
                    "status": status,
                    "answered": bool(user_answers),
                    "qroc_text": qroc_text,
                    "accepted_answers": accepted_answers,
                    "zone_results": _build_zone_results(q, qroc_text),
                }
            )

        answered = sum(1 for r in question_results if r["answered"])
        correct = sum(1 for r in question_results if r["status"] == "correct")
        partial = sum(1 for r in question_results if r["status"] == "partial")
        incorrect = sum(1 for r in question_results if r["status"] == "incorrect")
        note_20 = round(total_score / total * 20, 1) if total > 0 else 0.0

        return render(
            request,
            self.template_name,
            {
                "session": session,
                "question_results": question_results,
                "total": total,
                "answered": answered,
                "correct": correct,
                "partial": partial,
                "incorrect": incorrect,
                "total_score": round(total_score, 2),
                "note_20": note_20,
            },
        )


class CourseStatsView(LoginRequiredMixin, View):
    """Stats breakdown by EC for a specific course."""

    template_name = "qcm/stats_course.html"

    def get(self, request, course_id):
        from .models import Course, Question, Tag

        course = get_object_or_404(Course, pk=course_id)
        user = request.user
        all_answers = UserAnswer.objects.filter(
            session__user=user, question__course=course
        )

        # Global course stats
        course_block = _compute_course_block(
            course, UserAnswer.objects.filter(session__user=user)
        )

        # EC tags with questions in this course
        ec_tag_ids = (
            Tag.objects.filter(
                category__tag_type="souscategorie",
                questions__course=course,
            )
            .distinct()
            .order_by("name")
        )

        from collections import defaultdict

        ec_stats = []
        for tag in ec_tag_ids:
            ec_answers = all_answers.filter(question__tags=tag)
            nb_available = Question.objects.filter(
                course=course,
                qtype__in=["multichoice", "shortanswer"],
                tags=tag,
            ).count()
            nb_done = ec_answers.values("question_id").distinct().count()
            pct_done = round(nb_done / nb_available * 100) if nb_available > 0 else 0

            # Question-level scoring: group answer fractions by (session, question)
            pair_fracs: dict = defaultdict(list)
            for ua in ec_answers.values(
                "session_id", "question_id", "answer__fraction", "is_correct"
            ):
                frac = _ua_fraction(ua["answer__fraction"], ua["is_correct"])
                pair_fracs[(ua["session_id"], ua["question_id"])].append(frac)

            nb_total_sessions = len(pair_fracs)

            if nb_total_sessions > 0:
                q_scores = [
                    max(0.0, min(1.0, sum(fracs))) for fracs in pair_fracs.values()
                ]
                note = round(sum(q_scores) / nb_total_sessions * 20, 1)
                correct = sum(1 for s in q_scores if s >= 1.0 - 1e-6)
                pct = round(correct / nb_total_sessions * 100)
            else:
                note = 0.0
                pct = 0

            nb_anchored = _compute_anchored_count(ec_answers)
            pct_anchored = (
                round(nb_anchored / nb_available * 100) if nb_available > 0 else 0
            )

            ec_stats.append(
                {
                    "tag": tag,
                    "nb_available": nb_available,
                    "nb_done": nb_done,
                    "nb_total_sessions": nb_total_sessions,
                    "pct_done": pct_done,
                    "note_20": note,
                    "pct_correct": pct,
                    "nb_anchored": nb_anchored,
                    "pct_anchored": pct_anchored,
                }
            )

        import json

        ec_json = json.dumps(
            [
                {
                    "nb_available": s["nb_available"],
                    "nb_done": s["nb_done"],
                    "nb_anchored": s["nb_anchored"],
                    "pct_done": s["pct_done"],
                    "pct_anchored": s["pct_anchored"],
                }
                for s in ec_stats
            ]
        )

        return render(
            request,
            self.template_name,
            {
                "course": course,
                "course_block": course_block,
                "ec_stats": ec_stats,
                "ec_json": ec_json,
            },
        )


class InscriptionView(View):
    """Public registration request page — no login required."""

    template_name = "registration/inscription.html"

    def get(self, request):
        form = InscriptionForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = InscriptionForm(request.POST, request.FILES)
        if form.is_valid():
            RegistrationRequest.objects.create(
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                email=form.cleaned_data["email"],
                year=form.cleaned_data.get("year", ""),
                parcours=form.cleaned_data.get("parcours", ""),
                message=form.cleaned_data.get("message", ""),
                certificate=form.cleaned_data.get("certificate"),
            )
            return redirect("qcm:inscription_done")
        return render(request, self.template_name, {"form": form})


class InscriptionDoneView(TemplateView):
    """Confirmation page after registration request."""

    template_name = "registration/inscription_done.html"


# ── Admin — Upload de questions Moodle XML ────────────────────────────────────


class AdminQuestionsUploadView(LoginRequiredMixin, View):
    """Staff-only: upload a Moodle XML question file."""

    template_name = "qcm/admin_questions_upload.html"

    def _staff_required(self, request):
        if not request.user.is_staff:
            from django.http import Http404

            raise Http404

    def _courses(self):
        return Course.objects.select_related("semester__study_year").order_by(
            "semester__study_year__order",
            "semester__order",
            "name",
        )

    def get(self, request):
        self._staff_required(request)
        success = request.GET.get("success")
        return render(
            request,
            self.template_name,
            {
                "courses": self._courses(),
                "success": int(success) if success and success.isdigit() else None,
            },
        )

    def post(self, request):
        self._staff_required(request)
        xml_file = request.FILES.get("xml_file")
        if not xml_file:
            return render(
                request,
                self.template_name,
                {
                    "courses": self._courses(),
                    "error": "Veuillez sélectionner un fichier XML.",
                },
            )

        from .question_upload import parse_moodle_xml

        try:
            questions = parse_moodle_xml(xml_file.read())
        except ValueError as exc:
            return render(
                request,
                self.template_name,
                {
                    "courses": self._courses(),
                    "error": f"Fichier invalide : {exc}",
                },
            )

        if not questions:
            return render(
                request,
                self.template_name,
                {
                    "courses": self._courses(),
                    "error": "Aucune question multichoix trouvée dans ce fichier.",
                },
            )

        request.session["upload_questions"] = questions
        return redirect("qcm:questions_preview")


class AdminQuestionsPreviewView(LoginRequiredMixin, View):
    """Staff-only: preview and edit parsed questions before confirming."""

    template_name = "qcm/admin_questions_preview.html"

    def get(self, request):
        if not request.user.is_staff:
            from django.http import Http404

            raise Http404
        questions = request.session.get("upload_questions")
        if not questions:
            return redirect("qcm:questions_upload")

        from .models import TagCategory

        courses = Course.objects.select_related("semester__study_year").order_by(
            "semester__study_year__order",
            "semester__order",
            "name",
        )
        tag_groups = [
            {"category": tc, "tags": list(tc.tags.order_by("name"))}
            for tc in TagCategory.objects.prefetch_related("tags").order_by(
                "tag_type", "name"
            )
            if tc.tags.exists()
        ]

        # Pre-match XML tag names to DB tag PKs (case-insensitive)
        tag_by_name = {t.name.lower(): t.pk for t in Tag.objects.all()}
        for q in questions:
            xml_tags = q.get("xml_tags", [])
            matched_names = {
                name.lower() for name in xml_tags if name.lower() in tag_by_name
            }
            q["matched_tag_ids"] = [str(tag_by_name[name]) for name in matched_names]
            q["matched_xml_names"] = list(matched_names)  # for template badge coloring

        return render(
            request,
            self.template_name,
            {
                "questions": questions,
                "courses": courses,
                "tag_groups": tag_groups,
                "fraction_choices": FRACTION_CHOICES,
                "fraction_choices_json": FRACTION_CHOICES_JSON,
            },
        )


class AdminQuestionsConfirmView(LoginRequiredMixin, View):
    """Staff-only: save uploaded questions to the database."""

    def post(self, request):
        if not request.user.is_staff:
            from django.http import Http404

            raise Http404

        course_id = request.POST.get("course_id")
        course = get_object_or_404(Course, pk=course_id)

        q_count = int(request.POST.get("q_count", 0))
        created = 0

        for n in range(q_count):
            text = request.POST.get(f"q_{n}_text", "").strip()
            feedback = request.POST.get(f"q_{n}_feedback", "").strip()
            a_count = int(request.POST.get(f"q_{n}_a_count", 0))

            if not text or a_count < 2:
                continue

            question = Question.objects.create(
                text=text,
                feedback=feedback,
                course=course,
                qtype=Question.MULTICHOICE,
                moodle_id=None,
            )

            for m in range(a_count):
                ans_text = request.POST.get(f"q_{n}_a_{m}_text", "").strip()
                try:
                    fraction = float(request.POST.get(f"q_{n}_a_{m}_fraction", "0"))
                except ValueError:
                    fraction = 0.0
                if ans_text:
                    Answer.objects.create(
                        text=ans_text,
                        question=question,
                        fraction=fraction,
                        is_correct=fraction > 0,
                    )

            tag_ids = request.POST.getlist(f"q_{n}_tag_ids")
            if tag_ids:
                question.tags.set(Tag.objects.filter(pk__in=tag_ids))

            created += 1

        request.session.pop("upload_questions", None)
        return redirect(f"/questions/upload/?success={created}")


class ErrataUploadImageView(LoginRequiredMixin, View):
    """Staff-only: upload an image for an errata of type IMAGE and accept it."""

    def post(self, request, pk):
        from django.http import Http404
        from django.utils import timezone

        if not request.user.is_staff:
            raise Http404
        errata = get_object_or_404(Errata, pk=pk)
        image_file = request.FILES.get("image_file")
        moodle_filename = request.POST.get("moodle_filename", "").strip()
        if image_file and moodle_filename:
            QuestionImage.objects.update_or_create(
                question=errata.question,
                moodle_filename=moodle_filename,
                defaults={"file": image_file},
            )
        errata.status = Errata.ACCEPTED
        errata.resolved_by = request.user
        errata.resolved_at = timezone.now()
        errata.save()

        from .models import Notification

        Notification.objects.create(
            user=errata.reported_by,
            message=(
                f"✅ Votre signalement « {errata.get_error_type_display()} » "
                f"a été accepté — merci pour votre contribution !"
            ),
            link="/",
        )
        return _errata_list_redirect(request)


# ---------------------------------------------------------------------------
# Profil utilisateur
# ---------------------------------------------------------------------------


class ProfileView(LoginRequiredMixin, View):
    template_name = "qcm/profile.html"

    def _build_context(self, request, form=None):
        from collections import defaultdict

        user = request.user
        if form is None:
            form = ProfileForm(user=user)

        reg = (
            RegistrationRequest.objects.filter(
                email=user.email, status=RegistrationRequest.ACCEPTED
            )
            .order_by("-created_at")
            .first()
        )

        # Même calcul que StatsView : grouper par (session, question)
        raw = list(
            UserAnswer.objects.filter(session__user=user).values(
                "session_id", "question_id", "is_correct", "answer__fraction"
            )
        )
        pair_fracs: dict = defaultdict(list)
        for r in raw:
            pair_fracs[(r["session_id"], r["question_id"])].append(
                _ua_fraction(r["answer__fraction"], r["is_correct"])
            )
        q_scores = [max(0.0, min(1.0, sum(fracs))) for fracs in pair_fracs.values()]
        total_questions = len(q_scores)
        avg_score = (
            round(sum(q_scores) / total_questions * 20, 1) if total_questions else None
        )

        user_profile, _ = UserProfile.objects.get_or_create(user=user)

        # Trophées
        from django.contrib.auth.models import User as AuthUser

        rarity_colors = {
            Trophy.GOLD: "#FFD700",
            Trophy.SILVER: "#B0B0B0",
            Trophy.BRONZE: "#CD7F32",
        }
        locked_color = "#2a2a2a"

        from django.db.models import Case, IntegerField, When

        year_order = Case(
            When(study_year=Trophy.YEAR_ALL, then=0),
            When(study_year=Trophy.YEAR_P2, then=1),
            When(study_year=Trophy.YEAR_D1, then=2),
            default=3,
            output_field=IntegerField(),
        )
        all_trophies = Trophy.objects.select_related("condition_tag").order_by(
            year_order, "name"
        )
        earned_map: dict = {
            ut.trophy_id: ut.unlocked_at
            for ut in UserTrophy.objects.filter(user=user).select_related("trophy")
        }
        total_users = max(1, AuthUser.objects.filter(is_active=True).count())
        trophy_data = []
        year_label_map = dict(Trophy.YEAR_CHOICES)
        for t in all_trophies:
            earned = t.pk in earned_map
            unlock_count = UserTrophy.objects.filter(trophy=t).count()
            pct = round(unlock_count / total_users * 100, 1)
            icon_color = rarity_colors.get(t.rarity, "#888") if earned else locked_color
            year_label = year_label_map.get(t.study_year, "Non classé")
            is_hidden = t.hidden and not earned
            trophy_data.append(
                {
                    "trophy": t,
                    "earned": earned,
                    "pct": pct,
                    "earned_at": earned_map.get(t.pk),
                    "icon_color": icon_color,
                    "year_label": year_label,
                    "is_hidden": is_hidden,
                }
            )
        earned_count = sum(1 for d in trophy_data if d["earned"])

        return {
            "form": form,
            "reg": reg,
            "total_questions": total_questions,
            "avg_score": avg_score,
            "saved": request.GET.get("saved") == "1",
            "user_profile": user_profile,
            "trophy_data": trophy_data,
            "earned_count": earned_count,
            "total_trophies": len(trophy_data),
        }

    def get(self, request):
        return render(request, self.template_name, self._build_context(request))

    def post(self, request):
        form = ProfileForm(request.POST, request.FILES, user=request.user)
        if not form.is_valid():
            return render(
                request, self.template_name, self._build_context(request, form=form)
            )
        form.save()
        return redirect(f"{reverse('qcm:profile')}?saved=1")
