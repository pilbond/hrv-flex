from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_DIR = ROOT / "analysis"
ALLOWED_ANALYSIS_FILES = {
    "efficiency_context_audit.py",
}


def test_exploratory_files_do_not_live_in_analysis_root() -> None:
    forbidden_prefixes = (
        "audit_",
        "experiment_",
        "exploratory_",
        "m3_",
        "research_",
    )
    forbidden_suffixes = (
        "_audit.py",
        "_audit.json",
        "_results.json",
    )

    misplaced = sorted(
        path.name
        for path in ANALYSIS_DIR.iterdir()
        if path.is_file()
        and path.name not in ALLOWED_ANALYSIS_FILES
        and (
            path.name.lower().startswith(forbidden_prefixes)
            or path.name.lower().endswith(forbidden_suffixes)
        )
    )

    assert not misplaced, (
        "Archivos exploratorios en analysis/. Moverlos a research/: "
        + ", ".join(misplaced)
    )
