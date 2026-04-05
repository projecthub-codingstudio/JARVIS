"""Session query learning — capture, detect, and reuse refinement patterns."""
from pathlib import Path


def schema_sql_path() -> str:
    return str(Path(__file__).parent / "schema.sql")
