from sqlalchemy import text
from sqlmodel import SQLModel

from app.core.db import engine
import app.models #모델 등록용


ENUM_SQL = """
DO $$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'auth_provider') THEN
  CREATE TYPE auth_provider AS ENUM ('google','github');
END IF;

IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'summary_style') THEN
  CREATE TYPE summary_style AS ENUM ('default','short','detailed');
END IF;

IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'site') THEN
  CREATE TYPE site AS ENUM ('arxiv','github');
END IF;

IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'event_type') THEN
  CREATE TYPE event_type AS ENUM ('view','like','unlike','save','unsave','search');
END IF;

IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'tag_type') THEN
  CREATE TYPE tag_type AS ENUM ('cs.AI','cs.LG','cs.CV','cs.CL');
END IF;
END $$;
"""


def main() -> None:
    with engine.begin() as conn:
        conn.execute(text(ENUM_SQL))

    SQLModel.metadata.create_all(engine)
    print("✅ ENUM types + tables created (if not existed).")


if __name__ == "__main__":
    main()