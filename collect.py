#!/usr/bin/env python3
"""3D-Druck Lead-Radar – Sammel-Dienst.

Ruft öffentliche Feeds ab (Reddit JSON/RSS, Lemmy-API, Mastodon-Hashtags),
normalisiert die Beiträge und schreibt sie nach leads.json.
Nur Python-Standardbibliothek. Läuft als GitHub Action (siehe .github/workflows).
"""
import json, os, re, sys, time, html, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone

OUT = os.environ.get("LEADS_FILE", "leads.json")
KEEP_DAYS = 21
MAX_LEADS = 900
UA = os.environ.get("RADAR_UA", "lead-radar/1.0 (public feed reader; github action)")

SUBS_ALL = ["3Dprintmything", "3Drequests", "PrintMyThing", "3Dprintingrequests"]
SUBS_SEARCH = [
    ("3Dprinting", '"print for me" OR "someone to print" OR "can someone print" OR "looking for someone to print"'),
    ("BambuLab", '"print for me" OR "someone to print" OR "can someone print"'),
    ("3Ddruck", 'gesucht OR "drucken lassen" OR "wer kann" OR "suche jemanden"'),
    ("de", '"3D Druck" OR "3D-Druck" OR 3D-Drucker'),
    ("germany", '"3D print" OR "3D printer" OR "3D printing"'),
]
DACH_HINT = {"de", "3Ddruck", "germany"}
LEMMY = [("printmything@lemmy.world", "Lemmy !printmything", True), ("3DPrinting@lemmy.world", "Lemmy !3DPrinting", False)]
MASTO = [("mastodon.social", "3ddruck", "Mastodon #3DDruck", True), ("troet.cafe", "3ddruck", "troet.cafe #3DDruck", True),
         ("norden.social", "3ddruck", "norden.social #3DDruck", True), ("mastodon.social", "3dprinting", "Mastodon #3DPrinting", False),
         ("mastodon.social", "3dprintrequest", "Mastodon #3DPrintRequest", False)]

REQ = re.compile(r"\b(print for me|someone to print|anyone (?:print|able to print|with a (?:3d )?printer)|can (?:someone|somebody|anyone) print|looking for (?:someone|somebody|a printer|a print service|printing)|need (?:something|this|a part|it) (?:3d )?printed|need someone|request|commission|drucken lassen|suche (?:jemanden|wen|einen drucker)|gesucht|jemand mit (?:einem )?3d.?drucker|wer kann)", re.I)


