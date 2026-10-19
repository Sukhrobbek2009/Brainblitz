from app.db import get_engine
from app.models import Base

Base.metadata.create_all(get_engine())
print("tables created")
