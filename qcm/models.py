import re

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


_PLUGINFILE_IMG_RE = re.compile(
    r'<img\b([^>]*)src=["\']@@PLUGINFILE@@/([^"\'>\s]+)["\']([^>]*)>',
    re.IGNORECASE,
)


class StudyYear(models.Model):
    name = models.CharField(max_length=20)
    order = models.IntegerField()

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return self.name


class Semester(models.Model):
    study_year = models.ForeignKey(
        StudyYear, on_delete=models.CASCADE, related_name="semesters"
    )
    name = models.CharField(max_length=20)
    order = models.IntegerField()

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return f"{self.study_year} — {self.name}"


class Course(models.Model):
    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=50)
    moodle_id = models.IntegerField(unique=True, null=True, blank=True)
    semester = models.ForeignKey(
        Semester,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TagCategory(models.Model):
    ANNEE = "annee"
    SOUSCATEGORIE = "souscategorie"
    CHAPITRE = "chapitre"
    TYPE_CHOICES = [
        (ANNEE, "Annales par année"),
        (SOUSCATEGORIE, "Sous-catégorie de cours"),
        (CHAPITRE, "Chapitre"),
    ]

    name = models.CharField(max_length=100)
    tag_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=ANNEE)
    course = models.ForeignKey(
        "Course",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="tag_categories",
    )
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "catégorie de tag"
        verbose_name_plural = "catégories de tags"

    def __str__(self) -> str:
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True)
    moodle_id = models.IntegerField(unique=True, null=True, blank=True)
    category = models.ForeignKey(
        TagCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tags",
    )
    parent_ec = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chapter_tags",
        verbose_name="EC parente (pour les tags chapitres)",
        limit_choices_to={"category__tag_type": "souscategorie"},
    )
    course = models.ForeignKey(
        "Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chapter_tags",
        verbose_name="Cours (pour les tags chapitres)",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Question(models.Model):
    MULTICHOICE = "multichoice"
    SHORTANSWER = "shortanswer"
    MATCH = "match"
    DDIMAGEORTEXT = "ddimageortext"
    QTYPE_CHOICES = [
        (MULTICHOICE, "Choix multiple"),
        (SHORTANSWER, "Réponse courte"),
        (MATCH, "Appariement"),
        (DDIMAGEORTEXT, "Légende interactive"),
    ]

    text = models.TextField()
    feedback = models.TextField(blank=True)
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="questions",
    )
    qtype = models.CharField(max_length=50, choices=QTYPE_CHOICES, default=MULTICHOICE)
    moodle_id = models.IntegerField(unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="questions")

    class Meta:
        ordering = ["moodle_id"]

    def __str__(self) -> str:
        return f"Question #{self.moodle_id or 'N/A'} ({self.course})"

    def render_text(self) -> str:
        """Return question text with @@PLUGINFILE@@ refs resolved to media URLs."""
        images_map = {img.moodle_filename: img.file.url for img in self.images.all()}

        def _replace(m: re.Match) -> str:
            before_src, filename, after_src = m.group(1), m.group(2), m.group(3)
            if filename in images_map:
                return f'<img{before_src}src="{images_map[filename]}"{after_src}>'
            return (
                '<span class="badge bg-secondary border">⚠ Image non disponible</span>'
            )

        return _PLUGINFILE_IMG_RE.sub(_replace, self.text)


class QuestionImage(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="images"
    )
    moodle_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to="question_images/")

    class Meta:
        unique_together = [("question", "moodle_filename")]
        verbose_name = "Image de question"
        verbose_name_plural = "Images de questions"

    def __str__(self) -> str:
        return f"Image {self.moodle_filename} pour Q#{self.question_id}"


class Answer(models.Model):
    text = models.TextField()
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="answers"
    )
    fraction = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="1.0 = correcte, 0.0 = incorrecte",
    )
    is_correct = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Réponse {'correcte' if self.is_correct else 'incorrecte'} pour Q#{self.question_id}"


