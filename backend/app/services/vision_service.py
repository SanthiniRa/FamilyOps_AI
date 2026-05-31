import base64
from openai import AsyncOpenAI
from app.db.models import Recipe

class FoodVisionService:
    def __init__(self):
        self.client = AsyncOpenAI()
    
    async def analyze_food_image(self, image_path: str) -> dict:
        """Identify food items in image"""
        with open(image_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode()
        
        response = await self.client.chat.completions.create(
            model="gpt-4-vision",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}},
                        {"type": "text", "text": "List all food items visible. Return JSON with food names and confidence scores."}
                    ]
                }
            ]
        )
        return response.choices[0].message.content
    
    async def suggest_recipes(self, available_foods: list) -> list:
        """Suggest recipes based on available food"""
        prompt = f"Suggest 5 recipes using these ingredients: {', '.join(available_foods)}"
        # Query recipes from DB or call LLM
