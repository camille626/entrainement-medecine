"""Template tags and filters for the qcm app."""

import re

from django import template


register = template.Library()

_PLUGINFILE_RE = re.compile(r'@@PLUGINFILE@@/([^"\'>\s]+)')


@register.filter
def pluginfile_names(text: str) -> list[str]:
    """Return list of filenames referenced as @@PLUGINFILE@@/filename in text."""
    return _PLUGINFILE_RE.findall(text or "")
