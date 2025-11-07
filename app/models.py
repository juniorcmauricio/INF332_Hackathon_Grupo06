from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class Recommendation(BaseModel):
    """
    Single recommendation item returned by the API.
    """
    title: str
    source: str = "TMDB"
    score: float = Field(ge=0.0, le=1.0, default=0.7)
    providers: List[str] | None = None  # streaming platforms (optional)

class RecommendationList(BaseModel):
    """
    Envelope holding a list of recommendations.
    """
    items: List[Recommendation]

    model_config: Dict[str, Any] = {
        "json_schema_extra": {
            "examples": [{
                "items": [
                    {"title": "Amélie", "source": "TMDB", "score": 0.82, "providers": ["Netflix", "Prime Video"]},
                    {"title": "La La Land", "source": "TMDB", "score": 0.87, "providers": ["Disney Plus"]}
                ]
            }]
        }
    }
