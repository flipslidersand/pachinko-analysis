"""PostgreSQL データベース接続管理"""
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# 環境変数読み込み
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/dev_db")

# エンジン作成
engine = create_engine(DATABASE_URL, echo=False)

# セッション作成
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """DB セッション取得"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """スキーマ初期化"""
    sql_file = os.path.join(
        os.path.dirname(__file__),
        "migrations",
        "001_init.sql"
    )

    with open(sql_file, "r", encoding="utf-8") as f:
        sql = f.read()

    with engine.connect() as conn:
        conn.execute(text(sql))
        conn.commit()
        print("✅ Database schema initialized")


if __name__ == "__main__":
    init_db()
