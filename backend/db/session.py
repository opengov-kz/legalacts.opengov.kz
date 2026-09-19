from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base


def create_engine_and_session_factory(database_url):
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    return engine, session_factory
