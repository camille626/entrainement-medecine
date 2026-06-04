from django.contrib import admin
from django.contrib.auth.models import User as DjangoUser

from .models import (
    Answer,
    Category,
    Course,
    CoursePackage,
    Errata,
    Notification,
    Question,
    QuestionImage,
    QuizSession,
    RegistrationRequest,
    Semester,
    StudyYear,
    Tag,
    TagCategory,
    UserAnswer,
    UserEnrollment,
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


class QuestionImageInline(admin.TabularInline):
    model = QuestionImage
    extra = 1
    fields = ["moodle_filename", "file"]


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ["moodle_id", "category", "qtype"]
    list_filter = ["qtype", "category__course", "tags"]
    search_fields = ["text", "moodle_id"]
    raw_id_fields = ["category"]
    filter_horizontal = ["tags"]
    inlines = [QuestionImageInline]


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


class UserEnrollmentInline(admin.TabularInline):
    model = UserEnrollment
    fk_name = "user"
    extra = 1
    fields = ["course", "enrolled_at"]
    readonly_fields = ["enrolled_at"]
    autocomplete_fields = ["course"]


class UserAdminWithEnrollments(admin.ModelAdmin):
    inlines = [UserEnrollmentInline]
    list_display = ["username", "email", "first_name", "last_name", "is_staff"]
    search_fields = ["username", "email", "first_name", "last_name"]
    actions = ["apply_package"]

    @admin.action(
        description="📦 Appliquer un menu d'inscription aux utilisateurs sélectionnés"
    )
    def apply_package(self, request, queryset):
        package_id = request.POST.get("package_id")
        if not package_id:
            self.message_user(
                request,
                "Sélectionnez un menu dans l'URL : /admin/auth/user/?package_id=<id>",
                level="warning",
            )
            return
        try:
            package = CoursePackage.objects.get(pk=package_id)
        except CoursePackage.DoesNotExist:
            self.message_user(request, "Menu introuvable.", level="error")
            return
        count = 0
        for user in queryset:
            for course in package.courses.all():
                _, created = UserEnrollment.objects.get_or_create(
                    user=user,
                    course=course,
                    defaults={"enrolled_by": request.user},
                )
                if created:
                    count += 1
        self.message_user(
            request,
            f"{count} inscription(s) créée(s) pour {queryset.count()} utilisateur(s) via le menu « {package.name} ».",
        )


admin.site.unregister(DjangoUser)
admin.site.register(DjangoUser, UserAdminWithEnrollments)


@admin.register(UserEnrollment)
class UserEnrollmentAdmin(admin.ModelAdmin):
    list_display = ["user", "course", "enrolled_at", "enrolled_by"]
    list_filter = ["course__semester__study_year", "course__semester", "course"]
    search_fields = ["user__username", "user__email", "course__name"]
    raw_id_fields = ["user", "enrolled_by"]
    actions = ["enroll_in_semester"]

    @admin.action(
        description="📚 Inscrire les utilisateurs sélectionnés au même semestre"
    )
    def enroll_in_semester(self, request, queryset):
        pass  # placeholder — bulk enrollment by semester implemented via UserAdmin inline


@admin.register(CoursePackage)
class CoursePackageAdmin(admin.ModelAdmin):
    list_display = ["name", "description", "course_count"]
    search_fields = ["name"]
    filter_horizontal = ["courses"]

    @admin.display(description="Nb cours")
    def course_count(self, obj):
        return obj.courses.count()

    def get_urls(self):
        from django.urls import path

        urls = super().get_urls()
        custom = [
            path(
                "<int:package_id>/apply/<int:user_id>/",
                self.admin_site.admin_view(self.apply_to_user),
                name="coursepackage_apply_to_user",
            ),
        ]
        return custom + urls

    def apply_to_user(self, request, package_id, user_id):
        from django.contrib import messages
        from django.shortcuts import redirect

        try:
            package = CoursePackage.objects.get(pk=package_id)
            user = DjangoUser.objects.get(pk=user_id)
        except (CoursePackage.DoesNotExist, DjangoUser.DoesNotExist):
            messages.error(request, "Menu ou utilisateur introuvable.")
            return redirect("..")
        count = 0
        for course in package.courses.all():
            _, created = UserEnrollment.objects.get_or_create(
                user=user,
                course=course,
                defaults={"enrolled_by": request.user},
            )
            if created:
                count += 1
        messages.success(
            request,
            f"{count} inscription(s) ajoutée(s) à {user.username} via le menu « {package.name} ».",
        )
        return redirect(f"/admin/auth/user/{user_id}/change/")


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
        from .views_admin import accept_registration

        accepted = sum(
            1
            for req in queryset.filter(status=RegistrationRequest.PENDING)
            if accept_registration(req, request.user) is not None
        )
        self.message_user(
            request, f"{accepted} demande(s) acceptée(s), compte(s) créé(s)."
        )

    @admin.action(description="❌ Refuser les demandes sélectionnées")
    def reject_requests(self, request, queryset):
        count = queryset.filter(status=RegistrationRequest.PENDING).update(
            status=RegistrationRequest.REJECTED
        )
        self.message_user(request, f"{count} demande(s) refusée(s).")


class AnswerInlineForErrata(admin.TabularInline):
    model = Answer
    extra = 0
    fields = ["text", "fraction", "is_correct"]
    readonly_fields = ["text"]

    def get_queryset(self, request):
        return super().get_queryset(request)


@admin.register(Errata)
class ErrataAdmin(admin.ModelAdmin):
    list_display = [
        "question_short",
        "error_type",
        "reported_by",
        "status",
        "created_at",
    ]
    list_filter = ["status", "error_type", "question__category__course"]
    search_fields = ["description", "reported_by__username", "question__text"]
    ordering = ["-created_at"]
    filter_horizontal = ["concerned_answers", "suggested_tags"]
    readonly_fields = [
        "question",
        "reported_by",
        "created_at",
        "resolved_at",
        "resolved_by",
    ]
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "question",
                    "reported_by",
                    "error_type",
                    "status",
                    "description",
                    "admin_note",
                ),
            },
        ),
        (
            "QROC — réponse suggérée",
            {
                "fields": ("qroc_suggested_text", "qroc_suggested_fraction"),
                "classes": ("collapse",),
                "description": "Renseignez une fraction avant d'accepter (1.0 = réponse complète).",
            },
        ),
        (
            "Références",
            {
                "fields": ("concerned_answers", "suggested_tags"),
                "classes": ("collapse",),
            },
        ),
        (
            "Métadonnées",
            {
                "fields": ("created_at", "resolved_at", "resolved_by"),
                "classes": ("collapse",),
            },
        ),
    )
    actions = ["accept_erratas", "reject_erratas"]

    @admin.display(description="Question")
    def question_short(self, obj):
        text = obj.question.text[:60].replace("<p>", "").replace("</p>", "")
        return f"Q#{obj.question_id} — {text}"

    @admin.action(description="✅ Accepter les erratas sélectionnés")
    def accept_erratas(self, request, queryset):
        from django.utils import timezone

        count = 0
        for errata in queryset.filter(status=Errata.PENDING):
            errata.status = Errata.ACCEPTED
            errata.resolved_by = request.user
            errata.resolved_at = timezone.now()
            errata.save()

            # If tag error: apply suggested tags
            if errata.error_type == Errata.TAG and errata.suggested_tags.exists():
                errata.question.tags.set(errata.suggested_tags.all())

            # Notify the reporter via in-app notification
            Notification.objects.create(
                user=errata.reported_by,
                message=(
                    f"Votre signalement ({errata.get_error_type_display()}) "
                    f"sur la question #{errata.question_id} a été accepté. Merci !"
                ),
                link="/errata/",
            )
            count += 1

        self.message_user(request, f"{count} errata(s) accepté(s).")

    @admin.action(description="❌ Refuser les erratas sélectionnés")
    def reject_erratas(self, request, queryset):
        from django.utils import timezone

        count = queryset.filter(status=Errata.PENDING).update(
            status=Errata.REJECTED,
            resolved_by=request.user,
            resolved_at=timezone.now(),
        )
        self.message_user(request, f"{count} errata(s) refusé(s).")