class QuizSession(models.Model):
    TRAINING = "training"
    REVIEW = "review"
    MODE_CHOICES = [
        (TRAINING, "Entraînement"),
        (REVIEW, "Révision"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="quiz_sessions",
        null=True,
        blank=True,
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="sessions", null=True, blank=True
    )
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=TRAINING)
    shuffle_answers = models.BooleanField(default=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    hidden_by_user = models.BooleanField(default=False)
    questions: models.ManyToManyField = models.ManyToManyField(
        "Question",
        through="QuizSessionQuestion",
        related_name="sessions",
        blank=True,
    )

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        user_str = str(self.user) if self.user else "anonyme"
        return f"Session {self.mode} de {user_str} — {self.started_at:%d/%m/%Y}"


class QuizSessionQuestion(models.Model):
    session = models.ForeignKey(
        QuizSession, on_delete=models.CASCADE, related_name="session_questions"
    )
    question = models.ForeignKey(
        "Question", on_delete=models.CASCADE, related_name="session_questions"
    )
    order = models.IntegerField()

    class Meta:
        ordering = ["order"]
        unique_together = [("session", "question")]

    def __str__(self) -> str:
        return f"Session {self.session_id} Q#{self.question_id} (ordre {self.order})"


class UserAnswer(models.Model):
    session = models.ForeignKey(
        QuizSession, on_delete=models.CASCADE, related_name="user_answers"
    )
    question = models.ForeignKey(
        Question, on_delete=models.PROTECT, related_name="user_answers"
    )
    answer = models.ForeignKey(
        Answer,
        on_delete=models.PROTECT,
        related_name="user_answers",
        null=True,
        blank=True,
    )
    is_correct = models.BooleanField()
    # QROC-specific fields (null for multichoice questions)
    qroc_text = models.TextField(null=True, blank=True)
    is_self_evaluated = models.BooleanField(default=False)
    # ddimageortext: partial fraction override (computed from zone results)
    fraction_override = models.FloatField(null=True, blank=True)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["answered_at"]

    def __str__(self) -> str:
        return f"Réponse de {self.session.user} à Q#{self.question_id}"

    @property
    def effective_fraction(self) -> float:
        """Fraction effective : fraction_override > answer.fraction > is_correct (QROC)."""
        if self.fraction_override is not None:
            return self.fraction_override
        if self.answer_id is not None and self.answer is not None:
            return self.answer.fraction
        return 1.0 if self.is_correct else 0.0


class CoursePackage(models.Model):
    YEAR_P2 = "P2"
    YEAR_D1 = "D1"
    YEAR_CHOICES = [(YEAR_P2, "P2 (DFGSM2)"), (YEAR_D1, "D1 (DFGSM3)")]

    PARCOURS_PASS = "PASS"
    PARCOURS_LAS1 = "LAS1"
    PARCOURS_LAS2 = "LAS2"
    PARCOURS_CHOICES = [
        (PARCOURS_PASS, "Ancien PASS"),
        (PARCOURS_LAS1, "Ancien LAS1"),
        (PARCOURS_LAS2, "Ancien LAS2"),
    ]

    name = models.CharField(max_length=100, unique=True, verbose_name="Nom du menu")
    description = models.TextField(blank=True, verbose_name="Description")
    year = models.CharField(
        max_length=10, choices=YEAR_CHOICES, blank=True, verbose_name="Année"
    )
    parcours = models.CharField(
        max_length=10, choices=PARCOURS_CHOICES, blank=True, verbose_name="Parcours"
    )
    courses = models.ManyToManyField(
        Course, blank=True, related_name="packages", verbose_name="Cours inclus"
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Menu d'inscription"
        verbose_name_plural = "Menus d'inscription"

    def __str__(self) -> str:
        return self.name


class UserEnrollment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="enrollments"
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    enrolled_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrollments_created",
    )

    class Meta:
        unique_together = [("user", "course")]
        ordering = ["course__name"]
        verbose_name = "Inscription"
        verbose_name_plural = "Inscriptions"

    def __str__(self) -> str:
        return f"{self.user.username} → {self.course.name}"


class RegistrationRequest(models.Model):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "En attente"),
        (ACCEPTED, "Acceptée"),
        (REJECTED, "Refusée"),
    ]

    first_name = models.CharField(max_length=150, verbose_name="Prénom")
    last_name = models.CharField(max_length=150, verbose_name="Nom")
    email = models.EmailField(unique=True, verbose_name="Email")
    year = models.CharField(
        max_length=10,
        choices=CoursePackage.YEAR_CHOICES,
        verbose_name="Année d'entrée",
        default="",
    )
    parcours = models.CharField(
        max_length=10,
        choices=CoursePackage.PARCOURS_CHOICES,
        blank=True,
        verbose_name="Parcours antérieur",
    )
    message = models.TextField(blank=True, verbose_name="Message complémentaire")
    certificate = models.FileField(
        upload_to="certificates/",
        verbose_name="Certificat de scolarité (PDF)",
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Demande d'inscription"
        verbose_name_plural = "Demandes d'inscription"

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name} <{self.email}> — {self.get_status_display()}"


