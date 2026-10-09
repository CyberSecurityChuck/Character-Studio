from pydantic import BaseModel, ConfigDict, Field, field_validator


class PreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    studio_name: str = Field(min_length=1, max_length=60)
    revision: int = Field(ge=1)

    @field_validator("studio_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Use a studio name with visible text and no control characters.")
        return value


class PreferencesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    studio_name: str
    revision: int
