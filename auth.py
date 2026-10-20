# auth.py — Upstox OAuth2 authentication handler
import os
import json
import webbrowser
import requests
from datetime import datetime
from flask import Flask, request as flask_request
from config import (
    UPSTOX_API_KEY, UPSTOX_API_SECRET,
    UPSTOX_REDIRECT_URL, TOKEN_FILE
)

app = Flask(__name__)
_access_token = None


def get_login_url():
    return (
        f"https://api.upstox.com/v2/login/authorization/dialog"
        f"?response_type=code"
        f"&client_id={UPSTOX_API_KEY}"
        f"&redirect_uri={UPSTOX_REDIRECT_URL}"
    )


def exchange_code_for_token(auth_code):
    url = "https://api.upstox.com/v2/login/authorization/token"
    payload = {
        "code":          auth_code,
        "client_id":     UPSTOX_API_KEY,
        "client_secret": UPSTOX_API_SECRET,
        "redirect_uri":  UPSTOX_REDIRECT_URL,
        "grant_type":    "authorization_code",
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(url, data=payload, headers=headers)
    data = response.json()

    if "access_token" in data:
        save_token(data["access_token"])
        return data["access_token"]
    else:
        print(f"❌ Token exchange failed: {data}")
        return None


def save_token(token):
    os.makedirs("db", exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "access_token": token,
            "saved_at": datetime.now().isoformat()
        }, f)
    print(f"✅ Token saved to {TOKEN_FILE}")


def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r") as f:
        data = json.load(f)
    saved_at = datetime.fromisoformat(data["saved_at"])
    hours_old = (datetime.now() - saved_at).total_seconds() / 3600
    if hours_old > 23:
        print("⚠️  Token is older than 23 hours — need fresh login")
        return None
    return data["access_token"]


def get_access_token():
    """Main entry point — returns valid token or triggers login."""
    token = load_token()
    if token:
        print("✅ Token loaded from file")
        return token
    print("🔐 No valid token found — starting login flow...")
    return run_auth_flow()


def run_auth_flow():
    """Opens browser for login, catches redirect, returns token."""
    login_url = get_login_url()
    print(f"\n🌐 Opening Upstox login in browser...")
    webbrowser.open(login_url)

    # Start local Flask server to catch the redirect
    @app.route("/callback")
    def callback():
        global _access_token
        auth_code = flask_request.args.get("code")
        if not auth_code:
            return "❌ No auth code received", 400
        _access_token = exchange_code_for_token(auth_code)
        if _access_token:
            return "<h2>✅ Login successful! You can close this tab.</h2>"
        return "<h2>❌ Login failed. Check terminal.</h2>", 500

    print("⏳ Waiting for Upstox login... (complete it in the browser)")
    app.run(port=5000, debug=False, use_reloader=False)
    return _access_token


if __name__ == "__main__":
    token = get_access_token()
    if token:
        print(f"\n✅ Auth working! Token preview: {token[:20]}...")
    else:
        print("\n❌ Auth failed")