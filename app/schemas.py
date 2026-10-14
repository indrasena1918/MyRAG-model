"""Request and response models for the travel assistant API."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    model: Literal["qwen2.5:3b", "llama3.2:latest"] | None = None
    conversation_id: str | None = None


class Citation(BaseModel):
    label: str
    source: str
    section: str | None = None
    page: int | None = None
    excerpt: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    conversation_id: str
    grounded: bool


class ItineraryRequest(BaseModel):
    starting_city: str = Field(min_length=2, max_length=100)
    destination: str = Field(min_length=2, max_length=100)
    start_date: date
    end_date: date
    travelers: int = Field(ge=1, le=30)
    budget_inr: int = Field(gt=0, le=100_000_000)
    interests: list[Literal["nature", "adventure", "history", "temples", "beaches", "food", "shopping"]] = Field(min_length=1)
    travel_preference: Literal["bus", "train", "car", "flight"]
    accommodation_preference: str = Field(min_length=2, max_length=200)
    pace: Literal["relaxed", "moderate", "packed"]
    requirements: str = Field(default="", max_length=1000)
    model: Literal["qwen2.5:3b", "llama3.2:latest"] | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date.")
        if (self.end_date - self.start_date).days > 30:
            raise ValueError("Trips longer than 31 days are not supported.")
        return self


class ItineraryDay(BaseModel):
    day: int
    date: date
    morning: str
    afternoon: str
    evening: str


class BudgetAllocation(BaseModel):
    transport: int
    accommodation: int
    food: int
    activities: int
    total: int
    note: str


class ItineraryResponse(BaseModel):
    destination: str
    days: list[ItineraryDay]
    transport_suggestion: str
    accommodation_suggestion: str
    travel_tips: list[str]
    budget: BudgetAllocation
    citations: list[Citation]
    limitations: list[str]


class TripCreate(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    destination: str = Field(min_length=1, max_length=100)
    itinerary: dict


class TripRecord(TripCreate):
    id: int
    created_at: str
