"""Management command: list questions with unresolved @@PLUGINFILE@@ image refs."""

import re

from django.core.management.base import BaseCommand

from qcm.models import Question


_PLUGINFILE_RE = re.compile(r'@@PLUGINFILE@@/([^"\'>\s]+)')


class Command(BaseCommand):
    help = "List questions with unresolved @@PLUGINFILE@@ image references"

    def handle(self, *args, **options):
        questions = Question.objects.filter(
            text__contains="@@PLUGINFILE@@"
        ).prefetch_related("images", "category__course")
        if not questions.exists():
            self.stdout.write(
                self.style.SUCCESS("Aucune référence @@PLUGINFILE@@ trouvée.")
            )
            return

        missing_count = 0
        for q in questions:
            filenames = _PLUGINFILE_RE.findall(q.text)
            uploaded = {img.moodle_filename for img in q.images.all()}
            missing = [f for f in filenames if f not in uploaded]
            if missing:
                missing_count += 1
                self.stdout.write(
                    f"Q#{q.moodle_id or q.pk} "
                    f"({q.category.course.short_name}): "
                    f"manquant [{', '.join(missing)}]"
                )

        if missing_count == 0:
            self.stdout.write(
                self.style.SUCCESS("Toutes les images référencées ont été uploadées.")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{missing_count} question(s) avec des images manquantes."
                )
            )
