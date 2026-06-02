"""Parse a Moodle PostgreSQL dump (binary PG17 or text SQL) into Python dicts."""

import re
import subprocess
import tempfile
from pathlib import Path


COPY_HEADER = re.compile(
    r'^COPY\s+"public"\."(\w+)"\s+\(([^)]+)\)\s+FROM\s+stdin;', re.MULTILINE
)


def _is_binary_dump(path: str) -> bool:
    with open(path, "rb") as f:
        return f.read(5) == b"PGDMP"


def _find_pg_restore() -> str:
    """Return path to pg_restore, checking common locations."""
    candidates = [
        "/usr/bin/pg_restore",
        "/usr/lib/postgresql/17/bin/pg_restore",
        "/usr/lib/postgresql/16/bin/pg_restore",
        "/usr/lib/postgresql/15/bin/pg_restore",
        "/usr/lib/postgresql/14/bin/pg_restore",
        "/usr/lib/postgresql/13/bin/pg_restore",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    # Fallback: rely on PATH
    return "pg_restore"


def _convert_binary_to_text(binary_path: str) -> str:
    """Convert a binary Moodle dump to text SQL using pg_restore."""
    pg_restore = _find_pg_restore()
    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp:
        tmp_path = tmp.name
    subprocess.run(
        [pg_restore, "-f", tmp_path, binary_path],
        check=True,
        capture_output=True,
    )
    return tmp_path


def _parse_text_sql(sql_text: str) -> dict[str, list[dict[str, str | None]]]:
    """Extract COPY blocks from SQL text into {table: [row_dict, ...]}."""
    tables: dict[str, list[dict[str, str | None]]] = {}
    lines = sql_text.splitlines()
    i = 0
    while i < len(lines):
        match = COPY_HEADER.match(lines[i])
        if match:
            table_name = match.group(1)
            col_names = [c.strip().strip('"') for c in match.group(2).split(",")]
            rows = []
            i += 1
            while i < len(lines) and lines[i] != "\\.":
                fields = lines[i].split("\t")
                row = {
                    col: (None if val == "\\N" else val)
                    for col, val in zip(col_names, fields)
                }
                rows.append(row)
                i += 1
            tables[table_name] = rows
        i += 1
    return tables


def parse_sql_dump(path: str) -> dict[str, list[dict[str, str | None]]]:
    """Parse a Moodle dump file (binary or text) and return table data."""
    if _is_binary_dump(path):
        text_path = _convert_binary_to_text(path)
        sql_text = Path(text_path).read_text(encoding="utf-8", errors="replace")
    else:
        sql_text = Path(path).read_text(encoding="utf-8", errors="replace")
    return _parse_text_sql(sql_text)


def build_context_to_course(
    data: dict[str, list[dict[str, str | None]]],
) -> dict[int, int]:
    """Return {context_id: course_moodle_id} for quiz module contexts."""
    # module_id → course_moodle_id
    module_to_course: dict[int, int] = {
        int(row["id"]): int(row["course"])  # type: ignore[arg-type]
        for row in data.get("m_course_modules", [])
        if row.get("id") and row.get("course")
    }
    # context_id → course_moodle_id (contextlevel=70 = course module)
    context_to_course: dict[int, int] = {}
    for row in data.get("m_context", []):
        if row.get("contextlevel") == "70" and row.get("instanceid"):
            module_id = int(row["instanceid"])  # type: ignore[arg-type]
            if module_id in module_to_course:
                context_to_course[int(row["id"])] = module_to_course[module_id]  # type: ignore[arg-type]
    return context_to_course
