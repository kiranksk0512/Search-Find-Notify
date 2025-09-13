from dataclasses import dataclass
from typing import Dict, Any, Optional

@dataclass
class ScrapeSummary:
    company: str
    new: Dict[str, Any]
    deleted: Dict[str, Any]
    error: Optional[str] = None  # None if success; string if failed
