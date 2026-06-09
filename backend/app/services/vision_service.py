import base64
import json
from typing import Any, Dict, List

from openai import AsyncOpenAI
from app.core.config import settings
from app.observability.langfuse_client import get_langfuse, start_ai_trace, end_ai_generation


langfuse = get_langfuse()


class FoodVisionService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key or None)

    def _parse_json(self, raw: str, fallback_key: str) -> Dict[str, Any]:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        return {
            fallback_key: [],
            "raw": raw,
        }

    async def analyze_food_image(self, image_path: str) -> Dict[str, Any]:
        """Identify food items in an image and normalize the response."""

        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()

        messages = [
            {
                "role": "system",
                "content": (
                    "You identify visible food items in an image. "
                    "Return JSON with keys: foods (array of {name, confidence}), summary (string)."
                ),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_data}"
                        },
                    },
                    {
                        "type": "text",
                        "text": "List all food items visible. Return JSON only.",
                    },
                ],
            },
        ]

        trace = start_ai_trace(
            "vision.food_image",
            input={"image_path": image_path, "messages": messages},
            metadata={"model": settings.openai_model},
        )

        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            end_ai_generation(
                trace,
                name="vision.food_image",
                model=settings.openai_model,
                input={"image_path": image_path, "messages": messages},
                output=None,
                metadata={"feature": "analyze_food_image"},
                level="ERROR",
                status_message=str(exc),
            )
            raise

        raw = response.choices[0].message.content or "{}"
        payload = self._parse_json(raw, "foods")
        foods = payload.get("foods", [])

        normalized_foods: List[Dict[str, Any]] = []
        for item in foods:
            if isinstance(item, dict):
                normalized_foods.append({
                    "name": item.get("name") or item.get("food") or item.get("item"),
                    "confidence": item.get("confidence"),
                })
            else:
                normalized_foods.append({
                    "name": str(item),
                    "confidence": None,
                })

        normalized = {
            "foods": normalized_foods,
            "summary": payload.get("summary"),
            "raw": raw,
        }

        end_ai_generation(
            trace,
            name="vision.food_image",
            model=settings.openai_model,
            input={"image_path": image_path, "messages": messages},
            output=raw,
            usage=response.usage.model_dump() if response.usage else None,
            metadata={"feature": "analyze_food_image"},
        )

        return normalized

    async def suggest_recipes(self, available_foods: list) -> Dict[str, Any]:
        prompt = (
            "Suggest up to 5 simple recipes using these ingredients: "
            + ", ".join(available_foods)
            + ". Return JSON with key recipes (array of {name, ingredients, reason})."
        )

        trace = start_ai_trace(
            "vision.recipe_suggestions",
            input={"available_foods": available_foods, "prompt": prompt},
            metadata={"model": settings.openai_model},
        )

        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            end_ai_generation(
                trace,
                name="vision.recipe_suggestions",
                model=settings.openai_model,
                input={"available_foods": available_foods, "prompt": prompt},
                output=None,
                metadata={"feature": "suggest_recipes"},
                level="ERROR",
                status_message=str(exc),
            )
            raise

        raw = response.choices[0].message.content or "{}"
        end_ai_generation(
            trace,
            name="vision.recipe_suggestions",
            model=settings.openai_model,
            input={"available_foods": available_foods, "prompt": prompt},
            output=raw,
            usage=response.usage.model_dump() if response.usage else None,
            metadata={"feature": "suggest_recipes"},
        )
        payload = self._parse_json(raw, "recipes")
        recipes = payload.get("recipes", [])

        normalized_recipes: List[Dict[str, Any]] = []
        for item in recipes:
            if isinstance(item, dict):
                normalized_recipes.append({
                    "name": item.get("name"),
                    "ingredients": item.get("ingredients", []),
                    "reason": item.get("reason"),
                })
            else:
                normalized_recipes.append({
                    "name": str(item),
                    "ingredients": [],
                    "reason": None,
                })

        return {
            "recipes": normalized_recipes,
            "raw": raw,
        }