class Notification(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{'Lu' if self.read else 'Non lu'}] {self.user.username}: {self.message[:50]}"


class Errata(models.Model):
    POINTS = "points"
    CORRECTION = "correction"
    IMAGE = "image"
    TAG = "tag"
    QROC_ANSWER = "qroc_answer"
    OTHER = "autre"
    TYPE_CHOICES = [
        (POINTS, "Erreur d'attribution de points"),
        (CORRECTION, "Erreur dans la correction"),
        (IMAGE, "Image manquante"),
        (TAG, "Erreur de tag"),
        (QROC_ANSWER, "Ma réponse est correcte (QROC)"),
        (OTHER, "Autre"),
    ]

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "En attente"),
        (ACCEPTED, "Accepté"),
        (REJECTED, "Refusé"),
    ]

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="erratas"
    )
    reported_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="erratas_reported"
    )
    error_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description = models.TextField(verbose_name="Description du problème", blank=True)
    # QROC-specific fields for "ma réponse est correcte"
    qroc_suggested_text = models.TextField(
        blank=True, verbose_name="Réponse suggérée (QROC)"
    )
    qroc_suggested_fraction = models.FloatField(
        null=True,
        blank=True,
        verbose_name="Fraction suggérée (QROC)",
        help_text="1.0 = réponse complète, 0.7 = réponse partielle, etc.",
    )
    concerned_answers = models.ManyToManyField(
        Answer, blank=True, related_name="erratas", verbose_name="Réponses concernées"
    )
    suggested_tags = models.ManyToManyField(
        Tag, blank=True, related_name="erratas", verbose_name="Tags suggérés"
    )
    admin_note = models.TextField(blank=True, verbose_name="Note admin")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erratas_resolved",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Errata"
        verbose_name_plural = "Erratas"

    def __str__(self) -> str:
        return f"[{self.get_error_type_display()}] Q#{self.question_id} — {self.reported_by.username}"


class ImageDragItem(models.Model):
    """Étiquette draggable pour une question ddimageortext."""

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="drag_items"
    )
    no = models.IntegerField()
    label = models.CharField(max_length=500)
    draggroup = models.IntegerField(default=1)

    class Meta:
        ordering = ["no"]
        unique_together = [("question", "no")]
        verbose_name = "Étiquette drag"
        verbose_name_plural = "Étiquettes drag"

    def __str__(self) -> str:
        return f"Drag #{self.no} '{self.label}' (Q#{self.question_id})"


class ImageDropZone(models.Model):
    """Zone cible positionnée sur l'image de fond d'une question ddimageortext."""

    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="drop_zones"
    )
    no = models.IntegerField()
    xleft = models.IntegerField()
    ytop = models.IntegerField()
    correct_drag_no = models.IntegerField()
    correct_label = models.CharField(max_length=500)

    class Meta:
        ordering = ["no"]
        unique_together = [("question", "no")]
        verbose_name = "Zone drop"
        verbose_name_plural = "Zones drop"

    def __str__(self) -> str:
        return f"Zone #{self.no} '{self.correct_label}' (Q#{self.question_id})"

    @property
    def accepted_labels_text(self) -> str:
        """Labels alternatifs acceptés, joints par '; ' (pour pré-remplir le formulaire admin)."""
        return "; ".join(self.accepted_labels.values_list("text", flat=True))


class ImageDropZoneLabel(models.Model):
    """Réponse alternative acceptée pour une zone ddimageortext (en plus du label principal)."""

    zone = models.ForeignKey(
        ImageDropZone, on_delete=models.CASCADE, related_name="accepted_labels"
    )
    text = models.CharField(max_length=500)

    class Meta:
        verbose_name = "Label accepté (zone)"
        verbose_name_plural = "Labels acceptés (zone)"

    def __str__(self) -> str:
        return f"'{self.text}' (zone #{self.zone_id})"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    photo = models.ImageField(upload_to="profile_photos/", blank=True, null=True)

    class Meta:
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"

    def __str__(self) -> str:
        return f"Profil de {self.user.username}"


