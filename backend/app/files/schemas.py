from uuid import UUID
from pydantic import BaseModel, ConfigDict


class FileReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: UUID
