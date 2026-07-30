"""
BookMyShow reachability probe — deploy to Render to find out whether the fetch
that works on a laptop also works from a datacenter IP.

Deploy on Render:
    Build Command:  pip install -r requirements.txt
    Start Command:  gunicorn app:app
    (or Start Command: python app.py  — works too)

Then open the service URL.
"""

import os
import re
import urllib.error
import urllib.request

from flask import Flask, jsonify

app = Flask(__name__)

# A browser User-Agent matters. Without it urllib sends "Python-urllib/3.x",
# which Cloudflare blocks outright — you would get a 403 for the wrong reason
# and conclude the host is blocked when it is not.
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

VENUE_URL = "https://in.bookmyshow.com/HYD/venue-list"
SHOW_URL = (
    "https://in.bookmyshow.com/cinemas/hyderabad/"
    "br-hitech-70mm-madhapur/buytickets/HMHD/20260802"
)


def fetch(url, user_agent=BROWSER_UA):
    """
    Fetch and report. Note: NO `context=` argument — passing an explicit
    ssl.create_default_context() changes the TLS ClientHello enough to get a
    403, while omitting it returns 200. Measured, not guessed. Leave it out.
    """
    try:
        headers = {"User-Agent": user_agent} if user_agent else {}
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return {"status": response.status, "bytes": len(body), "body": body}
    except urllib.error.HTTPError as error:
        return {"status": error.code, "bytes": 0, "body": ""}
    except Exception as error:  # noqa: BLE001
        return {"status": 0, "bytes": 0, "body": "", "error": repr(error)[:200]}


def egress_ip():
    try:
        request = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": BROWSER_UA})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read().decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


@app.route("/")
def test():
    # 1. city -> venues, with a browser UA
    venues = fetch(VENUE_URL)
    codes = sorted(set(re.findall(r'"VenueCode"\s*:\s*"([A-Z0-9]{3,8})"', venues["body"])))

    # 2. same URL with urllib's default UA, to show the UA is what matters
    no_ua = fetch(VENUE_URL, user_agent=None)

    # 3. venue + date -> movies
    shows = fetch(SHOW_URL)
    events = sorted(set(re.findall(r'href="/movies/[^"]*?/(ET\d+)"', shows["body"])))
    titles = [t.strip() for t in re.findall(r'href="/movies/[^"]+"[^>]*>([^<]{2,90})</a>', shows["body"])]

    ok = venues["status"] == 200 and len(codes) > 0

    if ok:
        verdict = "WORKS FROM THIS HOST — safe to run the fetcher on the server."
    elif venues["status"] == 403:
        verdict = (
            "BLOCKED (403) FROM THIS HOST — IP reputation is part of the decision, "
            "so the fetcher must run from a residential connection instead."
        )
    else:
        verdict = "INCONCLUSIVE — status %s, check the error field." % venues["status"]

    return jsonify(
        {
            "verdict": verdict,
            "egress_ip": egress_ip(),
            "venue_list": {
                "status": venues["status"],
                "bytes": venues["bytes"],
                "venues_found": len(codes),
                "sample_codes": codes[:8],
                "error": venues.get("error"),
            },
            "venue_list_without_user_agent": {
                "status": no_ua["status"],
                "note": "403 here but 200 above means the User-Agent is the deciding factor.",
            },
            "showtimes": {
                "status": shows["status"],
                "bytes": shows["bytes"],
                "movies_found": len(events),
                "sample_titles": titles[:6],
                "error": shows.get("error"),
            },
        }
    )


@app.route("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