class Trophy(models.Model):
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    RARITY_CHOICES = [
        (BRONZE, "Bronze"),
        (SILVER, "Argent"),
        (GOLD, "Or"),
    ]

    QUESTIONS_COUNT = "questions_count"
    CORRECT_COUNT = "correct_count"
    QUESTIONS_COUNT_TAG = "questions_count_tag"
    CORRECT_COUNT_TAG = "correct_count_tag"
    PERFECT_SESSION = "perfect_session"
    SESSIONS_COUNT = "sessions_count"
    ERRATAS_ACCEPTED = "erratas_accepted"
    ZERO_SCORE_COUNT = "zero_score_count"
    ZERO_SCORE_COUNT_TAG = "zero_score_count_tag"
    LOGIN_COUNT = "login_count"
    CONSECUTIVE_DAYS = "consecutive_days"
    CONDITION_CHOICES = [
        (QUESTIONS_COUNT, "Nombre de questions réalisées"),
        (CORRECT_COUNT, "Nombre de bonnes réponses"),
        (QUESTIONS_COUNT_TAG, "Nombre de questions réalisées (tag)"),
        (CORRECT_COUNT_TAG, "Nombre de bonnes réponses (tag)"),
        (PERFECT_SESSION, "Session parfaite (20/20)"),
        (SESSIONS_COUNT, "Nombre de sessions complétées"),
        (ERRATAS_ACCEPTED, "Erratas acceptés par l'admin"),
        (ZERO_SCORE_COUNT, "Questions avec score nul (0 point)"),
        (ZERO_SCORE_COUNT_TAG, "Questions avec score nul (0 point) — tag"),
        (LOGIN_COUNT, "Nombre de connexions à la plateforme"),
        (CONSECUTIVE_DAYS, "Jours de connexion consécutifs"),
    ]

    YEAR_ALL = "ALL"
    YEAR_P2 = "P2"
    YEAR_D1 = "D1"
    YEAR_CHOICES = [
        (YEAR_ALL, "Transversal"),
        (YEAR_P2, "P2"),
        (YEAR_D1, "D1"),
    ]

    name = models.CharField(max_length=100, unique=True, verbose_name="Nom")
    description = models.TextField(verbose_name="Description")
    icon_emoji = models.CharField(max_length=10, default="🏆", verbose_name="Emoji")
    rarity = models.CharField(
        max_length=10,
        choices=RARITY_CHOICES,
        verbose_name="Rareté",
    )
    study_year = models.CharField(
        max_length=5,
        choices=YEAR_CHOICES,
        blank=True,
        default="",
        verbose_name="Année",
    )
    hidden = models.BooleanField(
        default=False,
        verbose_name="Masqué avant obtention",
    )
    condition_type = models.CharField(
        max_length=30,
        choices=CONDITION_CHOICES,
        verbose_name="Type de condition",
    )
    condition_value = models.IntegerField(default=1, verbose_name="Valeur seuil")
    condition_tag = models.ForeignKey(
        Tag,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trophies",
        verbose_name="Tag (pour trophées par EC)",
    )

    class Meta:
        verbose_name = "Trophée"
        verbose_name_plural = "Trophées"

    def __str__(self) -> str:
        return f"{self.icon_emoji} {self.name} ({self.get_rarity_display()})"


class UserTrophy(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_trophies"
    )
    trophy = models.ForeignKey(
        Trophy, on_delete=models.CASCADE, related_name="user_trophies"
    )
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "trophy")]
        ordering = ["-unlocked_at"]
        verbose_name = "Trophée utilisateur"
        verbose_name_plural = "Trophées utilisateurs"

    def __str__(self) -> str:
        return f"{self.user.username} — {self.trophy.name}"


class LoginEvent(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="login_events"
    )
    logged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Connexion"
        verbose_name_plural = "Connexions"
        indexes = [models.Index(fields=["user", "logged_at"])]

    def __str__(self) -> str:
        return f"{self.user.username} — {self.logged_at.date()}"
