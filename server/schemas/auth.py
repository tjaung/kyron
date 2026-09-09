from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class PracticeInfo(BaseModel):
    practice_id: UUID
    name: str
    slug: str


class ProviderInfo(BaseModel):
    provider_id: UUID
    first_name: str
    last_name: str
    username: str


class AuthSession(BaseModel):
    practice: PracticeInfo
    provider: ProviderInfo
