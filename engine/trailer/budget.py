"""A run may not spend past what it quoted. Enforced, not remembered.

Episode one cost three films' worth of pictures (2026-09-02, Lars: "50% of
it is because you forget things and not do what we agreed"). Every one of
those overspends was a loop that nobody had told to stop: a redraw round
that never converged, a checker outage read as 146 bad pictures, a cache
serving old footage as new.

So a run now carries a budget. The stills stage counts every drawing it
asks for and refuses the one that would pass the cap. The shoot checks the
credit balance between takes and stops launching new ones past its cap.
The caps are quoted in the log before anything is spent, and hitting one
ends the run with the numbers, not with a bigger bill.
"""
from __future__ import annotations

import threading


class OverBudget(RuntimeError):
    """The run has reached its quoted spend. Stop; do not spend more."""


class Budget:
    def __init__(self):
        self.lock = threading.Lock()
        self.drawings = 0
        self.drawings_cap = None       # None = uncapped (never in the line)
        self.credits_start = None
        self.credits_cap = None        # Runway credits this run may spend

    def quote(self, drawings_cap: int, credits_cap: int = None,
              credits_start: int = None):
        self.drawings = 0
        self.drawings_cap = int(drawings_cap)
        self.credits_cap = credits_cap
        self.credits_start = credits_start

    def spend_drawing(self, what: str = ""):
        with self.lock:
            if self.drawings_cap is not None and self.drawings >= self.drawings_cap:
                raise OverBudget(
                    f"the run has reached its cap of {self.drawings_cap} drawings"
                    + (f" (next would be {what})" if what else "")
                    + " — stopped so nothing more is spent; raise the cap on purpose "
                    "if the pictures are worth it")
            self.drawings += 1

    def check_credits(self, balance_now, what: str = ""):
        if self.credits_cap is None or self.credits_start is None:
            return
        # AN EMPTY READ IS NOT A SPEND (2026-09-02). A balance that comes
        # back as 0 or None is a failed request, not a bill of 41,000
        # credits — that false alarm stopped a shoot at its second take.
        # Unknown means unknown; the cap is judged only on a real number.
        try:
            balance_now = int(balance_now)
        except Exception:
            return
        if balance_now <= 0 or balance_now > self.credits_start:
            return
        spent = self.credits_start - balance_now
        if spent >= self.credits_cap:
            raise OverBudget(
                f"the shoot has spent {spent} credits against a cap of "
                f"{self.credits_cap}" + (f" ({what})" if what else "")
                + " — stopped so nothing more is spent")

    def report(self) -> str:
        cap = "uncapped" if self.drawings_cap is None else str(self.drawings_cap)
        return f"drawings {self.drawings} of {cap}"


BUDGET = Budget()
