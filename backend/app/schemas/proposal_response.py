import uuid
from typing import Literal
from pydantic import BaseModel, model_validator


class ProposalResponseCreate(BaseModel):
    participant_id: uuid.UUID
    proposal_id: uuid.UUID | None = None
    choice: Literal["picked", "declined", "maybe"] = "picked"
    comment: str | None = None

    @model_validator(mode="after")
    def validate_choice(self) -> "ProposalResponseCreate":
        if self.choice == "picked" and self.proposal_id is None:
            raise ValueError("proposal_id is required when choice is picked")
        if self.choice == "declined" and self.proposal_id is not None:
            raise ValueError("proposal_id must be null when choice is declined")
        return self


class RequestFinalize(BaseModel):
    proposal_id: uuid.UUID
