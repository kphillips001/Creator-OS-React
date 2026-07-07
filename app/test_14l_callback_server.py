import json
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


SESSION_FILE = Path("data/config/fanvue_oauth_session.json")


def load_session():
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text())
    return {}


def save_session(data: dict):
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(data, indent=2))


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        query = parse_qs(parsed_url.query)

        code = query.get("code", [None])[0]
        state = query.get("state", [None])[0]

        print("\n=== FANVUE CALLBACK RECEIVED ===")
        print("Path:", parsed_url.path)
        print("Code received:", bool(code))
        print("State received:", bool(state))

        if code:
            session = load_session()
            session["code"] = code
            session["callback_state"] = state
            save_session(session)

            print("[FANVUE OAUTH SESSION SAVED]")
            print("Saved to:", SESSION_FILE)

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        self.wfile.write(b"<h1>Fanvue OAuth callback received.</h1>")
        self.wfile.write(b"<p>You can return to VS Code now.</p>")


def run_server():
    print("\n=== FANVUE CALLBACK SERVER RUNNING ===")
    print("Listening on: http://localhost:8000/callback")
    print("Leave this terminal running while you approve the Fanvue app.\n")

    server = HTTPServer(("localhost", 8000), OAuthCallbackHandler)
    server.serve_forever()


if __name__ == "__main__":
    run_server()