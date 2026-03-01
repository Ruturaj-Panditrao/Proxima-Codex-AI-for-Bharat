import os
import json
import time
import boto3
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Scheme

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

bedrock = boto3.client('bedrock-runtime', region_name='ap-south-1')

def get_embedding(text: str):
    """Call AWS Titan V2 to get a 1024-dimension vector."""
    try:
        # Titan V2 requires the dimension size in the request body
        body = json.dumps({
            "inputText": text,
            "dimensions": 1024,
            "normalize": True
        })
        
        response = bedrock.invoke_model(
            body=body,
            modelId='amazon.titan-embed-text-v2:0', # <-- The new V2 Model ID
            accept='application/json',
            contentType='application/json'
        )
        return json.loads(response.get('body').read())['embedding']
    except Exception as e:
        print(f"Bedrock Error: {e}")
        return None
    
def update_db_with_rich_vectors():
    db = SessionLocal()
    # Fetch schemes that haven't been vectorized yet
    schemes = db.query(Scheme).filter(Scheme.embedding == None).all()
    
    print(f"Found {len(schemes)} schemes needing AI vectors...")
    
    for i, scheme in enumerate(schemes):
        # 1. Grab base metadata
        states = ", ".join(scheme.beneficiaryState) if scheme.beneficiaryState else "Pan-India"
        tags_str = ", ".join(scheme.tags) if scheme.tags else ""
        
        # 2. Extract the deep JSON payload safely
        deep = scheme.deep_details or {}
        details_en = deep.get("details", {}).get("en", {})
        content = details_en.get("schemeContent", {})
        eligibility = details_en.get("eligibilityCriteria", {})
        processes = details_en.get("applicationProcess", [])
        faqs = deep.get("faqs", [])

        # 3. Pull out the Markdown (_md) fields
        detailed_desc = content.get("detailedDescription_md", "")
        benefits = content.get("benefits_md", "")
        exclusions = content.get("exclusions_md", "")
        eligibility_md = eligibility.get("eligibilityDescription_md", "")

        # 4. Extract Application Process
        process_text = ""
        for p in processes:
            process_text += p.get("process_md", "") + "\n"

        # 5. Extract FAQs (Massive context boost for the AI)
        faq_text = ""
        for f in faqs:
            q = f.get("question", "")
            a = f.get("answer_md", "")
            faq_text += f"Q: {q}\nA: {a}\n"

        # 6. Build the Ultimate Master Context String
        raw_search_text = f"""
        Scheme Name: {scheme.schemeName}
        State Availability: {states}
        Keywords: {tags_str}
        
        Description: 
        {detailed_desc or scheme.briefDescription}
        
        Eligibility Criteria:
        {eligibility_md}
        
        Benefits:
        {benefits}
        
        Exclusions:
        {exclusions}
        
        Application Process:
        {process_text}
        
        FAQs:
        {faq_text}
        """
        
        # 7. Clean up the text (remove HTML leftovers and weird spaces)
        clean_search_text = raw_search_text.replace("<br>", "\n").replace("&amp;quot;", '"').strip()
        
        # 8. Truncate to ~7500 characters to safely stay under Titan's token limit (approx 8000 tokens)
        # This prevents the script from crashing if a scheme has an abnormally long FAQ list
        final_search_text = clean_search_text[:7500]
        
        # 9. Generate the vector
        vector = get_embedding(final_search_text)
        
        if vector:
            scheme.embedding = vector
            if (i + 1) % 10 == 0:
                db.commit()
                print(f"   ✅ Vectorized {i + 1} / {len(schemes)}")
        else:
            print(f"   ⚠️ Failed to vectorize {scheme.slug}")
        
        # Prevent AWS rate limiting (Throttling Exception)
        time.sleep(0.3) 
        
    db.commit()
    db.close()
    print("🎉 Database is now a fully functioning, context-rich Vector Store!")

if __name__ == "__main__":
    update_db_with_rich_vectors()