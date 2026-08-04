"""
BookMyShow reachability probe — updated to avoid timeouts by disabling JS rendering
where unneeded and increasing request timeouts.
"""

import os
import re
import urllib.parse
import urllib.request
from flask import Flask, jsonify

app = Flask(__name__)

SCRAPER_API_KEY = "6a988f50e76286d88291e73cd9998202"

VENUE_URL = "https://in.bookmyshow.com/HYD/venue-list"
SHOW_URL = (
    "https://in.bookmyshow.com/cinemas/hyderabad/"
    "br-hitech-70mm-madhapur/buytickets/HMHD/20260802"
)


def fetch_via_scraper_api(target_url, render_js=False):
    """
    Routes target URL through ScraperAPI.
    
    :param target_url: Target URL to scrape.
    :param render_js: Set True ONLY for pages requiring full browser JS execution.
    """
    encoded_target = urllib.parse.quote(target_url, safe="")
    proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={encoded_target}"
    
    if render_js:
        proxy_url += "&render=true"

    try:
        request = urllib.request.Request(proxy_url)
        # Increased socket timeout to 70 seconds to allow for proxy retries
        with urllib.request.urlopen(request, timeout=70) as response:
            body = response.read().decode("utf-8", errors="ignore")
            return {"status": response.status, "bytes": len(body), "body": body}
    except urllib.error.HTTPError as error:
        return {"status": error.code, "bytes": 0, "body": ""}
    except Exception as error:  # noqa: BLE001
        return {"status": 0, "bytes": 0, "body": "", "error": repr(error)[:200]}


def egress_ip():
    try:
        request = urllib.request.Request("https://api.ipify.org")
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.read().decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


@app.route("/")
def test():
    # 1. Fetch venue list (render_js=False is much faster and rarely gets blocked)
    venues = fetch_via_scraper_api(VENUE_URL, render_js=False)
    codes = sorted(set(re.findall(r'"VenueCode"\s*:\s*"([A-Z0-9]{3,8})"', venues["body"])))

    # 2. Fetch showtimes (render_js=True for dynamic showtime/ticket elements)
    shows = fetch_via_scraper_api(SHOW_URL, render_js=True)
    events = sorted(set(re.findall(r'href="/movies/[^"]*?/(ET\d+)"', shows["body"])))
    titles = [t.strip() for t in re.findall(r'href="/movies/[^"]+"[^>]*>([^<]{2,90})</a>', shows["body"])]

    ok = (venues["status"] == 200 or shows["status"] == 200)

    if ok:
        verdict = "SUCCESS — Cloudflare bypassed without timeouts!"
    else:
        verdict = f"FAILED — Venue status: {venues['status']}, Show status: {shows['status']}"

    return jsonify(
        {
            "verdict": verdict,
            "render_egress_ip": egress_ip(),
            "venue_list": {
                "status": venues["status"],
                "bytes": venues["bytes"],
                "venues_found": len(codes),
                "sample_codes": codes[:8],
                "error": venues.get("error"),
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
