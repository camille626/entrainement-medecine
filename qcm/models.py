from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Course(models.Model):
    name = models.CharField(max_length=255)
    short_name = models.CharField(max_length=50)
    moodle_id = models.IntegerField(unique=True, null=True, blank=True)

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
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="questions"
    )
    qtype = models.CharField(max_length=50, choices=QTYPE_CHOICES, default=MULTICHOICE)
    moodle_id = models.IntegerField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["moodle_id"]

    def __str__(self) -> str:
        return f"Question #{self.moodle_id} ({self.category})"


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
        User, on_delete=models.CASCADE, related_name="quiz_sessions"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="sessions", null=True, blank=True
    )
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=TRAINING)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Session {self.mode} de {self.user} — {self.started_at:%d/%m/%Y}"


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
