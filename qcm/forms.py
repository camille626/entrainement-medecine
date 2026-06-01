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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["courses"].queryset = Course.objects.select_related(
            "semester__study_year"
        ).order_by("semester__study_year__order", "semester__order", "name")
        self.fields["tags"].queryset = Tag.objects.order_by("name")


class InscriptionForm(forms.Form):
    first_name = forms.CharField(max_length=150, label="Prénom")
    last_name = forms.CharField(max_length=150, label="Nom")
    email = forms.EmailField(label="Email")
    message = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 4}),
        required=True,
        label="Message",
        help_text=(
            "Indiquez votre année (P2, D1...) et votre parcours (ex-PASS, ex-LAS...). "
            "Ex : Je suis en P2, ex-LAS, promo 2026."
        ),
    )
    certificate = forms.FileField(
        required=True,
        label="Certificat de scolarité (PDF)",
        help_text="Fichier PDF uniquement — justifie votre appartenance à l'université.",
    )

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
