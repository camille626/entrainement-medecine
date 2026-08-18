"""Service de fusion/conversion de tags EC scopée à un cours (issue #108/#115).

Réutilisé par la commande `manage.py merge_tags` et par la vue admin
`AdminTagMergeView` — aucune règle métier dupliquée entre les deux.
"""

from dataclasses import dataclass

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from qcm.models import Course, Question, Tag, TagCategory, TagMergeLog


class TagMergeError(Exception):
    """Erreur métier de fusion/conversion de tags (tags identiques, parent EC invalide...)."""


@dataclass
class MergeResult:
    questions_migrated: int
    reparented_tags: list[str]
    log_id: int | None = None


@dataclass
class ConvertToChapterResult:
    questions_updated: int
    log_id: int | None = None


def merge_course_tags(
    course: Course,
    from_tag: Tag,
    to_tag: Tag,
    dry_run: bool = False,
    performed_by: User | None = None,
) -> MergeResult:
    """Fusionne `from_tag` dans `to_tag` pour les questions d'un seul cours.

    Reparente aussi (`parent_ec`) les tags-chapitres scopés à ce cours qui
    pointaient vers `from_tag`. Ne touche ni au `Tag` `from_tag` lui-même ni
    aux questions des autres cours. Enregistre un `TagMergeLog` (sauf en
    dry-run) permettant d'annuler l'opération via `undo_tag_merge_log`.
    """
    if from_tag.pk == to_tag.pk:
        raise TagMergeError("Les tags source et cible doivent être différents.")

    questions = list(Question.objects.filter(course=course, tags=from_tag))
    question_ids = [q.pk for q in questions]
    already_had_to_tag_ids = list(
        Question.objects.filter(pk__in=question_ids, tags=to_tag).values_list(
            "pk", flat=True
        )
    )
    reparent_tags = Tag.objects.filter(course=course, parent_ec=from_tag)
    reparent_names = list(reparent_tags.values_list("name", flat=True))
    reparent_ids = list(reparent_tags.values_list("pk", flat=True))

    if dry_run:
        return MergeResult(
            questions_migrated=len(questions), reparented_tags=reparent_names
        )

    with transaction.atomic():
        for q in questions:
            q.tags.add(to_tag)
            q.tags.remove(from_tag)
        reparent_tags.update(parent_ec=to_tag)

        log = TagMergeLog.objects.create(
            action=TagMergeLog.MERGE,
            course=course,
            summary=(
                f"Fusion « {from_tag.name} » → « {to_tag.name} » ({course.name}) : "
                f"{len(questions)} question(s) migrée(s), "
                f"{len(reparent_ids)} tag(s)-chapitres reparenté(s)."
            ),
            snapshot={
                "from_tag_id": from_tag.pk,
                "to_tag_id": to_tag.pk,
                "question_ids": question_ids,
                "already_had_to_tag_ids": already_had_to_tag_ids,
                "reparented_tag_ids": reparent_ids,
            },
            performed_by=performed_by,
        )

    return MergeResult(
        questions_migrated=len(questions),
        reparented_tags=reparent_names,
        log_id=log.pk,
    )


def convert_tag_to_chapter(
    course: Course,
    tag: Tag,
    parent_ec: Tag,
    dry_run: bool = False,
    performed_by: User | None = None,
) -> ConvertToChapterResult:
    """Convertit `tag` (EC) en tag chapitre rattaché à `parent_ec`, scopé au cours.

    Ajoute aussi `parent_ec` aux questions du cours taguées `tag` (un tag
    chapitre coexiste toujours avec son EC parent sur les questions).
    Enregistre un `TagMergeLog` (sauf en dry-run) permettant d'annuler
    l'opération via `undo_tag_merge_log`.
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
    question_ids = [q.pk for q in questions]
    already_had_parent_ec_ids = list(
        Question.objects.filter(pk__in=question_ids, tags=parent_ec).values_list(
            "pk", flat=True
        )
    )

    if dry_run:
        return ConvertToChapterResult(questions_updated=len(questions))

    previous_category_id = tag.category_id
    previous_parent_ec_id = tag.parent_ec_id
    previous_course_id = tag.course_id

    with transaction.atomic():
        tag.category = chapter_category
        tag.parent_ec = parent_ec
        tag.course = course
        tag.save(update_fields=["category", "parent_ec", "course"])
        for q in questions:
            q.tags.add(parent_ec)

        log = TagMergeLog.objects.create(
            action=TagMergeLog.CONVERT_TO_CHAPTER,
            course=course,
            summary=(
                f"« {tag.name} » converti en chapitre de « {parent_ec.name} » "
                f"({course.name}) : {len(questions)} question(s) mise(s) à jour."
            ),
            snapshot={
                "tag_id": tag.pk,
                "parent_ec_id": parent_ec.pk,
                "previous_category_id": previous_category_id,
                "previous_parent_ec_id": previous_parent_ec_id,
                "previous_course_id": previous_course_id,
                "question_ids": question_ids,
                "already_had_parent_ec_ids": already_had_parent_ec_ids,
            },
            performed_by=performed_by,
        )

    return ConvertToChapterResult(questions_updated=len(questions), log_id=log.pk)


def undo_tag_merge_log(log: TagMergeLog) -> None:
    """Annule une fusion/conversion enregistrée, si ce n'est pas déjà fait.

    Restaure l'état tel que capturé au moment de l'opération d'origine ; si
    les mêmes tags ont été modifiés par une opération ultérieure entretemps,
    l'annulation peut ne pas être exacte (pas de versioning complet).
    """
    if log.undone_at is not None:
        raise TagMergeError("Cette opération a déjà été annulée.")

    data = log.snapshot

    try:
        with transaction.atomic():
            if log.action == TagMergeLog.MERGE:
                from_tag = Tag.objects.get(pk=data["from_tag_id"])
                to_tag = Tag.objects.get(pk=data["to_tag_id"])
                already_had = set(data["already_had_to_tag_ids"])
                for qid in data["question_ids"]:
                    q = Question.objects.get(pk=qid)
                    q.tags.add(from_tag)
                    if qid not in already_had:
                        q.tags.remove(to_tag)
                Tag.objects.filter(pk__in=data["reparented_tag_ids"]).update(
                    parent_ec=from_tag
                )
            else:
                tag = Tag.objects.get(pk=data["tag_id"])
                parent_ec = Tag.objects.get(pk=data["parent_ec_id"])
                tag.category_id = data["previous_category_id"]
                tag.parent_ec_id = data["previous_parent_ec_id"]
                tag.course_id = data["previous_course_id"]
                tag.save(update_fields=["category", "parent_ec", "course"])
                already_had = set(data["already_had_parent_ec_ids"])
                for qid in data["question_ids"]:
                    if qid not in already_had:
                        q = Question.objects.get(pk=qid)
                        q.tags.remove(parent_ec)

            log.undone_at = timezone.now()
            log.save(update_fields=["undone_at"])
    except (Tag.DoesNotExist, Question.DoesNotExist) as exc:
        raise TagMergeError(
            "Impossible d'annuler : un tag ou une question impliqué(e) n'existe plus."
        ) from exc
