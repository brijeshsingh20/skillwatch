"""Serve the Markdown documents shown on the Accuracy and Privacy pages."""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from backend.app.api.deps import get_current_user
from backend.app.models import User

router = APIRouter(prefix="/api/reports", tags=["reports"])
DOCS_DIR = Path(__file__).resolve().parents[3] / "docs"
FILES = {"accuracy": "ACCURACY.md", "privacy": "PRIVACY.md"}  # fixed allow-list: no user-chosen paths


@router.get("/{name}")
def get_report(name: str, _: User = Depends(get_current_user)) -> dict[str, str]:
    filename = FILES.get(name)
    if filename is None:
        raise HTTPException(status_code=404, detail="Unknown report")
    path = DOCS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Report not generated yet")
    return {"name": name, "markdown": path.read_text(encoding="utf-8")}
