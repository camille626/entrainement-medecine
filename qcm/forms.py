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
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="Message (optionnel)",
        help_text="Ex : Je suis étudiant en P2, promo 2026...",
    )

    def clean_email(self):
        email = self.cleaned_data["email"]
        if RegistrationRequest.objects.filter(email=email).exists():
            raise forms.ValidationError(
                "Une demande avec cet email existe déjà. Contactez l'administrateur."
            )
        return email
