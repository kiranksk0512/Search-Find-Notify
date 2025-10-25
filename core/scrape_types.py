from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, TYPE_CHECKING

# Only import BaseJob for static type checking; avoid runtime deps/cycles
if TYPE_CHECKING:
    from models.base_job import BaseJob
else:
    BaseJob = Any  # runtime placeholder only

@dataclass
class ScrapeResult:
    # Use a forward string so runtime doesn’t need the symbol
    jobs: List['BaseJob']
    scrape_id: str
    anomalous_zero: bool = False

    should_persist: bool = True
    decision_reason: str = "ok"

    stats: Dict[str, Any] = field(default_factory=dict)
    meta:  Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        # keep job objects as-is
        return {
            "jobs": self.jobs,
            "scrape_id": self.scrape_id,
            "anomalous_zero": self.anomalous_zero,
            "should_persist": self.should_persist,
            "decision_reason": self.decision_reason,
            "stats": self.stats,
            "meta": self.meta,
        }
