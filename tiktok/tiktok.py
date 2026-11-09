#!/usr/bin/env python3
"""TikTok Content Posting API helper (stdlib only).

Commands:
  auth-url             print the link the account owner opens once to allow posting
  exchange CODE        turn the code from that link into tokens (saved encrypted)
  post VIDEO CAPTION   refresh the token and publish VIDEO

Env: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REDIRECT_URI,
     optional TIKTOK_PRIVACY (default PUBLIC_TO_EVERYONE).

The refresh token lives in tiktok/token.enc, AES-256 encrypted with the client
secret, so it can sit in a public repository and be rotated by the workflow.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://open.tiktokapis.com/v2"
TOKEN_FILE = Path(__file__).resolve().parent / "token.enc"
SCOPES = "user.info.basic,video.publish"


def env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"Missing environment variable {name}")
    return v


def request(method, url, *, data=None, headers=None, form=False):
    headers = dict(headers or {})
    body = None
    if data is not None and not isinstance(data, bytes):
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json; charset=UTF-8"
    elif isinstance(data, bytes):
        body = data
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
    try:
        return json.loads(raw or b"{}")
    except json.JSONDecodeError:
        return {"raw": raw.decode(errors="replace")}


# ---- token storage -------------------------------------------------------

def _openssl(args, data: bytes) -> bytes:
    return subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
         "-base64", "-A", "-pass", "env:TIKTOK_CLIENT_SECRET", *args],
        input=data, capture_output=True, check=True).stdout


def save_refresh_token(token: str) -> None:
    env("TIKTOK_CLIENT_SECRET")
    TOKEN_FILE.write_bytes(_openssl([], token.encode()) + b"\n")


def load_refresh_token() -> str:
    env("TIKTOK_CLIENT_SECRET")
    if not TOKEN_FILE.exists():
        sys.exit("No tiktok/token.enc yet: run the 'TikTok connect' workflow first.")
    return _openssl(["-d"], TOKEN_FILE.read_bytes().strip()).decode()


# ---- OAuth ---------------------------------------------------------------

def auth_url() -> str:
    q = urllib.parse.urlencode({
        "client_key": env("TIKTOK_CLIENT_KEY"),
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": env("TIKTOK_REDIRECT_URI"),
        "state": "autopost",
    })
    return f"https://www.tiktok.com/v2/auth/authorize/?{q}"


def _token(params) -> dict:
    res = request("POST", f"{API}/oauth/token/", form=True, data={
        "client_key": env("TIKTOK_CLIENT_KEY"),
        "client_secret": env("TIKTOK_CLIENT_SECRET"),
        **params,
    })
    if "access_token" not in res:
        sys.exit(f"Token request failed: {res.get('error')} {res.get('error_description')}")
    save_refresh_token(res["refresh_token"])
    return res


def exchange(code_or_url: str) -> None:
    code = code_or_url.strip()
    if "code=" in code:  # the whole redirected address was pasted
        code = urllib.parse.parse_qs(urllib.parse.urlparse(code).query)["code"][0]
    code = urllib.parse.unquote(code)
    _token({"code": code, "grant_type": "authorization_code",
            "redirect_uri": env("TIKTOK_REDIRECT_URI")})
    print("Connected. Refresh token saved to tiktok/token.enc")


def access_token() -> str:
    return _token({"grant_type": "refresh_token",
                   "refresh_token": load_refresh_token()})["access_token"]


# ---- publishing ----------------------------------------------------------

def _api(token, path, data):
    res = request("POST", f"{API}{path}", data=data,
                  headers={"Authorization": f"Bearer {token}"})
    err = res.get("error", {})
    if err.get("code", "ok") != "ok":
        raise RuntimeError(f"{path}: {err.get('code')} - {err.get('message')}")
    return res["data"]


def post(video: Path, caption: str) -> None:
    token = access_token()
    info = _api(token, "/post/publish/creator_info/query/", {})
    options = info.get("privacy_level_options", [])
    want = os.environ.get("TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE")
    privacy = want if want in options else (options[0] if options else "SELF_ONLY")
    print(f"Account: @{info.get('creator_username')}  privacy: {privacy}")

    size = video.stat().st_size

    def init(level):
        return _api(token, "/post/publish/video/init/", {
            "post_info": {
                "title": caption[:2200],
                "privacy_level": level,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1500,
                "is_aigc": True,
            },
            "source_info": {"source": "FILE_UPLOAD", "video_size": size,
                            "chunk_size": size, "total_chunk_count": 1},
        })

    try:
        data = init(privacy)
    except RuntimeError as e:
        if "unaudited" not in str(e) or privacy == "SELF_ONLY":
            raise
        print("::warning::App is not audited by TikTok yet - posting as private "
              "(only you can see it). Submit the app for review to post publicly.")
        data = init("SELF_ONLY")

    up = urllib.request.Request(data["upload_url"], data=video.read_bytes(),
                                method="PUT", headers={
        "Content-Type": "video/mp4",
        "Content-Length": str(size),
        "Content-Range": f"bytes 0-{size - 1}/{size}",
    })
    with urllib.request.urlopen(up, timeout=300) as r:
        print(f"Uploaded ({r.status})")

    for _ in range(30):
        time.sleep(10)
        st = _api(token, "/post/publish/status/fetch/",
                  {"publish_id": data["publish_id"]})
        status = st.get("status")
        print("Status:", status)
        if status == "PUBLISH_COMPLETE":
            return
        if status == "FAILED":
            raise RuntimeError(f"Publish failed: {st.get('fail_reason')}")
    print("::warning::Still processing on TikTok's side; it usually finishes on its own.")


def main(argv):
    if argv[:1] == ["auth-url"]:
        print(auth_url())
    elif argv[:1] == ["exchange"] and len(argv) == 2:
        exchange(argv[1])
    elif argv[:1] == ["post"] and len(argv) == 3:
        post(Path(argv[1]), argv[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
