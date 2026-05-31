from fastapi import APIRouter, UploadFile, File, Depends
from app.db.database import get_db
from app.services.vision_service import FoodVisionService

router = APIRouter(prefix="/uploads", tags=["uploads"])

@router.post("/food-image")
async def upload_food_image(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """Upload food image to analyze ingredients"""
    import tempfile
    import os
    
    vision_service = FoodVisionService()
    
    # Save temp file
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        analysis = await vision_service.analyze_food_image(tmp_path)
        recipes = await vision_service.suggest_recipes(analysis['foods'])
        return {"food_items": analysis, "recipes": recipes}
    finally:
        os.unlink(tmp_path)
