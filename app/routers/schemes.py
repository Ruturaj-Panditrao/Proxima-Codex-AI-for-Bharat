from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

# Import from your app package
from app.database import get_db
from app import models, schemas

router = APIRouter(
    prefix="/api/schemes",
    tags=["Schemes"]
)

@router.get("/", response_model=List[schemas.SchemeResponse])
def get_schemes(
    skip: int = Query(0, description="Pagination: number of records to skip"),
    limit: int = Query(50, description="Pagination: maximum records to return"),
    state: Optional[str] = Query(None, description="Filter by state name (e.g., Assam)"),
    search: Optional[str] = Query(None, description="Search in scheme name"),
    db: Session = Depends(get_db)
):
    """
    Fetch a list of schemes. Supports pagination, state filtering, and basic text search.
    """
    query = db.query(models.Scheme)
    
    # Simple text search on the scheme name
    if search:
        query = query.filter(models.Scheme.schemeName.ilike(f"%{search}%"))
        
    # Filter by state using PostgreSQL array 'any'
    if state:
        query = query.filter(models.Scheme.beneficiaryState.any(state))
        
    schemes = query.offset(skip).limit(limit).all()
    return schemes

@router.get("/{slug}", response_model=schemas.SchemeResponse)
def get_scheme_by_slug(slug: str, db: Session = Depends(get_db)):
    """
    Fetch all deep details for a specific scheme using its unique slug.
    """
    scheme = db.query(models.Scheme).filter(models.Scheme.slug == slug).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return scheme