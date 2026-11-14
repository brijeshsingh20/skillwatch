"""Project-level guarantees from the brief: no placeholder code, pinned dependencies, complete docs and config."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE_DIRS = ["backend", "vision", "scripts", "frontend/src"]
PLACEHOLDER = re.compile(r"\bTODO\b|\bFIXME\b|implement here|NotImplementedError")


def source_files():
    for d in CODE_DIRS:
        for ext in ("*.py", "*.js", "*.jsx"):
            yield from (ROOT / d).rglob(ext)


def test_no_placeholder_code():
    hits = [f"{p.relative_to(ROOT)}:{i}" for p in source_files() for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
            if PLACEHOLDER.search(line)]
    assert hits == []


def test_every_python_file_parses():
    for p in source_files():
        if p.suffix == ".py":
            ast.parse(p.read_text(encoding="utf-8"), filename=str(p))


def test_requirements_are_pinned():
    for name in ("requirements.txt", "requirements-yolo.txt"):
        for line in (ROOT / name).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "-r")):
                assert "==" in line, f"{name}: '{line}' is not pinned"


def test_frontend_dependencies_are_pinned():
    import json

    pkg = json.loads((ROOT / "frontend/package.json").read_text())
    for section in ("dependencies", "devDependencies"):
        for name, version in pkg[section].items():
            assert re.fullmatch(r"\d+\.\d+\.\d+", version), f"{name}@{version} is not an exact version"


def test_env_example_covers_every_setting():
    tree = ast.parse((ROOT / "backend/app/core/config.py").read_text())
    settings = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Settings")
    fields = {n.target.id for n in settings.body if isinstance(n, ast.AnnAssign)} - {"jwt_algorithm", "model_config"}
    env = (ROOT / ".env.example").read_text()
    missing = [f for f in sorted(fields) if not re.search(rf"^{f.upper()}=", env, re.M)]
    assert missing == []


def test_required_docs_exist_and_are_substantial():
    for name in ("README.md", "docs/ARCHITECTURE.md", "docs/API.md", "docs/PRIVACY.md", "docs/ACCURACY.md", "docs/BANDWIDTH.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert len(text) > 800, f"{name} looks empty"


def test_privacy_note_states_what_is_and_is_not_identified():
    text = (ROOT / "docs/PRIVACY.md").read_text(encoding="utf-8").lower()
    for phrase in ("no face recognition", "tracking", "raw frames", "pixelat", "not legal advice"):
        assert phrase in text, f"PRIVACY.md should mention '{phrase}'"


def test_no_face_recognition_dependencies_anywhere():
    banned = re.compile(r"\b(face_recognition|deepface|insightface|dlib|facenet|mediapipe)\b")  # \b: 'stdlib' is fine
    for p in source_files():
        assert not banned.search(p.read_text(encoding="utf-8").lower()), f"{p.relative_to(ROOT)} references a face library"
    reqs = " ".join((ROOT / n).read_text().lower() for n in ("requirements.txt", "requirements-yolo.txt"))
    assert not banned.search(reqs)
