"""Database engine and sessions. SQLite on the PC; the same models run on PostgreSQL by changing DATABASE_URL."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str, data_dir: Path):
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        kw: dict = {}
        if url.startswith("sqlite"):
            kw["connect_args"] = {"check_same_thread": False, "timeout": 30}
        self.engine = create_engine(url, future=True, **kw)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _pragmas(conn, _):  # noqa: ANN001
                cur = conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.close()
        self._factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def create_all(self) -> None:
        from . import models  # noqa: F401  (registers the tables)
        Base.metadata.create_all(self.engine)
        self._add_missing_columns()
        self._data_fixes()

    def _add_missing_columns(self) -> None:
        """A database made by an earlier version lacks the columns added since. Adding a nullable column is safe, so do it here."""
        from sqlalchemy import inspect, text

        insp = inspect(self.engine)
        with self.engine.begin() as conn:
            for table in Base.metadata.sorted_tables:
                if not insp.has_table(table.name):
                    continue
                have = {c["name"] for c in insp.get_columns(table.name)}
                for col in table.columns:
                    if col.name not in have and not col.primary_key:
                        ddl = col.type.compile(self.engine.dialect)
                        conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))

    def _data_fixes(self) -> None:
        """One-time corrections of data written by earlier versions (SQLite keeps the step in PRAGMA user_version)."""
        from sqlalchemy import text

        if not str(self.engine.url).startswith("sqlite"):
            return
        with self.engine.begin() as conn:
            v = conn.execute(text("PRAGMA user_version")).scalar() or 0
            if v < 1:  # web research is on for every report from now on
                conn.execute(text("UPDATE reports SET use_web = 1 WHERE use_web IS NULL OR use_web = 0"))
                conn.execute(text("PRAGMA user_version = 1"))
            if v < 2:  # the sign-offs are gone: a finished or revised report is simply a draft
                conn.execute(text("UPDATE reports SET state = 'DECK_REVIEW', stage = 2 WHERE state IN ('FINAL', 'FEEDBACK')"))
                conn.execute(text("UPDATE reports SET stage = 2 WHERE stage = 3 AND state IN ('GENERATING', 'DECK_REVIEW')"))
                conn.execute(text("PRAGMA user_version = 2"))

    @contextmanager
    def session(self):
        s: Session = self._factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def dispose(self) -> None:
        self.engine.dispose()
