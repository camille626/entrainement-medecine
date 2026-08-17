"""Template tags and filters for the qcm app."""

import re

from django import template
from django.utils.safestring import mark_safe


register = template.Library()

_PLUGINFILE_RE = re.compile(r'@@PLUGINFILE@@/([^"\'>\s]+)')


@register.filter
def pluginfile_names(text: str) -> list[str]:
    """Return list of filenames referenced as @@PLUGINFILE@@/filename in text."""
    return _PLUGINFILE_RE.findall(text or "")


_P_WITH_BR_RE = re.compile(
    r"<p([^>]*)>((?:(?!</p>).)*?<br\s*/?>(?:(?!</p>).)*)</p>",
    re.IGNORECASE | re.DOTALL,
)
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)


@register.filter
def quillify(html: str) -> str:
    """Split a <p> containing mid-paragraph <br> into one <p> per line.

    Quill (used to edit Question.text/feedback) loads existing HTML via
    `quill.root.innerHTML = ...`, which does not visually preserve a <br>
    in the middle of a <p> — the lines end up concatenated and illegible.
    Splitting into one <p> per line matches how Quill itself represents
    multi-line text, so it stays readable once loaded and is preserved on
    the next save.
    """

    def _split(match: re.Match[str]) -> str:
        attrs, inner = match.group(1), match.group(2)
        return "".join(f"<p{attrs}>{line}</p>" for line in _BR_RE.split(inner))

    return mark_safe(_P_WITH_BR_RE.sub(_split, html or ""))
