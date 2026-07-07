import hmac
import hashlib

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
            received_signature = parsed["signature"]

            raw_body_text = raw_body.decode("utf-8")

            signed_payload = (
                f"{timestamp}.{raw_body_text}"
            )

            expected_signature = hmac.new(
                FANVUE_WEBHOOK_SIGNING_SECRET.encode(
                    "utf-8"
                ),
                signed_payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            is_valid = hmac.compare_digest(
                expected_signature,
                received_signature,
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

        parsed = {}

        for piece in pieces:
            key, value = piece.split("=", 1)

            parsed[key.strip()] = value.strip()

        return {
            "timestamp": parsed["t"],
            "signature": parsed["v0"],
        }