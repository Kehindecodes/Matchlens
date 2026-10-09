"""The shared reference type for the polymorphic relationships.

`Moment.subject` (Team | Player), `Claim.evidence_ids` (Event | SignalReading | Run) and
`ProducerAction.target_id` (Moment | Rendition | Lens) all point at more than one kind of entity.
A bare ID string would leave the verifier unable to tell which lookup to run, so they carry a
`Ref` instead: one type, one dispatch point.
"""

from pydantic import BaseModel, ConfigDict

from matchlens.models.enums import RefKind


class Ref(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: RefKind
    id: str
