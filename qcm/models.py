from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


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


class Category(models.Model):
    name = models.CharField(max_length=255)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="categories"
    )
    moodle_id = models.IntegerField(unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

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
    moodle_id = models.IntegerField(unique=True)
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
    QTYPE_CHOICES = [
        (MULTICHOICE, "Choix multiple"),
        (SHORTANSWER, "Réponse courte"),
        (MATCH, "Appariement"),
    ]

    text = models.TextField()
    feedback = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="questions"
    )
    qtype = models.CharField(max_length=50, choices=QTYPE_CHOICES, default=MULTICHOICE)
    moodle_id = models.IntegerField(unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="questions")

    class Meta:
        ordering = ["moodle_id"]

    def __str__(self) -> str:
        return f"Question #{self.moodle_id or 'N/A'} ({self.category})"


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
        Answer, on_delete=models.PROTECT, related_name="user_answers"
    )
    is_correct = models.BooleanField()
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["answered_at"]

    def __str__(self) -> str:
        return f"Réponse de {self.session.user} à Q#{self.question_id}"


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
    OTHER = "autre"
    TYPE_CHOICES = [
        (POINTS, "Erreur d'attribution de points"),
        (CORRECTION, "Erreur dans la correction"),
        (IMAGE, "Image manquante"),
        (TAG, "Erreur de tag"),
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
    description = models.TextField(verbose_name="Description du problème")
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
