from django.contrib import admin

from .models import (
    Answer,
    Category,
    Course,
    Question,
    QuizSession,
    Semester,
    StudyYear,
    UserAnswer,
)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ["name", "short_name"]
    search_fields = ["name", "short_name"]


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "course", "moodle_id"]
    list_filter = ["course"]
    search_fields = ["name"]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["moodle_id", "category", "qtype"]
    list_filter = ["qtype", "category__course"]
    search_fields = ["text", "moodle_id"]
    raw_id_fields = ["category"]


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ["question", "is_correct", "fraction"]
    list_filter = ["is_correct"]
    raw_id_fields = ["question"]


@admin.register(QuizSession)
class QuizSessionAdmin(admin.ModelAdmin):
    list_display = ["user", "course", "mode", "started_at", "completed_at"]
    list_filter = ["mode", "course"]
    raw_id_fields = ["user", "course"]


@admin.register(UserAnswer)
class UserAnswerAdmin(admin.ModelAdmin):
    list_display = ["session", "question", "is_correct", "answered_at"]
    list_filter = ["is_correct"]
    raw_id_fields = ["session", "question", "answer"]


@admin.register(StudyYear)
class StudyYearAdmin(admin.ModelAdmin):
    list_display = ["name", "order"]


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ["name", "study_year", "order"]
    list_filter = ["study_year"]
