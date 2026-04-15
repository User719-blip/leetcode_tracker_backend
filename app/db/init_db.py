from app.db.base import Base
from app.db.session import engine
from app.models import Snapshot, User


def init_db() -> None:
    # Importing models above ensures metadata contains all tables.
    _ = (User, Snapshot)
    Base.metadata.create_all(bind=engine)
