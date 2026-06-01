import secrets
import string

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.mail import send_mail

from .models import (
    Answer,
    Category,
    Course,
    Question,
    QuizSession,
    RegistrationRequest,
    Semester,
    StudyYear,
    Tag,
    TagCategory,
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


@admin.register(TagCategory)
class TagCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "tag_type", "course", "order"]
    list_filter = ["tag_type", "course"]
    search_fields = ["name"]
    ordering = ["order", "name"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "moodle_id", "category", "parent_ec", "course"]
    list_filter = ["category__tag_type", "category", "course"]
    search_fields = ["name"]
    raw_id_fields = ["parent_ec"]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["moodle_id", "category", "qtype"]
    list_filter = ["qtype", "category__course", "tags"]
    search_fields = ["text", "moodle_id"]
    raw_id_fields = ["category"]
    filter_horizontal = ["tags"]


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


def _generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@admin.register(RegistrationRequest)
class RegistrationRequestAdmin(admin.ModelAdmin):
    list_display = [
        "email",
        "first_name",
        "last_name",
        "status",
        "created_at",
        "certificate",
    ]
    list_filter = ["status"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["-created_at"]
    actions = ["accept_requests", "reject_requests"]

    @admin.action(description="✅ Accepter les demandes sélectionnées")
    def accept_requests(self, request, queryset):
        accepted = 0
        for req in queryset.filter(status=RegistrationRequest.PENDING):
            if User.objects.filter(email=req.email).exists():
                continue
            password = _generate_password()
            username = req.email.split("@")[0].lower()
            # Ensure unique username
            base = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base}{counter}"
                counter += 1

            User.objects.create_user(
                username=username,
                email=req.email,
                password=password,  # pragma: allowlist secret
                first_name=req.first_name,
                last_name=req.last_name,
            )
            req.status = RegistrationRequest.ACCEPTED
            req.save()

            send_mail(
                subject="Accès accordé — Entraînement Médecine",
                message=(
                    f"Bonjour {req.first_name},\n\n"
                    f"Votre demande d'accès a été acceptée.\n\n"
                    f"Identifiant : {username}\n"
                    f"Mot de passe provisoire : {password}\n\n"  # pragma: allowlist secret
                    f"Connectez-vous sur : http://127.0.0.1:8000/login/\n\n"
                    f"Pensez à changer votre mot de passe après votre première connexion.\n\n"
                    f"L'équipe Entraînement Médecine"
                ),
                from_email=None,
                recipient_list=[req.email],
                fail_silently=True,
            )
            accepted += 1

        self.message_user(
            request, f"{accepted} demande(s) acceptée(s), compte(s) créé(s)."
        )

    @admin.action(description="❌ Refuser les demandes sélectionnées")
    def reject_requests(self, request, queryset):
        count = queryset.filter(status=RegistrationRequest.PENDING).update(
            status=RegistrationRequest.REJECTED
        )
        self.message_user(request, f"{count} demande(s) refusée(s).")
