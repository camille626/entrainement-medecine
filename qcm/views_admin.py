"""Views for the staff-only web admin interface (/admin-site/)."""

import secrets
import string

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Max
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .models import (
    Answer,
    Course,
    CoursePackage,
    ImageDragItem,
    ImageDropZone,
    ImageDropZoneLabel,
    Question,
    QuestionImage,
    RegistrationRequest,
    Semester,
    UserEnrollment,
)


# ── Mixin ─────────────────────────────────────────────────────────────────────


class StaffRequiredMixin(LoginRequiredMixin):
    """Redirect non-staff users to home instead of raising 403/404."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not request.user.is_staff:
            return redirect("qcm:home")
        return super().dispatch(request, *args, **kwargs)


# ── Shared business logic ──────────────────────────────────────────────────────


def _generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def accept_registration(req: RegistrationRequest, accepted_by: User) -> User | None:
    """Create a user account from a pending registration request.

    Returns the created User, or None if a user with that email already exists.
    """
    if User.objects.filter(email=req.email).exists():
        return None

    password = _generate_password()
    username = req.email.split("@")[0].lower()
    base = username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base}{counter}"
        counter += 1

    new_user = User.objects.create_user(
        username=username,
        email=req.email,
        password=password,  # pragma: allowlist secret
        first_name=req.first_name,
        last_name=req.last_name,
    )

    req.status = RegistrationRequest.ACCEPTED
    req.save()

    # Auto-enroll in matching CoursePackage
    if req.year or req.parcours:
        package_qs = CoursePackage.objects.all()
        if req.year:
            package_qs = package_qs.filter(year=req.year)
        if req.parcours:
            package_qs = package_qs.filter(parcours=req.parcours)
        package = package_qs.first()
        if package:
            for course in package.courses.all():
                UserEnrollment.objects.get_or_create(
                    user=new_user,
                    course=course,
                    defaults={"enrolled_by": accepted_by},
                )

    send_mail(
        subject="Accès accordé — Entraînement Médecine",
        message=(
            f"Bonjour {req.first_name},\n\n"
            f"Votre demande d'accès a été acceptée.\n\n"
            f"Identifiant : {username}\n"
            f"Mot de passe provisoire : {password}\n\n"  # pragma: allowlist secret
            f"Connectez-vous sur le site et pensez à changer votre mot de passe.\n\n"
            f"L'équipe Entraînement Médecine"
        ),
        from_email=None,
        recipient_list=[req.email],
        fail_silently=True,
    )
    return new_user


# ── Answer formset ────────────────────────────────────────────────────────────


AnswerFormSet: type[BaseInlineFormSet] = inlineformset_factory(
    Question,
    Answer,
    fields=["text", "fraction"],
    extra=2,
    can_delete=True,
)


# ── ddimageortext (légende interactive) : formsets et helpers ─────────────────


ImageDragItemFormSet: type[BaseInlineFormSet] = inlineformset_factory(
    Question,
    ImageDragItem,
    fields=["label"],
    extra=2,
    can_delete=True,
)

ImageDropZoneFormSet: type[BaseInlineFormSet] = inlineformset_factory(
    Question,
    ImageDropZone,
    fields=["xleft", "ytop", "correct_label"],
    extra=0,
    can_delete=True,
)


def _save_ddi_background_image(question: Question, request: HttpRequest) -> None:
    """Remplace l'image de fond unique d'une question ddimageortext.

    Une question ddimageortext n'a qu'une seule image conceptuelle (le fond) ;
    on supprime systématiquement les images existantes avant d'enregistrer la
    nouvelle, qu'elles viennent de cet admin (nom 'background') ou de l'import
    Moodle (nom de fichier d'origine, ex. 'oeil 150815.png').
    """
    image_file = request.FILES.get("new_bg_image_file")
    if not image_file:
        return
    for old in question.images.all():
        old.file.delete(save=False)
        old.delete()
    QuestionImage.objects.create(
        question=question,
        moodle_filename="background",
        file=image_file,
    )


def _save_ddi_drag_items(question: Question, request: HttpRequest) -> BaseInlineFormSet:
    """Sauvegarde les étiquettes (drag items), avec auto-assignation du champ `no`."""
    formset = ImageDragItemFormSet(request.POST, instance=question, prefix="dragform")
    if not formset.is_valid():
        return formset
    next_no = (question.drag_items.aggregate(Max("no"))["no__max"] or 0) + 1
    for form in formset.forms:
        if form in formset.deleted_forms:
            if form.instance.pk is not None:
                form.instance.delete()
            continue
        if not form.has_changed() and form.instance.pk is None:
            continue
        obj = form.save(commit=False)
        if obj.pk is None:
            obj.no = next_no
            next_no += 1
        obj.save()
    return formset


def _save_ddi_drop_zones(question: Question, request: HttpRequest) -> BaseInlineFormSet:
    """Sauvegarde les zones, leur `no` auto-assigné et leurs réponses alternatives acceptées."""
    formset = ImageDropZoneFormSet(request.POST, instance=question, prefix="zoneform")
    if not formset.is_valid():
        return formset
    next_no = (question.drop_zones.aggregate(Max("no"))["no__max"] or 0) + 1
    for form in formset.forms:
        if form in formset.deleted_forms:
            if form.instance.pk is not None:
                form.instance.delete()
            continue
        if not form.has_changed() and form.instance.pk is None:
            continue
        obj = form.save(commit=False)
        if obj.pk is None:
            obj.no = next_no
            next_no += 1
            obj.correct_drag_no = 0
        obj.save()
        alt_raw = request.POST.get(f"{form.prefix}-alts", "")
        alt_labels = [s.strip() for s in alt_raw.split(";") if s.strip()]
        obj.accepted_labels.all().delete()
        if alt_labels:
            ImageDropZoneLabel.objects.bulk_create(
                ImageDropZoneLabel(zone=obj, text=text) for text in alt_labels
            )
    return formset


# ── Views ─────────────────────────────────────────────────────────────────────


class AdminDashboardView(StaffRequiredMixin, View):
    template_name = "qcm/admin_site/dashboard.html"

    def get(self, request):
        pending_count = RegistrationRequest.objects.filter(
            status=RegistrationRequest.PENDING
        ).count()
        user_count = User.objects.count()
        question_count = Question.objects.count()
        course_count = Course.objects.count()
        return render(
            request,
            self.template_name,
            {
                "pending_count": pending_count,
                "user_count": user_count,
                "question_count": question_count,
                "course_count": course_count,
            },
        )


class AdminRegistrationsView(StaffRequiredMixin, View):
    template_name = "qcm/admin_site/registrations.html"

    def get(self, request):
        status_filter = request.GET.get("status", "pending")
        qs = RegistrationRequest.objects.order_by("-created_at")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return render(
            request,
            self.template_name,
            {
                "requests": qs[:100],
                "status_filter": status_filter,
                "status_choices": RegistrationRequest.STATUS_CHOICES,
            },
        )


class AdminAcceptRegistrationView(StaffRequiredMixin, View):
    def post(self, request, pk):
        req = get_object_or_404(RegistrationRequest, pk=pk)
        if req.status == RegistrationRequest.PENDING:
            accept_registration(req, request.user)
        return redirect("qcm:admin_registrations")


class AdminRejectRegistrationView(StaffRequiredMixin, View):
    def post(self, request, pk):
        req = get_object_or_404(RegistrationRequest, pk=pk)
        if req.status == RegistrationRequest.PENDING:
            req.status = RegistrationRequest.REJECTED
            req.save()
        return redirect("qcm:admin_registrations")


class AdminUsersView(StaffRequiredMixin, View):
    template_name = "qcm/admin_site/users.html"

    def get(self, request):
        search = request.GET.get("q", "").strip()
        qs = User.objects.order_by("username")
        if search:
            from django.db.models import Q

            qs = qs.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )

        packages = CoursePackage.objects.order_by("year", "parcours", "name")

        # Fetch accepted registration requests indexed by email for fast lookup
        reg_by_email = {
            r.email: r
            for r in RegistrationRequest.objects.filter(
                status=RegistrationRequest.ACCEPTED
            ).only("email", "year", "parcours")
        }

        # For each user, find the matching package (to pre-select in the dropdown)
        package_courses: dict[int, set[int]] = {
            pkg.pk: set(pkg.courses.values_list("id", flat=True)) for pkg in packages
        }
        user_rows = []
        for user in qs[:200]:
            enrolled_ids = set(
                UserEnrollment.objects.filter(user=user).values_list(
                    "course_id", flat=True
                )
            )
            matched_pkg = next(
                (
                    pkg_pk
                    for pkg_pk, course_ids in package_courses.items()
                    if course_ids and course_ids == enrolled_ids
                ),
                None,
            )
            reg = reg_by_email.get(user.email)
            user_rows.append(
                {
                    "user": user,
                    "package_pk": matched_pkg,
                    "year": reg.year if reg else None,
                    "parcours": reg.parcours if reg else None,
                }
            )

        return render(
            request,
            self.template_name,
            {"user_rows": user_rows, "search": search, "packages": packages},
        )


class AdminToggleUserView(StaffRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target.pk != request.user.pk:
            target.is_active = not target.is_active
            target.save()
        return redirect("qcm:admin_users")


class AdminDeleteUserView(StaffRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target.pk != request.user.pk:
            target.delete()
        return redirect("qcm:admin_users")


class AdminChangeUserYearView(StaffRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        package_id = request.POST.get("package")
        # Remove all current enrollments
        UserEnrollment.objects.filter(user=target).delete()
        # Add new enrollments from selected package
        if package_id:
            package = get_object_or_404(CoursePackage, pk=package_id)
            for course in package.courses.all():
                UserEnrollment.objects.create(
                    user=target, course=course, enrolled_by=request.user
                )
        return redirect("qcm:admin_users")


class AdminQuestionsView(StaffRequiredMixin, View):
    template_name = "qcm/admin_site/questions.html"

    SORT_FIELDS = {"updated_at", "-updated_at"}

    def get(self, request):
        from django.core.paginator import Paginator

        from .models import Tag, TagCategory

        # Guard against non-numeric values (e.g. "None" string from duplicate params)
        raw_course = request.GET.get("course", "")
        course_id = raw_course if raw_course.isdigit() else None
        qtype = request.GET.get("qtype", "").strip()
        search = request.GET.get("q", "").strip()
        tag_ids = [t for t in request.GET.getlist("tags") if t.isdigit()]
        exclude_tag_ids = [
            t for t in request.GET.getlist("exclude_tags") if t.isdigit()
        ]
        exclude_course_ids = [
            c for c in request.GET.getlist("exclude_courses") if c.isdigit()
        ]
        no_chapitre = request.GET.get("no_chapitre", "") == "1"
        no_ec = request.GET.get("no_ec", "") == "1"
        sort = request.GET.get("sort", "").strip()

        qs = Question.objects.select_related("course")
        if course_id:
            qs = qs.filter(course_id=course_id)
        if qtype:
            qs = qs.filter(qtype=qtype)
        if search:
            from django.db.models import Q

            qs = qs.filter(Q(text__icontains=search))
        if tag_ids:
            qs = qs.filter(tags__id__in=tag_ids).distinct()
        if exclude_tag_ids:
            qs = qs.exclude(tags__id__in=exclude_tag_ids)
        if exclude_course_ids:
            qs = qs.exclude(course_id__in=exclude_course_ids)
        if no_chapitre:
            qs = qs.exclude(tags__category__tag_type=TagCategory.CHAPITRE).distinct()
        if no_ec:
            qs = qs.exclude(
                tags__category__tag_type=TagCategory.SOUSCATEGORIE
            ).distinct()

        if sort in self.SORT_FIELDS:
            qs = qs.order_by(sort, "course__name", "moodle_id")
        else:
            qs = qs.order_by("course__name", "moodle_id")

        courses = Course.objects.order_by("name")

        available_tags_qs = Tag.objects.order_by("name")
        if course_id:
            available_tags_qs = available_tags_qs.filter(
                questions__course_id=course_id
            ).distinct()

        paginator = Paginator(qs, 50)
        page_number = request.GET.get("page", 1)
        page_obj = paginator.get_page(page_number)

        return render(
            request,
            self.template_name,
            {
                "questions": page_obj,
                "page_obj": page_obj,
                "courses": courses,
                "qtype_choices": Question.QTYPE_CHOICES,
                "selected_course": course_id or "",
                "selected_qtype": qtype,
                "search": search,
                "available_tags": available_tags_qs,
                "selected_tag_ids": {int(t) for t in tag_ids},
                "selected_exclude_tag_ids": {int(t) for t in exclude_tag_ids},
                "selected_exclude_course_ids": {int(c) for c in exclude_course_ids},
                "no_chapitre": no_chapitre,
                "no_ec": no_ec,
                "sort": sort,
                "total": qs.count(),
            },
        )


class AdminQuestionAddView(StaffRequiredMixin, View):
    template_name = "qcm/admin_site/question_form.html"

    def _ctx(self, **extra):
        from .models import Tag

        return {
            "courses": Course.objects.order_by("name"),
            "all_tags": Tag.objects.select_related("category").order_by(
                "category__tag_type", "name"
            ),
            "action": "add",
            "selected_qtype": Question.MULTICHOICE,
            "drag_formset": ImageDragItemFormSet(prefix="dragform"),
            "zone_formset": ImageDropZoneFormSet(prefix="zoneform"),
            **extra,
        }

    def get(self, request):
        selected_qtype = request.GET.get("qtype", Question.MULTICHOICE)
        return render(
            request,
            self.template_name,
            self._ctx(formset=AnswerFormSet(), selected_qtype=selected_qtype),
        )

    def post(self, request):
        import re
        from html import unescape

        def strip_html(s: str) -> str:
            return re.sub(r"<[^>]+>", "", unescape(s)).strip()

        text = request.POST.get("text", "").strip()
        course_id = request.POST.get("course")
        qtype = request.POST.get("qtype", Question.MULTICHOICE)
        feedback = request.POST.get("feedback", "").strip()

        course = get_object_or_404(Course, pk=course_id) if course_id else None

        if not text or not course:
            return render(
                request,
                self.template_name,
                self._ctx(
                    formset=AnswerFormSet(request.POST),
                    selected_qtype=qtype,
                    error="Le texte et le cours sont obligatoires.",
                ),
            )

        question = Question.objects.create(
            text=text, feedback=feedback, course=course, qtype=qtype
        )

        tag_ids = request.POST.getlist("tags")
        if tag_ids:
            from .models import Tag

            question.tags.set(Tag.objects.filter(pk__in=tag_ids))

        if qtype == Question.DDIMAGEORTEXT:
            _save_ddi_background_image(question, request)
            _save_ddi_drag_items(question, request)
            _save_ddi_drop_zones(question, request)
        else:
            formset = AnswerFormSet(request.POST, instance=question)
            if formset.is_valid():
                answers = formset.save(commit=False)
                for answer in answers:
                    answer.is_correct = answer.fraction > 0
                    answer.save()
                for answer in formset.deleted_objects:
                    answer.delete()

            image_file = request.FILES.get("new_image_file")
            image_filename = request.POST.get("new_image_filename", "").strip()
            if image_file and image_filename:
                QuestionImage.objects.create(
                    question=question,
                    moodle_filename=image_filename,
                    file=image_file,
                )

        return redirect("qcm:admin_questions")


class AdminQuestionEditView(StaffRequiredMixin, View):
    template_name = "qcm/admin_site/question_form.html"

    def _ctx(self, question, **extra):
        from django.db.models import Q

        from .models import Tag, TagCategory

        course = question.course
        selected_tag_ids = set(question.tags.values_list("id", flat=True))

        base_qs = (
            Tag.objects.filter(Q(questions__course=course) | Q(course=course))
            .select_related("category", "parent_ec")
            .exclude(category=None)
            .distinct()
        )

        annale_tags = list(
            base_qs.filter(category__tag_type=TagCategory.ANNEE).order_by("name")
        )
        ec_tags = list(
            base_qs.filter(category__tag_type=TagCategory.SOUSCATEGORIE).order_by(
                "name"
            )
        )
        ec_ids = {t.pk for t in ec_tags}

        # Chapter tags grouped by parent_ec pk (only ECs present in this course)
        chapter_tags_raw = list(
            base_qs.filter(
                category__tag_type=TagCategory.CHAPITRE,
                parent_ec_id__in=ec_ids,
            ).order_by("name")
        )
        chapter_tags_by_ec: dict[int, list] = {}
        for tag in chapter_tags_raw:
            chapter_tags_by_ec.setdefault(tag.parent_ec_id, []).append(tag)

        # If no ECs exist for this course, show chapter tags directly
        if not ec_tags:
            direct_chapters = list(
                base_qs.filter(category__tag_type=TagCategory.CHAPITRE).order_by("name")
            )
            ec_with_chapters: list = []
        else:
            direct_chapters = []
            ec_with_chapters = [
                {"ec": ec_tag, "chapters": chapter_tags_by_ec.get(ec_tag.pk, [])}
                for ec_tag in ec_tags
            ]

        return {
            "question": question,
            "courses": Course.objects.order_by("name"),
            "annale_tags": annale_tags,
            "ec_tags": ec_tags,
            "ec_with_chapters": ec_with_chapters,
            "direct_chapters": direct_chapters,
            "selected_tag_ids": selected_tag_ids,
            "action": "edit",
            "selected_qtype": question.qtype,
            "existing_images": list(question.images.all()),
            "existing_bg_image": question.images.first(),
            "drag_formset": ImageDragItemFormSet(instance=question, prefix="dragform"),
            "zone_formset": ImageDropZoneFormSet(instance=question, prefix="zoneform"),
            **extra,
        }

    def get(self, request, pk):
        question = get_object_or_404(Question, pk=pk)
        back_url = request.GET.get("back", "/admin-site/questions/")
        return render(
            request,
            self.template_name,
            self._ctx(
                question, formset=AnswerFormSet(instance=question), back_url=back_url
            ),
        )

    def post(self, request, pk):
        question = get_object_or_404(Question, pk=pk)
        back_url = request.POST.get("back_url", "/admin-site/questions/")
        text = request.POST.get("text", "").strip()
        course_id = request.POST.get("course")
        qtype = request.POST.get("qtype", question.qtype)
        feedback = request.POST.get("feedback", "").strip()

        if text:
            question.text = text
        if course_id:
            question.course_id = course_id
        question.qtype = qtype
        question.feedback = feedback
        question.save()

        tag_ids = request.POST.getlist("tags")
        from .models import Tag

        question.tags.set(Tag.objects.filter(pk__in=tag_ids))

        if qtype == Question.DDIMAGEORTEXT:
            _save_ddi_background_image(question, request)
            _save_ddi_drag_items(question, request)
            _save_ddi_drop_zones(question, request)
        else:
            formset = AnswerFormSet(request.POST, instance=question)
            if formset.is_valid():
                answers = formset.save(commit=False)
                for answer in answers:
                    answer.is_correct = answer.fraction > 0
                    answer.save()
                for answer in formset.deleted_objects:
                    answer.delete()

            # Handle image deletions
            for img in question.images.all():
                if request.POST.get(f"delete_image_{img.pk}"):
                    img.file.delete(save=False)
                    img.delete()

            # Handle new image upload
            image_file = request.FILES.get("new_image_file")
            image_filename = request.POST.get("new_image_filename", "").strip()
            if image_file and image_filename:
                QuestionImage.objects.update_or_create(
                    question=question,
                    moodle_filename=image_filename,
                    defaults={"file": image_file},
                )

        return redirect(back_url)


class AdminQuestionDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        question = get_object_or_404(Question, pk=pk)
        back_url = request.POST.get("back_url", "/admin-site/questions/")
        question.delete()
        return redirect(back_url)


class AdminCoursesView(StaffRequiredMixin, View):
    template_name = "qcm/admin_site/courses.html"

    def get(self, request):
        semesters = Semester.objects.select_related("study_year").order_by(
            "study_year__order", "order"
        )
        courses = Course.objects.select_related("semester__study_year").order_by("name")
        return render(
            request,
            self.template_name,
            {"courses": courses, "semesters": semesters},
        )

    def post(self, request):
        name = request.POST.get("name", "").strip()
        short_name = request.POST.get("short_name", "").strip()
        semester_id = request.POST.get("semester")
        if name and short_name:
            course = Course.objects.create(name=name, short_name=short_name)
            if semester_id:
                course.semester_id = semester_id
                course.save()
        return redirect("qcm:admin_courses")


class AdminCourseEditView(StaffRequiredMixin, View):
    def post(self, request, pk):
        course = get_object_or_404(Course, pk=pk)
        semester_id = request.POST.get("semester")
        if semester_id:
            course.semester_id = semester_id
        else:
            course.semester = None
        course.save()
        return redirect("qcm:admin_courses")


# ── Tags ──────────────────────────────────────────────────────────────────────


class AdminTagsView(StaffRequiredMixin, View):
    template_name = "qcm/admin_site/tags.html"

    def get(self, request):
        from .models import Tag, TagCategory

        category_filter = request.GET.get("category_type")
        tags_qs = Tag.objects.select_related(
            "category", "parent_ec", "course"
        ).order_by("category__tag_type", "name")
        if category_filter:
            tags_qs = tags_qs.filter(category__tag_type=category_filter)

        return render(
            request,
            self.template_name,
            {
                "tags": tags_qs,
                "tag_categories": TagCategory.objects.order_by("tag_type", "name"),
                "courses": Course.objects.order_by("name"),
                "ec_tags": Tag.objects.filter(
                    category__tag_type=TagCategory.SOUSCATEGORIE
                ).order_by("name"),
                "category_filter": category_filter,
                "tag_type_choices": TagCategory.TYPE_CHOICES,
            },
        )

    def post(self, request):
        from .models import Tag

        name = request.POST.get("name", "").strip()
        tag_category_id = request.POST.get("tag_category")
        course_id = request.POST.get("course")
        parent_ec_id = request.POST.get("parent_ec")

        if name and tag_category_id:
            tag, created = Tag.objects.get_or_create(
                name=name,
                defaults={
                    "category_id": tag_category_id,
                    "course_id": course_id or None,
                    "parent_ec_id": parent_ec_id or None,
                },
            )
            if not created:
                tag.category_id = tag_category_id
                tag.course_id = course_id or None
                tag.parent_ec_id = parent_ec_id or None
                tag.save()
        return redirect("qcm:admin_tags")


class AdminTagDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        from .models import Tag

        tag = get_object_or_404(Tag, pk=pk)
        tag.delete()
        return redirect("qcm:admin_tags")
