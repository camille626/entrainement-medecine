"""Management command : initialise la liste des trophées."""

from django.core.management.base import BaseCommand

from qcm.models import Tag, Trophy


TROPHIES = [
    # Bronze
    {
        "name": "Première Victoire",
        "description": "Compléter sa première session",
        "icon_emoji": "🎯",
        "rarity": Trophy.BRONZE,
        "condition_type": Trophy.SESSIONS_COUNT,
        "condition_value": 1,
        "condition_tag_name": None,
    },
    {
        "name": "Curieux",
        "description": "Réaliser 10 questions",
        "icon_emoji": "🔍",
        "rarity": Trophy.BRONZE,
        "condition_type": Trophy.QUESTIONS_COUNT,
        "condition_value": 10,
        "condition_tag_name": None,
    },
    {
        "name": "Bonne lancée",
        "description": "Réaliser 50 questions",
        "icon_emoji": "🚀",
        "rarity": Trophy.BRONZE,
        "condition_type": Trophy.QUESTIONS_COUNT,
        "condition_value": 50,
        "condition_tag_name": None,
    },
    # Argent
    {
        "name": "Perfectionniste",
        "description": "Obtenir un 20/20 sur une session",
        "icon_emoji": "✨",
        "rarity": Trophy.SILVER,
        "condition_type": Trophy.PERFECT_SESSION,
        "condition_value": 1,
        "condition_tag_name": None,
    },
    {
        "name": "Assidu",
        "description": "Réaliser 200 questions",
        "icon_emoji": "📚",
        "rarity": Trophy.SILVER,
        "condition_type": Trophy.QUESTIONS_COUNT,
        "condition_value": 200,
        "condition_tag_name": None,
    },
    {
        "name": "Sérieux",
        "description": "Compléter 10 sessions",
        "icon_emoji": "🎓",
        "rarity": Trophy.SILVER,
        "condition_type": Trophy.SESSIONS_COUNT,
        "condition_value": 10,
        "condition_tag_name": None,
    },
    {
        "name": "Chirurgical",
        "description": "Obtenir 100 bonnes réponses",
        "icon_emoji": "🔬",
        "rarity": Trophy.SILVER,
        "condition_type": Trophy.CORRECT_COUNT,
        "condition_value": 100,
        "condition_tag_name": None,
    },
    # Or
    {
        "name": "Marathonien",
        "description": "Réaliser 1000 questions",
        "icon_emoji": "🏅",
        "rarity": Trophy.GOLD,
        "condition_type": Trophy.QUESTIONS_COUNT,
        "condition_value": 1000,
        "condition_tag_name": None,
    },
    {
        "name": "Régulier",
        "description": "Compléter 50 sessions",
        "icon_emoji": "📅",
        "rarity": Trophy.GOLD,
        "condition_type": Trophy.SESSIONS_COUNT,
        "condition_value": 50,
        "condition_tag_name": None,
    },
    {
        "name": "Expert",
        "description": "Obtenir 500 bonnes réponses",
        "icon_emoji": "🧠",
        "rarity": Trophy.GOLD,
        "condition_type": Trophy.CORRECT_COUNT,
        "condition_value": 500,
        "condition_tag_name": None,
    },
    {
        "name": "Natural Killer",
        "description": "Réaliser 500 questions d'immunologie",
        "icon_emoji": "⚔️",
        "rarity": Trophy.GOLD,
        "condition_type": Trophy.QUESTIONS_COUNT_TAG,
        "condition_value": 500,
        "condition_tag_name": "Immunologie",
    },
    {
        "name": "Hématologue",
        "description": "Obtenir 200 bonnes réponses en hématologie",
        "icon_emoji": "🩸",
        "rarity": Trophy.GOLD,
        "condition_type": Trophy.CORRECT_COUNT_TAG,
        "condition_value": 200,
        "condition_tag_name": "Hématologie",
    },
    # Argent — communauté
    {
        "name": "Vision d'Aigle",
        "description": "Avoir correctement signalé 5 questions (5 erratas acceptés par l'admin)",
        "icon_emoji": "🦅",
        "rarity": Trophy.SILVER,
        "condition_type": Trophy.ERRATAS_ACCEPTED,
        "condition_value": 5,
        "condition_tag_name": None,
    },
    # Bronze — singularités
    {
        "name": "Dazed and Confused",
        "description": "Obtenir 0 point sur 50 questions distinctes",
        "icon_emoji": "😵",
        "rarity": Trophy.BRONZE,
        "condition_type": Trophy.ZERO_SCORE_COUNT,
        "condition_value": 50,
        "condition_tag_name": None,
        "study_year": "",
        "hidden": False,
    },
    {
        "name": "ST+",
        "description": "Obtenir 0 point sur 10 questions d'ECG",
        "icon_emoji": "📈",
        "rarity": Trophy.BRONZE,
        "condition_type": Trophy.ZERO_SCORE_COUNT_TAG,
        "condition_value": 10,
        "condition_tag_name": "ECG",
        "study_year": Trophy.YEAR_P2,
        "hidden": True,
    },
]


class Command(BaseCommand):
    help = "Initialise ou met à jour la liste des trophées (idempotent)"

    def handle(self, *args, **options):
        created_count = 0
        skipped_count = 0

        for data in TROPHIES:
            tag_name = data.pop("condition_tag_name")
            condition_tag = None

            if tag_name:
                try:
                    condition_tag = Tag.objects.get(name=tag_name)
                except Tag.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Tag '{tag_name}' introuvable — trophée '{data['name']}' créé sans tag."
                        )
                    )

            _, created = Trophy.objects.get_or_create(
                name=data["name"],
                defaults={**data, "condition_tag": condition_tag},
            )
            if created:
                created_count += 1
                self.stdout.write(f"  ✅ Créé : {data['icon_emoji']} {data['name']}")
            else:
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{created_count} trophée(s) créé(s), {skipped_count} déjà existant(s)."
            )
        )
