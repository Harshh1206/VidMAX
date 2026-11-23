from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base


def create_db_engine(database_url: str, storage_dir: Path | None = None) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() == "sqlite":
        if url.database and url.database != ":memory:":
            database_path = Path(url.database)
            if not database_path.is_absolute() and storage_dir is not None:
                database_path = storage_dir / database_path
            database_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False, "timeout": 30},
            pool_pre_ping=True,
        )
    return create_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def check_db(engine: Engine) -> bool:
    with engine.connect() as connection:
        return connection.execute(text("SELECT 1")).scalar_one() == 1


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as session:
        yield session
