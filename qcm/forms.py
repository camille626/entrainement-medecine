from django import forms

from .models import Course, RegistrationRequest, Tag


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
