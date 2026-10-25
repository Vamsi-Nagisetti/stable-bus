from sqlalchemy import text
from core.database import engine

with engine.connect() as connection:
    result = connection.execute(text("SELECT current_database()"))
    print(result.scalar())