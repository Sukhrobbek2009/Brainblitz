from sqlalchemy import text

from app.db import get_engine
from app.models import Base

engine = get_engine()
Base.metadata.create_all(engine)
# create_all never alters existing tables, so add columns introduced later (safe to re-run)
if engine.dialect.name == "postgresql":
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE game_results ADD COLUMN IF NOT EXISTS questions JSONB"))
print("tables created")
