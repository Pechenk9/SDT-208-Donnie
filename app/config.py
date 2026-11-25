
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    echo=False,
    # Neon suspends an idle database and drops its connections; on Vercel a
    # warm function would then reuse a dead connection and answer 500.
    # pre_ping checks a connection before use, recycle retires old ones.
    pool_pre_ping=True,
    pool_recycle=300,
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


def get_session():
    with SessionLocal() as session:
        yield session
