import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# Your AWS RDS Connection String (Store this in your .env file)
# Format: postgresql://username:password@your-rds-endpoint.aws.com:5432/dbname
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to inject the DB session into your routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()