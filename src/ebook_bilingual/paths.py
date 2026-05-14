from __future__ import annotations

from pathlib import Path
import shutil

_PREFERRED_CLEAN_STYLE_NAME = "eink-10.3.css"


def discover_style_css(cwd: Path) -> Path | None:
    """If ``cwd/styles`` exists, prefer ``eink-10.3.css``, else the first ``*.css`` sorted by filename."""
    styles_dir = cwd / "styles"
    if not styles_dir.is_dir():
        return None

    preferred = styles_dir / _PREFERRED_CLEAN_STYLE_NAME
    if preferred.is_file():
        return preferred

    candidates = sorted(styles_dir.glob("*.css"))
    return candidates[0] if candidates else None


def default_output_path(input_path: Path) -> Path:
    suffix = input_path.suffix or ".epub"
    return input_path.with_name(f"{input_path.stem}.bilingual{suffix}")


def prepare_run_paths(
    input_path: Path,
    output_path: Path | None,
    cache_path: Path | None,
    work_dir: Path | None,
) -> tuple[Path, Path, Path]:
    run_input_path = copy_into_work_dir(input_path, work_dir)
    run_output_path = output_path or default_output_path(run_input_path)
    run_cache_path = cache_path or run_output_path.with_suffix(run_output_path.suffix + ".translation-cache.json")
    return run_input_path, run_output_path, run_cache_path


def copy_into_work_dir(path: Path, work_dir: Path | None) -> Path:
    if work_dir is None:
        return path
    work_dir.mkdir(parents=True, exist_ok=True)
    run_path = work_dir / path.name
    if path.resolve() != run_path.resolve():
        shutil.copy2(path, run_path)
    return run_path
