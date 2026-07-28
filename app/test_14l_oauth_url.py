import json
from pathlib import Path

from app.services.fanvue_oauth_service import FanvueOAuthService


SESSION_FILE = Path("data/config/fanvue_oauth_session.json")


def save_session(data: dict):
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(data, indent=2))


def run_test():
    print("\n=== 14L STEP 1A: FANVUE OAUTH URL TEST ===\n")

    service = FanvueOAuthService()
    result = service.generate_authorization_url()

    save_session({
        "code_verifier": result["code_verifier"],
        "state": result["state"],
    })

    print("\nAUTHORIZATION URL:")
    print("Authorization URL generated:", bool(result["authorization_url"]))

    print("\nSaved OAuth session to:")
    print(SESSION_FILE)


if __name__ == "__main__":
    run_test()
