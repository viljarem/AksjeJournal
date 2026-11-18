"""Journal-lagring mot en database med og uten bildekolonnen."""

import pytest

from core import db


class _Query:
    def __init__(self, columns, fail_on_image):
        self.columns = columns
        self.fail = fail_on_image and "image_path" in columns

    def eq(self, *_):
        return self

    def ilike(self, *_):
        return self

    def order(self, *_, **__):
        return self

    def limit(self, *_):
        return self

    def execute(self):
        if self.fail:
            raise Exception('{"code":"42703","message":"column journal_entries.image_path does not exist"}')
        row = {"id": 1, "ticker": "X.OL", "body": "hei", "created_at": "2026-01-01T00:00:00Z"}
        if "image_path" in self.columns:
            row["image_path"] = "journal/X.OL/a.png"
        return type("R", (), {"data": [row], "count": 1})()


class _Table:
    def __init__(self, fail_on_image):
        self.fail = fail_on_image

    def select(self, columns, **_):
        return _Query(columns, self.fail)

    def insert(self, row):
        table = self

        class _Ins:
            def execute(self):
                if table.fail and "image_path" in row:
                    raise Exception('{"code":"42703","message":"column journal_entries.image_path does not exist"}')
                return type("R", (), {"data": [dict(row, id=1)]})()

        return _Ins()


def test_list_journal_with_image_column(monkeypatch):
    monkeypatch.setattr(db, "_table", lambda name: _Table(fail_on_image=False))
    rows, total = db.list_journal()
    assert total == 1 and rows[0]["image_path"] == "journal/X.OL/a.png"


def test_list_journal_falls_back_without_image_column(monkeypatch):
    monkeypatch.setattr(db, "_table", lambda name: _Table(fail_on_image=True))
    rows, total = db.list_journal(ticker="X.OL", search="he")
    assert total == 1 and "image_path" not in rows[0]


def test_add_entry_with_image_explains_missing_column(monkeypatch):
    monkeypatch.setattr(db, "_table", lambda name: _Table(fail_on_image=True))
    assert db.add_journal_entry("X.OL", "uten bilde")["body"] == "uten bilde"
    with pytest.raises(RuntimeError, match="alter table public.journal_entries"):
        db.add_journal_entry("X.OL", "med bilde", "journal/X.OL/a.png")
