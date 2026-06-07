from django import forms
from django.contrib.auth.models import User

from .models import Course, RegistrationRequest, Tag, UserProfile


class SessionConfigForm(forms.Form):
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Cours",
    )
    mode = forms.ChoiceField(
        choices=[
            ("training", "Flash (correction immédiate)"),
            ("deferred", "Différé (correction à la fin)"),
        ],
        widget=forms.RadioSelect,
        initial="training",
        label="Mode",
    )
    nb_questions = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=10,
        label="Nombre de questions",
    )
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Filtrer par tags (optionnel)",
    )
    shuffle_answers = forms.BooleanField(
        required=False,
        initial=True,
        label="Propositions en ordre aléatoire (non alphabétique)",
    )
    include_qroc = forms.BooleanField(
        required=False,
        initial=False,
        label="Inclure les QROC (réponses ouvertes courtes)",
        help_text="Les questions QROC nécessitent de taper une réponse libre.",
    )
    include_ddimageortext = forms.BooleanField(
        required=False,
        initial=False,
        label="Inclure les légendes interactives (image à annoter)",
        help_text="Questions où il faut placer des étiquettes sur une image.",
    )
    question_filter = forms.ChoiceField(
        choices=[
            ("all", "Toutes les questions (aléatoire)"),
            (
                "review",
                "Mode révision — questions ratées ou jamais faites (taux < 50%)",
            ),
            ("never", "Questions jamais faites uniquement"),
            (
                "anchor",
                "Mode ancrage ⚓ — questions non encore ancrées (< 3 réussites)",
            ),
        ],
        widget=forms.RadioSelect,
        initial="all",
        required=False,
        label="Sélection des questions",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Course.objects.select_related("semester__study_year").order_by(
            "semester__study_year__order", "semester__order", "name"
        )
        # Staff see all courses; regular users only see enrolled courses
        if user is not None and not user.is_staff:
            qs = qs.filter(enrollments__user=user)
        self.fields["courses"].queryset = qs
        self.fields["tags"].queryset = Tag.objects.order_by("name")


class InscriptionForm(forms.Form):
    first_name = forms.CharField(max_length=150, label="Prénom")
    last_name = forms.CharField(max_length=150, label="Nom")
    email = forms.EmailField(label="Email")
    year = forms.ChoiceField(
        choices=[],
        label="Année d'entrée",
    )
    parcours = forms.ChoiceField(
        choices=[],
        required=False,
        label="Parcours antérieur (si P2)",
    )
    message = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Message complémentaire (optionnel)",
    )
    certificate = forms.FileField(
        required=True,
        label="Certificat de scolarité (PDF)",
        help_text="Fichier PDF uniquement — justifie votre appartenance à l'université.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import CoursePackage

        self.fields["year"].choices = [("", "— Sélectionnez votre année —")] + list(
            CoursePackage.YEAR_CHOICES
        )
        self.fields["parcours"].choices = [("", "— Sans parcours antérieur —")] + list(
            CoursePackage.PARCOURS_CHOICES
        )

    def clean(self):
        cleaned = super().clean()
        year = cleaned.get("year")
        parcours = cleaned.get("parcours")
        if not year:
            self.add_error("year", "Ce champ est obligatoire.")
        if year == "P2" and not parcours:
            self.add_error(
                "parcours", "Veuillez sélectionner votre parcours antérieur."
            )
        return cleaned

    def clean_email(self):
        email = self.cleaned_data["email"]
        if RegistrationRequest.objects.filter(email=email).exists():
            raise forms.ValidationError(
                "Une demande avec cet email existe déjà. Contactez l'administrateur."
            )
        return email

    def clean_certificate(self):
        cert = self.cleaned_data.get("certificate")
        if cert:
            if not cert.name.lower().endswith(".pdf"):
                raise forms.ValidationError("Seuls les fichiers PDF sont acceptés.")
            if cert.size > 5 * 1024 * 1024:  # 5 MB
                raise forms.ValidationError("Le fichier ne doit pas dépasser 5 Mo.")
        return cert


class ProfileForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False, label="Prénom")
    last_name = forms.CharField(max_length=150, required=False, label="Nom")
    email = forms.EmailField(label="Adresse e-mail")
    photo = forms.ImageField(
        required=False,
        label="Photo de profil",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user
        if user is not None:
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
            self.fields["email"].initial = user.email

    def clean_email(self):
        email = self.cleaned_data["email"]
        if (
            self._user is not None
            and User.objects.filter(email=email).exclude(pk=self._user.pk).exists()
        ):
            raise forms.ValidationError("Cette adresse e-mail est déjà utilisée.")
        return email

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "size") and photo.size > 2 * 1024 * 1024:
            raise forms.ValidationError("La photo ne doit pas dépasser 2 Mo.")
        return photo

    def save(self):
        u = self._user
        assert u is not None
        u.first_name = self.cleaned_data["first_name"]
        u.last_name = self.cleaned_data["last_name"]
        u.email = self.cleaned_data["email"]
        u.save(update_fields=["first_name", "last_name", "email"])
        photo = self.cleaned_data.get("photo")
        if photo:
            profile, _ = UserProfile.objects.get_or_create(user=u)
            profile.photo = photo
            profile.save()
        return u
