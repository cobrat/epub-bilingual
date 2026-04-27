from __future__ import annotations

from pathlib import Path
import shutil


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
