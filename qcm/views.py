"""Views for the QCM training interface."""

import random
from typing import TYPE_CHECKING

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from .forms import InscriptionForm, SessionConfigForm
from .models import (
    Answer,
    Course,
    QuizSession,
    QuizSessionQuestion,
    RegistrationRequest,
    Semester,
    StudyYear,
    Tag,
    TagCategory,
    UserAnswer,
)


if TYPE_CHECKING:
    from .models import Question as QuestionModel


def get_answers(question: "QuestionModel", shuffle: bool = True) -> list:
    """Return answers, optionally shuffled with a deterministic seed."""
    answers = list(question.answers.all())
    if shuffle:
        random.Random(question.pk).shuffle(answers)
    return answers


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
            request, self.template_name, {"form": form, "semesters": semesters}
        )

    def post(self, request):
        form = SessionConfigForm(request.POST, user=request.user)
        if not form.is_valid():
            semesters = self._get_semesters(request.user)
            return render(
                request, self.template_name, {"form": form, "semesters": semesters}
            )

        courses = form.cleaned_data["courses"]
        mode = form.cleaned_data["mode"]
        nb_questions = form.cleaned_data["nb_questions"]
        tags = form.cleaned_data.get("tags")

        # Select random questions from chosen courses

        from .models import Question

        qs = Question.objects.filter(
            category__course__in=courses,
            qtype="multichoice",
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

        question_ids = list(qs.values_list("id", flat=True))
        random.shuffle(question_ids)
        question_ids = question_ids[:nb_questions]

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
        session = QuizSession.objects.create(
            user=request.user,
            course=first_course,
            mode="training" if mode == "training" else "training",
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
        session = get_object_or_404(QuizSession, pk=pk)
        total = session.session_questions.count()
        answered_question_ids = set(
            session.user_answers.values_list("question_id", flat=True).distinct()
        )
        answered_count = len(answered_question_ids)

        if answered_count >= total:
            return redirect("qcm:fin", pk=pk)

        # Find current question (first not answered)
        current_sq = (
            session.session_questions.exclude(question_id__in=answered_question_ids)
            .order_by("order")
            .first()
        )
        question = current_sq.question
        answers = get_answers(question, shuffle=session.shuffle_answers)

        return render(
            request,
            self.template_name,
            {
                "session": session,
                "question": question,
                "answers": answers,
                "position": answered_count + 1,
                "total": total,
                "mode": session.mode,
            },
        )


class CheckView(LoginRequiredMixin, View):
    def post(self, request, pk):
        session = get_object_or_404(QuizSession, pk=pk)
        answered_question_ids = set(
            session.user_answers.values_list("question_id", flat=True).distinct()
        )

        # Get current question
        current_sq = (
            session.session_questions.exclude(question_id__in=answered_question_ids)
            .order_by("order")
            .first()
        )
        if current_sq is None:
            return HttpResponse("Session terminée", status=400)

        question = current_sq.question
        selected_ids = request.POST.getlist("answers")

        # Record selected answers
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

        # If no answers selected, still mark as attempted (with dummy UserAnswer for tracking)
        if not selected_ids:
            # Mark question as "skipped" by creating a placeholder — not needed if no answers
            pass

        score = max(0.0, min(1.0, score))

        # Determine status
        max_score = sum(a.fraction for a in question.answers.filter(fraction__gt=0))
        ratio = score / max_score if max_score > 0 else 0.0

        if ratio >= 1.0:
            status = "correct"
        elif ratio > 0:
            status = "partial"
        else:
            status = "incorrect"

        total = session.session_questions.count()
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
                "answers": get_answers(question, shuffle=session.shuffle_answers),
                "selected_ids": [int(i) for i in selected_ids],
                "score": score,
                "status": status,
                "session": session,
                "is_last": is_last,
                "position": position,
                "total": total,
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
            selected_ids = {ua.answer_id for ua in user_answers}

            raw_score = sum(ua.answer.fraction for ua in user_answers)
            score = max(0.0, min(1.0, raw_score))
            total_score += score

            max_score = sum(a.fraction for a in q.answers.filter(fraction__gt=0))
            ratio = score / max_score if max_score > 0 else 0.0

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
                    cat.tags.filter(questions__category__course__in=courses)
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
    from .models import Question

    answers = all_answers.filter(question__category__course=course)
    nb_available = Question.objects.filter(
        category__course=course, qtype="multichoice"
    ).count()
    nb_done = answers.values("question_id").distinct().count()
    nb_total_sessions = (
        answers.count()
    )  # total attempts (same question can appear multiple times)

    if nb_total_sessions > 0:
        score = sum(
            min(1.0, max(0.0, ua.answer.fraction))
            for ua in answers.select_related("answer")
        )
        note = round(score / nb_total_sessions * 20, 1)
        correct = answers.filter(answer__fraction=1.0).count()
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

    def get(self, request):
        import json
        from datetime import timedelta

        from django.utils import timezone

        user = request.user

        # --- Global stats ---
        all_answers = UserAnswer.objects.filter(session__user=user)
        total_answered = all_answers.count()

        if total_answered > 0:
            correct = all_answers.filter(answer__fraction=1.0).count()
            partial = all_answers.filter(
                answer__fraction__gt=0.0, answer__fraction__lt=1.0
            ).count()
            incorrect = total_answered - correct - partial

            total_score = sum(
                min(1.0, max(0.0, ua.answer.fraction))
                for ua in all_answers.select_related("answer")
            )
            note_20 = round(total_score / total_answered * 20, 1)

            pct_correct = round(correct / total_answered * 100)
            pct_partial = round(partial / total_answered * 100)
            pct_incorrect = round(incorrect / total_answered * 100)
        else:
            correct = partial = incorrect = 0
            note_20 = 0.0
            pct_correct = pct_partial = pct_incorrect = 0

        total_sessions = QuizSession.objects.filter(user=user).count()

        # --- Per-course stats ---
        from .models import Course, UserEnrollment

        if user.is_staff:
            # Staff: show courses that have at least 1 answer
            answered_course_ids = all_answers.values_list(
                "question__category__course_id", flat=True
            ).distinct()
            enrolled_courses = list(
                Course.objects.filter(pk__in=answered_course_ids).order_by("name")
            )
        else:
            enrolled_courses = [
                e.course
                for e in UserEnrollment.objects.filter(user=user).select_related(
                    "course"
                )
            ]

        course_stats = [_compute_course_block(c, all_answers) for c in enrolled_courses]
        course_stats.sort(key=lambda x: x["course"].name)

        # Global anchored count
        from .models import Question

        total_available = Question.objects.filter(
            category__course__in=[c.pk for c in enrolled_courses],
            qtype="multichoice",
        ).count()
        total_done = all_answers.values("question_id").distinct().count()
        pct_done_global = (
            round(total_done / total_available * 100) if total_available > 0 else 0
        )
        total_anchored = _compute_anchored_count(all_answers)
        pct_anchored = (
            round(total_anchored / total_available * 100) if total_available > 0 else 0
        )

        # --- Weekly progression (last 8 weeks) ---
        now = timezone.now()
        weekly_data = []
        for i in range(7, -1, -1):
            week_start = now - timedelta(weeks=i + 1)
            week_end = now - timedelta(weeks=i)
            week_answers = all_answers.filter(
                session__started_at__gte=week_start,
                session__started_at__lt=week_end,
            )
            wcount = week_answers.count()
            if wcount > 0:
                wscore = sum(
                    min(1.0, max(0.0, ua.answer.fraction))
                    for ua in week_answers.select_related("answer")
                )
                wnote = round(wscore / wcount * 20, 1)
            else:
                wnote = None
            label = week_end.strftime("S%U")
            weekly_data.append({"label": label, "note": wnote})

        chart_labels = json.dumps([d["label"] for d in weekly_data])
        chart_data = json.dumps([d["note"] for d in weekly_data])

        return render(
            request,
            self.template_name,
            {
                "total_answered": total_answered,
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
                "chart_data": chart_data,
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
            QuizSession.objects.filter(user=request.user)
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

            # Note: aggregate per question (correct for multichoice)
            if answered_q_ids:
                total_q_score = 0.0
                for q_id in answered_q_ids:
                    q_ans = s.user_answers.filter(question_id=q_id).select_related(
                        "answer"
                    )
                    q_score = min(
                        1.0, max(0.0, sum(ua.answer.fraction for ua in q_ans))
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
                "question__category__course_id", flat=True
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


class SessionDetailView(LoginRequiredMixin, View):
    """Detailed review of a past session — same logic as FinView."""

    template_name = "qcm/session_detail.html"

    def get(self, request, pk):
        session = QuizSession.objects.filter(user=request.user, pk=pk).first()
        if session is None:
            from django.http import Http404

            raise Http404

        total = session.session_questions.count()
        question_results = []
        total_score = 0.0

        for sq in session.session_questions.order_by("order"):
            q = sq.question
            user_answers = list(
                session.user_answers.filter(question=q).select_related("answer")
            )
            selected_ids = {ua.answer_id for ua in user_answers}
            raw_score = sum(ua.answer.fraction for ua in user_answers)
            score = max(0.0, min(1.0, raw_score))
            total_score += score
            max_score = sum(a.fraction for a in q.answers.filter(fraction__gt=0))
            ratio = score / max_score if max_score > 0 else 0.0

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
            session__user=user, question__category__course=course
        )

        # Global course stats
        course_block = _compute_course_block(
            course, UserAnswer.objects.filter(session__user=user)
        )

        # EC tags with questions in this course
        ec_tag_ids = (
            Tag.objects.filter(
                category__tag_type="souscategorie",
                questions__category__course=course,
            )
            .distinct()
            .order_by("name")
        )

        ec_stats = []
        for tag in ec_tag_ids:
            ec_answers = all_answers.filter(question__tags=tag)
            nb_available = Question.objects.filter(
                category__course=course, qtype="multichoice", tags=tag
            ).count()
            nb_done = ec_answers.values("question_id").distinct().count()
            nb_total_sessions = ec_answers.count()
            pct_done = round(nb_done / nb_available * 100) if nb_available > 0 else 0

            if nb_total_sessions > 0:
                score = sum(
                    min(1.0, max(0.0, ua.answer.fraction))
                    for ua in ec_answers.select_related("answer")
                )
                note = round(score / nb_total_sessions * 20, 1)
                correct = ec_answers.filter(answer__fraction=1.0).count()
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
