from __future__ import annotations

from the_show.state import count_unplanned_urgent_matters


class UrgentThrottle:
    """
    Counts unplanned urgent matters (monitor-triggered, cut-escalate-triggered).
    Planned human-approval scenes are always exempt.
    Critical severity always bypasses.
    """

    def __init__(self, db_path: str, show_id: str, max_per_show: int = 3) -> None:
        self.db_path = db_path
        self.show_id = show_id
        self.max_per_show = max_per_show

    def is_allowed(self, severity: str, trigger_type: str) -> bool:
        """Return True if this matter should proceed; False if throttled."""
        if severity == "critical":
            return True
        if trigger_type == "human-approval":
            return True  # planned scenes are exempt
        count = count_unplanned_urgent_matters(self.db_path, self.show_id)
        return count < self.max_per_show
