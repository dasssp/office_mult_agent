from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.workflows import EvidenceRef


class ArtifactReference(BaseModel):
    artifact_id: str
    kind: str
    uri: str | None = None


class ProposedAction(BaseModel):
    action: str
    target_id: str | None = None
    requires_approval: bool = False


class SubAgentOutcome(BaseModel):
    task_id: str = ""
    status: Literal["completed", "partial", "failed", "blocked"]
    summary: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    artifact_refs: list[ArtifactReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    proposed_actions: list[ProposedAction] = Field(default_factory=list)


class MainAgentResponse(BaseModel):
    status: Literal["completed", "partial", "failed", "awaiting_approval"]
    summary: str
    completed_tasks: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    artifact_refs: list[ArtifactReference] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
