"""Build a source-only archive for household users, without credentials, databases, or build outputs."""

import argparse
import os
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

SOURCE_DIRS = {"mealie", "frontend", "dev", "tests", "docker", "docs"}
EXCLUDED_DIRS = {
    ".git",
    ".github",
    ".venv",
    "node_modules",
    ".nuxt",
    ".output",
    "dist",
    ".temp",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "coverage",
    "htmlcov",
    "test-results",
}
ROOT_FILES = {
    "README.md",
    "LICENSE",
    "AGENTS.md",
    "HOUSEHOLD_GROCERIES.md",
    "pyproject.toml",
    "uv.lock",
    "Taskfile.yml",
    ".dockerignore",
    ".gitignore",
    ".gitattributes",
    ".pre-commit-config.yaml",
    ".pylintrc",
    "crowdin.yml",
    "compose.household.yml",
}


def source_files(root: Path) -> list[Path]:
    result: list[Path] = []
    for directory, children, filenames in os.walk(root):
        current = Path(directory)
        relative_dir = current.relative_to(root)
        children[:] = [
            name
            for name in children
            if name not in EXCLUDED_DIRS and not (relative_dir == Path("dev") and name == "data")
        ]
        if current == root:
            children[:] = [name for name in children if name in SOURCE_DIRS]
        for name in filenames:
            path = current / name
            relative = path.relative_to(root)
            if path.is_symlink() or name.startswith(".env") or name in {".dev.env", ".secret", "household-source.zip"}:
                continue
            if path.suffix in {".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".log"}:
                continue
            if relative.parts[0] in SOURCE_DIRS or relative.as_posix() in ROOT_FILES:
                result.append(path)
    return sorted(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for path in source_files(root):
            if path.resolve() != args.output.resolve():
                archive.write(path, path.relative_to(root).as_posix())


if __name__ == "__main__":
    main()
