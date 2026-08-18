"""Service de fusion/conversion de tags EC scopée à un cours (issue #108/#115).

Réutilisé par la commande `manage.py merge_tags` et par la vue admin
`AdminTagMergeView` — aucune règle métier dupliquée entre les deux.
"""

from dataclasses import dataclass

from django.db import transaction

from qcm.models import Course, Question, Tag, TagCategory


class TagMergeError(Exception):
    """Erreur métier de fusion/conversion de tags (tags identiques, parent EC invalide...)."""


@dataclass
class MergeResult:
    questions_migrated: int
    reparented_tags: list[str]


@dataclass
class ConvertToChapterResult:
    questions_updated: int


def merge_course_tags(
    course: Course, from_tag: Tag, to_tag: Tag, dry_run: bool = False
) -> MergeResult:
    """Fusionne `from_tag` dans `to_tag` pour les questions d'un seul cours.

    Reparente aussi (`parent_ec`) les tags-chapitres scopés à ce cours qui
    pointaient vers `from_tag`. Ne touche ni au `Tag` `from_tag` lui-même ni
    aux questions des autres cours.
    """
    if from_tag.pk == to_tag.pk:
        raise TagMergeError("Les tags source et cible doivent être différents.")

    questions = list(Question.objects.filter(course=course, tags=from_tag))
    reparent_tags = Tag.objects.filter(course=course, parent_ec=from_tag)
    reparent_names = list(reparent_tags.values_list("name", flat=True))

    if dry_run:
        return MergeResult(
            questions_migrated=len(questions), reparented_tags=reparent_names
        )

    with transaction.atomic():
        for q in questions:
            q.tags.add(to_tag)
            q.tags.remove(from_tag)
        reparent_tags.update(parent_ec=to_tag)

    return MergeResult(
        questions_migrated=len(questions), reparented_tags=reparent_names
    )


def convert_tag_to_chapter(
    course: Course, tag: Tag, parent_ec: Tag, dry_run: bool = False
) -> ConvertToChapterResult:
    """Convertit `tag` (EC) en tag chapitre rattaché à `parent_ec`, scopé au cours.

    Ajoute aussi `parent_ec` aux questions du cours taguées `tag` (un tag
    chapitre coexiste toujours avec son EC parent sur les questions).
    """
    if (
        not parent_ec.category
        or parent_ec.category.tag_type != TagCategory.SOUSCATEGORIE
    ):
        raise TagMergeError(f"'{parent_ec.name}' n'est pas un tag EC (souscategorie).")

    chapter_category = TagCategory.objects.filter(
        tag_type=TagCategory.CHAPITRE, course__isnull=True
    ).first()
    if chapter_category is None:
        raise TagMergeError("Catégorie globale 'Chapitre' introuvable en base.")

    questions = list(Question.objects.filter(course=course, tags=tag))

    if dry_run:
        return ConvertToChapterResult(questions_updated=len(questions))

    with transaction.atomic():
        tag.category = chapter_category
        tag.parent_ec = parent_ec
        tag.course = course
        tag.save(update_fields=["category", "parent_ec", "course"])
        for q in questions:
            q.tags.add(parent_ec)

    return ConvertToChapterResult(questions_updated=len(questions))
