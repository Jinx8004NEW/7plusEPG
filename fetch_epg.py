import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

API_BASE = "https://fvau-api-prod.switch.tv/content/v1/epgs/"

CHANNELS = {
    "Seven": "1013:0502:0520",
    "7two":  "1013:0502:0522",
    "7mate": "1013:0502:0527",
}

DAY_FROM = -1
DAY_TO = 4
TIMEOUT = 20


def iso_z(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def fetch_day(triplet, day_start, day_end):
    params = {
        "start": iso_z(day_start),
        "end": iso_z(day_end),
        "sort": "start",
        "related_entity_types": "episode.firstImage,shows.firstImage",
        "related_levels": "2",
        "include_related": "1",
        "expand_related": "full",
        "limit": "100",
        "offset": "0",
    }
    url = API_BASE + triplet + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (7plus-epg bot)",
        "Accept": "application/json",
        "Origin": "https://www.freeview.com.au",
        "Referer": "https://www.freeview.com.au/",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8")).get("data", [])


def episode_for(prog):
    eps = (prog.get("related") or {}).get("episodes") or []
    for e in eps:
        if e.get("id") == prog.get("episode_id"):
            return e
    return eps[0] if eps else None


def trim(prog):
    ep = episode_for(prog)
    sub, synopsis, image = "", "", ""
    if ep:
        synopsis = (ep.get("synopsis") or "").strip()
        cats = ep.get("categories") or []
        season = next((c.split("/")[-1].strip() for c in cats if c.startswith("season_number/")), None)
        epno = ep.get("episode_number")
        bits = []
        if season:
            bits.append("S%s" % season)
        if epno:
            bits.append("E%s" % epno)
        sub = " ".join(bits)
        imgs = (ep.get("related") or {}).get("images") or []
        if imgs:
            url = imgs[0].get("url", "")
            image = url.replace("http://", "https://") if url else ""
    return {
        "title": prog.get("title", ""),
        "start": prog.get("start", ""),
        "end": prog.get("end", ""),
        "sub": sub,
        "synopsis": synopsis[:400],
        "image": image,
    }


def build():
    now = datetime.now(timezone.utc)
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    out = {}
    for name, triplet in CHANNELS.items():
        seen = {}
        for d in range(DAY_FROM, DAY_TO):
            day_start = base + timedelta(days=d)
            day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
            try:
                rows = fetch_day(triplet, day_start, day_end)
            except Exception as e:
                print("WARN %s day %+d: %s" % (name, d, e))
                continue
            for p in rows:
                key = p.get("start", "") + "|" + p.get("title", "")
                if key not in seen:
                    seen[key] = trim(p)
        progs = sorted(seen.values(), key=lambda x: x["start"])
        cutoff = base + timedelta(days=DAY_FROM)
        progs = [p for p in progs if p["end"] and datetime.fromisoformat(p["end"]) >= cutoff]
        out[name] = progs
        print("%-6s %d programmes" % (name, len(progs)))

    return {
        "source": "Freeview Australia (Sydney feed)",
        "generated_at": int(time.time()),
        "generated_at_iso": iso_z(now),
        "channels": out,
    }


def main():
    data = build()
    os.makedirs("data", exist_ok=True)
    with open("data/epg.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    total = sum(len(v) for v in data["channels"].values())
    print("Wrote data/epg.json — %d programmes total" % total)
    if total == 0:
        raise SystemExit("No programmes fetched — not overwriting with empty guide.")


if __name__ == "__main__":
    main()
