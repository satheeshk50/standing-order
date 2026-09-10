from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import BUSINESS_ACTIONS


class SupervisorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    base_instruction: str = Field(min_length=1)
    allowed_actions: list[str] = Field(default_factory=lambda: list(BUSINESS_ACTIONS))
    default_wake_seconds: int = Field(default=900, ge=5)
    max_run_age_seconds: int = Field(default=60 * 60 * 24 * 7, ge=60)
    wake_aggressiveness: str = "balanced"
    wake_guidance: str | None = None
    model: str = "gemini-3.5-flash"
    classifier_model: str = "gemini-3.5-flash-lite"
    effort: str = "medium"
    is_default: bool = False


class SupervisorUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    base_instruction: str | None = None
    allowed_actions: list[str] | None = None
    default_wake_seconds: int | None = None
    max_run_age_seconds: int | None = None
    wake_aggressiveness: str | None = None
    wake_guidance: str | None = None
    model: str | None = None
    classifier_model: str | None = None
    effort: str | None = None
    is_default: bool | None = None


class SupervisorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: str
    name: str
    description: str | None
    base_instruction: str
    allowed_actions: list[str]
    default_wake_seconds: int
    max_run_age_seconds: int
    wake_aggressiveness: str
    wake_guidance: str | None
    model: str
    classifier_model: str
    effort: str
    is_default: bool
    created_at: datetime
