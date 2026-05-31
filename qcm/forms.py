from django import forms

from .models import Course, Tag


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