def get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def strip_html(s):
    s = re.sub(r"<br\s*/?>|</p>", "\n", s or "", flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def reddit_token():
    cid, sec = os.environ.get("REDDIT_CLIENT_ID"), os.environ.get("REDDIT_CLIENT_SECRET")
    if not (cid and sec):
        return None
    import base64
    data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request("https://www.reddit.com/api/v1/access_token", data=data, headers={
        "User-Agent": UA, "Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode()})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("access_token")
    except Exception as e:
        print("reddit oauth failed:", e, file=sys.stderr)
        return None


def reddit_listing(path, label, all_posts, dach, token):
    """path like /r/x/new or /r/x/search ; returns list of leads. Tries OAuth -> JSON -> RSS."""
    qs = "raw_json=1&limit=50"
    attempts = []
    if token:
        attempts.append(("oauth", f"https://oauth.reddit.com{path}?{qs}"))
    attempts.append(("json", f"https://www.reddit.com{path}.json?{qs}"))
    attempts.append(("rss", f"https://www.reddit.com{path}.rss?{qs}"))
    for kind, url in attempts:
        if "?" in path:  # search path already has query
            base, q = path.split("?", 1)
            url = {"oauth": f"https://oauth.reddit.com{base}?{q}&{qs}", "json": f"https://www.reddit.com{base}.json?{q}&{qs}",
                   "rss": f"https://www.reddit.com{base}.rss?{q}&{qs}"}[kind]
        try:
            if kind == "oauth":
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Authorization": "Bearer " + token})
                with urllib.request.urlopen(req, timeout=25) as r:
                    raw = r.read()
            else:
                raw = get(url, "application/json" if kind != "rss" else "application/atom+xml")
            if kind == "rss":
                return parse_reddit_rss(raw, label, all_posts, dach), kind
            j = json.loads(raw)
            out = []
            for c in j.get("data", {}).get("children", []):
                p = c.get("data", {})
                out.append({"id": "reddit:" + p.get("id", ""), "source": label, "kind": "reddit", "title": p.get("title", ""),
                            "text": (p.get("selftext") or "")[:4000], "url": "https://www.reddit.com" + p.get("permalink", ""),
                            "created": int(p.get("created_utc", 0) * 1000), "author": p.get("author", ""),
                            "flair": p.get("link_flair_text") or "", "all": all_posts, "dachHint": dach})
            return out, kind
        except Exception as e:
            print(f"  {label} {kind}: {e}", file=sys.stderr)
            time.sleep(2)
    return None, "failed"


def parse_reddit_rss(raw, label, all_posts, dach):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(raw)
    out = []
    for e in root.findall("a:entry", ns):
        eid = (e.findtext("a:id", "", ns) or "").replace("t3_", "")
        link = e.find("a:link", ns)
        upd = e.findtext("a:published", "", ns) or e.findtext("a:updated", "", ns)
        try:
            ts = int(datetime.fromisoformat(upd.replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            ts = 0
        cat = e.find("a:category", ns)
        out.append({"id": "reddit:" + eid, "source": label, "kind": "reddit", "title": e.findtext("a:title", "", ns),
                    "text": strip_html(e.findtext("a:content", "", ns))[:4000].replace("submitted by", "").strip(),
                    "url": link.get("href") if link is not None else "", "created": ts,
                    "author": (e.findtext("a:author/a:name", "", ns) or "").replace("/u/", ""), "flair": "",
                    "all": all_posts, "dachHint": dach})
    return out


def lemmy(community, label, all_posts):
    j = json.loads(get(f"https://lemmy.world/api/v3/post/list?community_name={community}&sort=New&limit=40"))
    out = []
    for v in j.get("posts", []):
        p = v.get("post", {})
        try:
            ts = int(datetime.fromisoformat(p.get("published", "").replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            ts = 0
        out.append({"id": "lemmy:" + str(p.get("ap_id") or p.get("id")), "source": label, "kind": "lemmy", "title": p.get("name", ""),
                    "text": (p.get("body") or "")[:4000], "url": p.get("ap_id") or f"https://lemmy.world/post/{p.get('id')}",
                    "created": ts, "author": v.get("creator", {}).get("name", ""), "flair": "", "all": all_posts, "dachHint": False})
    return out


def mastodon(host, tag, label, dach):
    j = json.loads(get(f"https://{host}/api/v1/timelines/tag/{tag}?limit=40"))
    out = []
    for s in j:
        t = strip_html(s.get("content", ""))
        try:
            ts = int(datetime.fromisoformat(s.get("created_at", "").replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            ts = 0
        out.append({"id": "masto:" + (s.get("uri") or str(s.get("id"))), "source": label, "kind": "mastodon",
                    "title": t.split("\n")[0][:140], "text": t[:4000], "url": s.get("url") or s.get("uri"), "created": ts,
                    "author": s.get("account", {}).get("acct", ""), "flair": "", "all": False, "dachHint": dach})
    return out


def main():
    try:
        with open(OUT, encoding="utf-8") as f:
            old = json.load(f)
        old = old.get("leads", old) if isinstance(old, dict) else old
    except Exception:
        old = []
    leads = {l["id"]: l for l in old if l.get("id")}
    status = {}
    token = reddit_token()

    jobs = [(f"/r/{s}/new", f"r/{s}", True, False) for s in SUBS_ALL]
    jobs += [(f"/r/{s}/search?" + urllib.parse.urlencode({"q": q, "restrict_sr": 1, "sort": "new", "t": "month"}), f"r/{s} (Suche)", False, s in DACH_HINT) for s, q in SUBS_SEARCH]
    for path, label, all_posts, dach in jobs:
        items, how = reddit_listing(path, label, all_posts, dach, token)
        status[label] = {"ok": items is not None, "via": how, "n": len(items or [])}
        for it in items or []:
            if all_posts or REQ.search(it["title"] + " " + it["text"]):
                leads[it["id"]] = {**leads.get(it["id"], {}), **it}
        time.sleep(1.5)  # freundlich zu Reddit
    for community, label, all_posts in LEMMY:
        try:
            items = lemmy(community, label, all_posts); status[label] = {"ok": True, "n": len(items)}
            for it in items:
                if all_posts or REQ.search(it["title"] + " " + it["text"]):
                    leads[it["id"]] = it
        except Exception as e:
            status[label] = {"ok": False, "err": str(e)}
    for host, tag, label, dach in MASTO:
        try:
            items = mastodon(host, tag, label, dach); status[label] = {"ok": True, "n": len(items)}
            for it in items:
                if REQ.search(it["title"] + " " + it["text"]):
                    leads[it["id"]] = it
        except Exception as e:
            status[label] = {"ok": False, "err": str(e)}

    cutoff = (time.time() - KEEP_DAYS * 86400) * 1000
    arr = sorted((l for l in leads.values() if l.get("created", 0) >= cutoff), key=lambda l: -l.get("created", 0))[:MAX_LEADS]
    doc = {"generated": datetime.now(timezone.utc).isoformat(), "status": status, "leads": arr}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=0)
    print(json.dumps(status, indent=1))
    print(f"{len(arr)} leads gespeichert")


if __name__ == "__main__":
    main()
