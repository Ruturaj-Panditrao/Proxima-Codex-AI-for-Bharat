from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Dict, Any

# 1. The nested dictionary structure from the scraper
class DeepDetails(BaseModel):
    details: Optional[Dict[str, Any]] = {}
    faqs: Optional[List[Dict[str, Any]]] = []
    documents: Optional[List[Dict[str, Any]]] = []

# 2. The main schema
class SchemeBase(BaseModel):
    slug: str
    schemeName: str
    schemeShortTitle: Optional[str] = None
    level: Optional[str] = None
    nodalMinistryName: Optional[str] = None
    beneficiaryState: Optional[List[str]] = []
    schemeCategory: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    briefDescription: Optional[str] = None
    deep_details: Optional[DeepDetails] = None
    
    # FIX 4: Aligned with the database model (String, not List)
    schemeFor: Optional[str] = None 
    schemeCloseDate: Optional[str] = None
    
# 3. The schema used when returning data to the frontend
class SchemeResponse(SchemeBase):
    
    # This enables Pydantic to read the SQLAlchemy ORM models directly
    model_config = ConfigDict(from_attributes=True)