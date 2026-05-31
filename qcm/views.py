"""Views for the QCM training interface."""

import random
from typing import TYPE_CHECKING

from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from .forms import SessionConfigForm
from .models import (
    Answer,
    QuizSession,
    QuizSessionQuestion,
    Semester,
    StudyYear,
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


class HomeView(TemplateView):
    template_name = "qcm/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        years = StudyYear.objects.prefetch_related("semesters__courses").order_by(
            "order"
        )
        ctx["years"] = years
        ctx["total_questions"] = sum(
            c.categories.aggregate_question_count()
            if hasattr(c.categories, "aggregate_question_count")
            else 0
            for y in years
            for s in y.semesters.all()
            for c in s.courses.all()
        )
        return ctx


class ConfigurationView(View):
    template_name = "qcm/configuration.html"

    def get(self, request):
        form = SessionConfigForm()
        semesters = (
            Semester.objects.select_related("study_year")
            .prefetch_related("courses")
            .order_by("study_year__order", "order")
        )
        return render(
            request, self.template_name, {"form": form, "semesters": semesters}
        )

    def post(self, request):
        form = SessionConfigForm(request.POST)
        if not form.is_valid():
            semesters = (
                Semester.objects.select_related("study_year")
                .prefetch_related("courses")
                .order_by("study_year__order", "order")
            )
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
            qs = qs.filter(tags__in=tags).distinct()

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
            course=first_course,
            mode="training" if mode == "training" else "training",
            shuffle_answers=form.cleaned_data.get("shuffle_answers", True),
        )
        for i, q_id in enumerate(question_ids, start=1):
            QuizSessionQuestion.objects.create(
                session=session, question_id=q_id, order=i
            )

        return redirect("qcm:question", pk=session.pk)


class QuestionView(View):
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


class CheckView(View):
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


class FinView(View):
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
