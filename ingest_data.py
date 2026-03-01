import json
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# FIX 1: Removed the dots for absolute imports
from app.database import Base
from app.models import Scheme

load_dotenv()

# Connect to AWS RDS
engine = create_engine(os.getenv("DATABASE_URL"))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def ingest_data():
    print("1️⃣ Connecting to AWS RDS and creating tables...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("2️⃣ Loading ultimate_schemes_database.json...")
    try:
        with open('ultimate_schemes_database.json', 'r', encoding='utf-8') as f:
            schemes = json.load(f)
    except FileNotFoundError:
        print("Error: JSON file not found.")
        return

    print(f"3️⃣ Pushing {len(schemes)} schemes to the cloud...")
    
    added_count = 0
    for i, item in enumerate(schemes):
        slug = item.get("slug")
        
        # Skip if already in DB
        if db.query(Scheme).filter(Scheme.slug == slug).first():
            continue

        db_scheme = Scheme(
            slug=slug,
            schemeName=item.get("schemeName", ""),
            schemeShortTitle=item.get("schemeShortTitle"),
            level=item.get("level"),
            nodalMinistryName=item.get("nodalMinistryName"),
            beneficiaryState=item.get("beneficiaryState", []),
            schemeCategory=item.get("schemeCategory", []),
            tags=item.get("tags", []),
            # FIX 2: Corrected the JSON key names
            schemeCloseDate=item.get("schemeCloseDate"), 
            schemeFor=item.get("schemeFor"), 
            briefDescription=item.get("briefDescription", ""),
            deep_details=item.get("deep_details", {})
        )
        
        db.add(db_scheme)
        added_count += 1
        
        # Batch commit every 100 rows to make the network upload faster
        if added_count % 100 == 0:
            db.commit()
            print(f"   💾 Uploaded {added_count} schemes so far...")

    db.commit()
    db.close()
    print(f"🎉 Success! {added_count} new schemes securely stored in AWS RDS.")

if __name__ == "__main__":
    ingest_data()