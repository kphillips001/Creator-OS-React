import json
from pathlib import Path

from app.services.fanvue_oauth_service import FanvueOAuthService


SESSION_FILE = Path("data/config/fanvue_oauth_session.json")


def run_test():
    print("\n=== 14L STEP 2: TOKEN EXCHANGE TEST ===\n")

    if not SESSION_FILE.exists():
        print("[ERROR] No OAuth session file found.")
        print("Run OAuth URL + callback flow first.")
        return

    session = json.loads(SESSION_FILE.read_text())

    code = session.get("code")
    code_verifier = session.get("code_verifier")

    print("Loaded code:", bool(code))
    print("Loaded code_verifier:", bool(code_verifier))

    service = FanvueOAuthService()
    result = service.exchange_code_for_tokens(code, code_verifier)

    print("\nTOKEN EXCHANGE RESULT:")
    print(result)


if __name__ == "__main__":
    run_test()