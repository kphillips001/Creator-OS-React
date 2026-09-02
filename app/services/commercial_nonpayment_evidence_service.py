"""Current and accumulated commercial nonpayment semantics."""
from __future__ import annotations

import re


class CommercialNonpaymentEvidenceService:
    """Classify customer wording without authorizing commerce or nurture."""

    REJECTION_PATTERN = (
        r"(^|\W)(no thanks|not interested|stop (trying to )?sell|leave me alone|"
        r"no more offers|not (buying|paying|spending)( right now| now| today)?|"
        r"don['’]?t feel like paying|not spending anything|"
        r"maybe later.{0,24}not paying)(\W|$)"
    )
    BROWSING_PATTERN = (
        r"(^|\W)((just|only) browsing|only here to look|just here to look|"
        r"just want to (see|look at) what['’]?s available|"
        r"only want to (see|look at) what['’]?s available)(\W|$)"
    )
    _rejection = re.compile(REJECTION_PATTERN, re.I)
    _browsing = re.compile(BROWSING_PATTERN, re.I)

    @classmethod
    def classify(cls, message: str) -> dict:
        text = str(message or "").strip()
        explicit_nonpayment = bool(cls._rejection.search(text))
        browsing_only = bool(cls._browsing.search(text))
        return {
            "explicitNonpaymentDetected": explicit_nonpayment,
            "browsingOnlyDetected": browsing_only,
            "commercialRejectionDetected": explicit_nonpayment,
        }
