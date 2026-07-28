import hmac
import hashlib
import time
from collections.abc import Callable

from app.config import FANVUE_WEBHOOK_SIGNING_SECRET


class WebhookSignatureService:
    """
    Verifies Fanvue webhook signatures.

    REAL Fanvue format:
    x-fanvue-signature: t=<timestamp>,v0=<signature>

    Signed payload:
    {timestamp}.{raw_request_body}
    """

    SIGNATURE_HEADER = "x-fanvue-signature"
    DEFAULT_TOLERANCE_SECONDS = 300

    def __init__(
        self,
        signing_secret: str | None = None,
        *,
        tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._signing_secret = (
            FANVUE_WEBHOOK_SIGNING_SECRET
            if signing_secret is None
            else signing_secret
        )
        self._tolerance_seconds = tolerance_seconds
        self._clock = clock

    def verify_signature(
        self,
        raw_body: bytes,
        signature_header: str | None,
    ) -> bool:

        if not signature_header:
            print("\n[WEBHOOK SECURITY]")
            print("Missing Fanvue signature header")
            return False

        try:
            parsed = self._parse_signature_header(
                signature_header
            )

            timestamp = parsed["timestamp"]
            received_signatures = parsed["signatures"]

            timestamp_seconds = int(timestamp)
            if abs(self._clock() - timestamp_seconds) > self._tolerance_seconds:
                return False

            if not self._signing_secret:
                return False

            signed_payload = f"{timestamp}.".encode("utf-8") + raw_body

            expected_signature = hmac.new(
                self._signing_secret.encode("utf-8"),
                signed_payload,
                hashlib.sha256,
            ).hexdigest()

            is_valid = any(
                hmac.compare_digest(expected_signature, received_signature)
                for received_signature in received_signatures
            )

            print("\n[SIGNATURE VERIFICATION]")
            print(f"timestamp={timestamp}")
            print(f"valid={is_valid}")

            return is_valid

        except Exception as e:
            print("\n[SIGNATURE VERIFICATION ERROR]")
            print(str(e))
            return False

    def _parse_signature_header(
        self,
        signature_header: str,
    ) -> dict:

        pieces = signature_header.split(",")

        timestamp = None
        signatures = []

        for piece in pieces:
            key, separator, value = piece.partition("=")
            if not separator:
                continue

            key = key.strip()
            value = value.strip()
            if key == "t":
                timestamp = value
            elif key == "v0":
                signatures.append(value)

        if not timestamp or not signatures:
            raise ValueError("Fanvue signature header is missing t or v0")

        return {
            "timestamp": timestamp,
            "signatures": signatures,
        }
