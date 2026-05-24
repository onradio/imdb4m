from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
KG_DIR = DATA_DIR / "kg"
REPORTS_DIR = REPO_ROOT / "reports"
REPORTS_STATS = REPORTS_DIR / "stats"
REPORTS_VALIDATION = REPORTS_DIR / "validation"
EMBEDDINGS_OUTPUT = REPO_ROOT / "embeddings_output"
SCRIPTS_DIR = REPO_ROOT / "scripts"
PARSING_DIR = SCRIPTS_DIR / "parsing"
