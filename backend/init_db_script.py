from sqlmodel import SQLModel, text
from app.core.db import engine
# Import all models to ensure they are registered
from app.models.paper import Paper, PaperTag
from app.models.user import User, UserPaperLike, UserPaperScrap, UserPaperView
from app.models.event import Event
# Add other models if found (will check list_dir output)

def init_db():
    print("Creating Enum types...")
    with engine.connect() as conn:
        conn.begin()
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'site') THEN
                    CREATE TYPE site AS ENUM ('arxiv', 'github');
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'summary_style') THEN
                    CREATE TYPE summary_style AS ENUM ('plain', 'detailed', 'dc');
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'event_type') THEN
                    CREATE TYPE event_type AS ENUM ('view', 'like', 'unlike', 'save', 'unsave', 'search', 'create_user', 'login');
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'auth_provider') THEN
                    CREATE TYPE auth_provider AS ENUM ('google', 'github');
                END IF;
            END$$;
        """))
        conn.commit()
    
    print("Creating tables...")
    SQLModel.metadata.create_all(engine)
    print("Tables created successfully.")

if __name__ == "__main__":
    init_db()
