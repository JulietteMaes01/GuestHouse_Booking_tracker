"""Writing pages into docs/."""
import os

import pytest

import config
import pages

TIMESTAMP = r"Mis à jour le [^<]*"


@pytest.fixture(autouse=True)
def docs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DOCS_DIR", str(tmp_path))
    return tmp_path


def test_page_kept_when_only_the_timestamp_changed(docs_dir):
    pages.write("a.html", "<p>Mis à jour le 01/10/2026 10:00</p><p>12 €</p>", TIMESTAMP)
    pages.write("a.html", "<p>Mis à jour le 01/10/2026 10:05</p><p>12 €</p>", TIMESTAMP)
    assert "10:00" in (docs_dir / "a.html").read_text(encoding="utf-8")


def test_page_rewritten_when_content_changed(docs_dir):
    pages.write("a.html", "<p>Mis à jour le 01/10/2026 10:00</p><p>12 €</p>", TIMESTAMP)
    pages.write("a.html", "<p>Mis à jour le 01/10/2026 10:05</p><p>13 €</p>", TIMESTAMP)
    assert "13 €" in (docs_dir / "a.html").read_text(encoding="utf-8")
