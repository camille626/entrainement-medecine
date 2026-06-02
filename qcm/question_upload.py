"""Utilities for uploading Moodle XML question files."""

from __future__ import annotations

import xml.etree.ElementTree as ET


# Allowed fraction values and their string keys (matching FRACTION_CHOICES in views.py)
_FRACTION_MAP: list[tuple[float, str]] = [
    (1.0, "1.0"),
    (0.5, "0.5"),
    (1 / 3, "0.333333"),
    (0.25, "0.25"),
    (0.0, "0.0"),
    (-1.0, "-1.0"),
]


def _snap_fraction(pct: float) -> tuple[float, str]:
    """Return (float, str) for the nearest allowed fraction from a Moodle percentage."""
    f = pct / 100.0
    nearest_val, nearest_str = min(_FRACTION_MAP, key=lambda item: abs(item[0] - f))
    return nearest_val, nearest_str


def parse_moodle_xml(content: bytes) -> list[dict]:
    """Parse a Moodle XML export and return a list of question dicts.

    Only multichoice questions are parsed; other types are silently ignored.
    Questions without text or with fewer than 2 answers are skipped.
    Raises ValueError for malformed XML.

    Moodle stores fractions as percentages (100, 33.33333, -100, 0).
    Each answer dict contains both ``fraction`` (float) and ``fraction_str``
    (string key matching FRACTION_CHOICES) for template pre-selection.
    """
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"XML invalide : {exc}") from exc

    questions = []
    for q_el in root.findall("question"):
        if q_el.get("type") != "multichoice":
            continue

        text = _get_cdata(q_el, "questiontext/text")
        feedback = _get_cdata(q_el, "generalfeedback/text")

        answers = []
        for ans_el in q_el.findall("answer"):
            try:
                frac_pct = float(ans_el.get("fraction", "0"))
            except ValueError:
                frac_pct = 0.0
            fraction, fraction_str = _snap_fraction(frac_pct)
            ans_text = _get_cdata(ans_el, "text")
            if ans_text:
                answers.append(
                    {
                        "text": ans_text,
                        "fraction": fraction,
                        "fraction_str": fraction_str,
                    }
                )

        # Tags from XML <tags><tag><text>...</text></tag>...</tags>
        xml_tags: list[str] = []
        tags_el = q_el.find("tags")
        if tags_el is not None:
            for tag_el in tags_el.findall("tag"):
                t = _get_cdata(tag_el, "text")
                if t:
                    xml_tags.append(t)

        if text and len(answers) >= 2:
            questions.append(
                {
                    "text": text,
                    "feedback": feedback,
                    "answers": answers,
                    "xml_tags": xml_tags,
                }
            )

    return questions


def _get_cdata(el: ET.Element, path: str) -> str:
    child = el.find(path)
    return (child.text or "").strip() if child is not None else ""
