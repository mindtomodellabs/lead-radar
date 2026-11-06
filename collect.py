#!/usr/bin/env python3
"""3D-Druck Lead-Radar – Sammel-Dienst.

Ruft öffentliche Quellen ab und schreibt die Anfragen nach leads.json:
  ohne Zugang:  Reddit (RSS, endet 13.11.2026), Lemmy (Communities + Suche), Mastodon-Hashtags,
                Discourse-Forum (Bambu-Lab-Forum)
  mit Zugang (GitHub-Secrets, siehe ANLEITUNG.md):
                Bluesky-Suche (BSKY_HANDLE, BSKY_APP_PASSWORD)
                Mastodon-Volltextsuche (MASTODON_TOKEN)
                Google Alerts (GOOGLE_ALERTS_FEEDS)
                E-Mail-Alarme z. B. von Kleinanzeigen (IMAP_HOST, IMAP_USER, IMAP_PASS, IMAP_FOLDER)
Je Lead wird – wo die Quelle es liefert – die Zahl der Antworten gespeichert ("comments").
Nur Python-Standardbibliothek. Läuft als GitHub Action (siehe .github/workflows).
"""
import json, os, re, sys, time, html, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone

OUT = os.environ.get("LEADS_FILE", "leads.json")
KEEP_DAYS = 21
MAX_LEADS = 900
UA = os.environ.get("RADAR_UA", "lead-radar/1.0 (public feed reader; github action)")

SUBS_ALL = ["3Dprintmything", "PrintMyThing"]  # Reddit: nur Quellen, die zuletzt noch geliefert haben (RSS endet 13.11.2026)
SUBS_SEARCH = [
    ("3Dprinting", '"print for me" OR "someone to print" OR "can someone print" OR "looking for someone to print"'),
]
DACH_HINT = {"de", "3Ddruck", "germany"}
LEMMY = [("printmything@lemmy.world", "Lemmy !printmything", True), ("3DPrinting@lemmy.world", "Lemmy !3DPrinting", False)]
MASTO = [("mastodon.social", "3ddruck", "Mastodon #3DDruck", True), ("norden.social", "3ddruck", "norden.social #3DDruck", True),
         ("mastodon.social", "3ddrucker", "Mastodon #3DDrucker", True),
         ("mastodon.social", "3dprinting", "Mastodon #3DPrinting", False), ("mastodon.social", "3dprint", "Mastodon #3DPrint", False),
         ("mastodon.social", "3dprintrequest", "Mastodon #3DPrintRequest", False)]
LEMMY_SEARCH = ["3d print request", "print this for me", "someone print", "3D Druck gesucht", "3D drucken lassen"]
DISCOURSE = [("forum.bambulab.com", "Bambu-Lab-Forum")]
DISCOURSE_Q = ['"print for me"', '"someone to print"', '"print service"', '"drucken lassen"', '"looking for someone"']
BSKY_Q = ['"print for me"', '"someone to print"', '"3d print this"', '"3D Druck" gesucht', '"wer kann mir" drucken', '"3D drucken lassen"', '"need something 3d printed"']
MASTO_Q = ["print for me 3d", "3D Druck gesucht", "wer kann mir drucken", "someone 3d print"]

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
                            "flair": p.get("link_flair_text") or "", "all": all_posts, "dachHint": dach,
                            "comments": p.get("num_comments")})
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
                    "text": re.sub(r"\s*(submitted by)?\s*/u/\S+\s*\[link\]\s*\[comments\]\s*$", "", strip_html(e.findtext("a:content", "", ns))).strip()[:4000],
                    "url": link.get("href") if link is not None else "", "created": ts,
                    "author": (e.findtext("a:author/a:name", "", ns) or "").replace("/u/", ""), "flair": "",
                    "all": all_posts, "dachHint": dach})
    return out


def lemmy(community, label, all_posts, search=None):
    if search:
        j = json.loads(get("https://lemmy.world/api/v3/search?" + urllib.parse.urlencode({"q": search, "type_": "Posts", "sort": "New", "limit": 30, "listing_type": "All"})))
    else:
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
                    "created": ts, "author": v.get("creator", {}).get("name", ""), "flair": "", "all": all_posts, "dachHint": False,
                    "comments": (v.get("counts") or {}).get("comments")})
    return out


def mastodon(host, tag, label, dach, statuses=None):
    j = statuses if statuses is not None else json.loads(get(f"https://{host}/api/v1/timelines/tag/{tag}?limit=40"))
    out = []
    for s in j:
        t = strip_html(s.get("content", ""))
        try:
            ts = int(datetime.fromisoformat(s.get("created_at", "").replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            ts = 0
        out.append({"id": "masto:" + (s.get("uri") or str(s.get("id"))), "source": label, "kind": "mastodon",
                    "title": t.split("\n")[0][:140], "text": t[:4000], "url": s.get("url") or s.get("uri"), "created": ts,
                    "author": s.get("account", {}).get("acct", ""), "flair": "", "all": False, "dachHint": dach,
                    "comments": s.get("replies_count")})
    return out


def ts_of(iso):
    try:
        return int(datetime.fromisoformat((iso or "").replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return 0


def mastodon_search(token):
    out = []
    for q in MASTO_Q:
        url = "https://mastodon.social/api/v2/search?" + urllib.parse.urlencode({"q": q, "type": "statuses", "limit": 40})
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=25) as r:
            out += mastodon("mastodon.social", "", "Mastodon-Suche", False, json.load(r).get("statuses", []))
        time.sleep(1)
    return out


def discourse(host, label):
    out, seen = [], set()
    for q in DISCOURSE_Q:
        j = json.loads(get(f"https://{host}/search.json?" + urllib.parse.urlencode({"q": q + " order:latest"})))
        blurbs = {p.get("topic_id"): p for p in j.get("posts", [])}
        for t in j.get("topics", []):
            if t["id"] in seen:
                continue
            seen.add(t["id"])
            p = blurbs.get(t["id"], {})
            out.append({"id": f"discourse:{host}:{t['id']}", "source": label, "kind": "forum", "title": t.get("title", ""),
                        "text": strip_html(p.get("blurb", ""))[:4000], "url": f"https://{host}/t/{t.get('slug', 'x')}/{t['id']}",
                        "created": ts_of(t.get("created_at")), "author": p.get("username", ""), "flair": "", "all": False,
                        "dachHint": False, "comments": max(0, (t.get("posts_count") or 1) - 1)})
        time.sleep(1)
    return out


def bluesky(handle, app_pw):
    body = json.dumps({"identifier": handle, "password": app_pw}).encode()
    req = urllib.request.Request("https://bsky.social/xrpc/com.atproto.server.createSession", data=body,
                                 headers={"User-Agent": UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        tok = json.load(r)["accessJwt"]
    out = []
    for q in BSKY_Q:
        url = "https://bsky.social/xrpc/app.bsky.feed.searchPosts?" + urllib.parse.urlencode({"q": q, "sort": "latest", "limit": 50})
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Authorization": "Bearer " + tok})
        with urllib.request.urlopen(req, timeout=25) as r:
            posts = json.load(r).get("posts", [])
        for p in posts:
            rec, a = p.get("record", {}), p.get("author", {})
            if rec.get("reply"):  # nur Ursprungs-Beiträge, keine Antworten
                continue
            t = rec.get("text", "")
            rkey = p.get("uri", "").rsplit("/", 1)[-1]
            out.append({"id": "bsky:" + p.get("uri", ""), "source": "Bluesky", "kind": "bluesky", "title": t.split("\n")[0][:140],
                        "text": t[:4000], "url": f"https://bsky.app/profile/{a.get('handle', '')}/post/{rkey}",
                        "created": ts_of(rec.get("createdAt")), "author": a.get("handle", ""), "flair": "", "all": False,
                        "dachHint": "de" in (rec.get("langs") or []), "comments": p.get("replyCount")})
        time.sleep(1)
    return out


def alert_urls(raw):
    raw = (raw or "").strip()
    found = re.findall(r"(?:https?://)?(?:www\.)?google\.[a-z.]+/alerts/feeds/\d+/\d+", raw)
    urls = [u if u.startswith("http") else "https://" + u.lstrip("/") for u in found]
    urls = [u.replace("http://", "https://", 1) for u in urls]
    if not urls:
        # Diagnose ohne den Inhalt zu verraten (leads.json ist öffentlich)
        low = raw.lower()
        hint = "beginnt mit 'tag:'" if low.startswith("tag:") else ("enthält 'alerts/feeds'" if "alerts/feeds" in low else ("enthält 'google.com/alerts' ohne /feeds/ – das ist die Verwaltungsseite, nicht der RSS-Feed" if "alerts" in low else "enthält keine Google-Alerts-Adresse"))
        raise ValueError(f"keine gültige Feed-Adresse gefunden ({len(raw)} Zeichen, {hint}). Erwartet: https://www.google.com/alerts/feeds/<Zahl>/<Zahl>")
    return list(dict.fromkeys(urls))


def google_alerts(feeds):
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for i, feed in enumerate(feeds):
        root = ET.fromstring(get(feed, "application/atom+xml"))
        for e in root.findall("a:entry", ns):
            link = e.find("a:link", ns)
            href = link.get("href", "") if link is not None else ""
            real = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("url", [href])[0]
            out.append({"id": "galert:" + real, "source": "Google Alerts", "kind": "web", "title": strip_html(e.findtext("a:title", "", ns)),
                        "text": strip_html(e.findtext("a:content", "", ns))[:4000], "url": real,
                        "created": ts_of(e.findtext("a:published", "", ns) or e.findtext("a:updated", "", ns)), "author": urllib.parse.urlparse(real).netloc,
                        "flair": "", "all": True, "dachHint": ".de/" in real or real.endswith(".de"), "comments": None})
    return out


def mail_alerts(host, user, pw, folder):
    """Liest Benachrichtigungs-Mails (z. B. gespeicherte Kleinanzeigen-Suche) der letzten 3 Tage aus einem IMAP-Ordner.
    Mails werden nur gelesen (BODY.PEEK), nicht verändert. Übernommen werden nur Titel + Link der Anzeigen."""
    import imaplib, email
    from email.utils import parsedate_to_datetime
    out = []
    host, user = host.strip(), user.strip()
    pw = re.sub(r"\s+", "", pw)  # App-Passwörter werden mit Leerzeichen angezeigt, gehören aber ohne
    M = imaplib.IMAP4_SSL(host)
    try:
        M.login(user, pw)
    except imaplib.IMAP4.error as e:
        dom = user.split("@")[-1] if "@" in user else "(kein @ in IMAP_USER)"
        raise RuntimeError(f"Anmeldung abgelehnt: Server {host}, Konto-Domain {dom}, Passwortlänge {len(pw)} (App-Passwort = 16). {e}")
    M.select('"' + folder + '"', readonly=True)
    since = time.strftime("%d-%b-%Y", time.gmtime(time.time() - 3 * 86400))
    _, ids = M.search(None, "SINCE", since)
    for mid in ids[0].split()[-80:]:
        _, data = M.fetch(mid, "(BODY.PEEK[])")
        msg = email.message_from_bytes(data[0][1])
        try:
            ts = int(parsedate_to_datetime(msg.get("Date")).timestamp() * 1000)
        except Exception:
            ts = 0
        sender = (msg.get("From") or "").lower()
        htmls = [p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "replace")
                 for p in msg.walk() if p.get_content_type() == "text/html"]
        for h in htmls:
            for href, label in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', h, flags=re.S | re.I):
                txt = strip_html(label).strip()
                href = html.unescape(href)
                if "kleinanzeigen.de/s-anzeige/" in href and len(txt) > 8:
                    clean = href.split("?")[0]
                    out.append({"id": "mail:" + clean, "source": "Kleinanzeigen (E-Mail)" if "kleinanzeigen" in sender or "kleinanzeigen" in href else "E-Mail-Alarm",
                                "kind": "mail", "title": txt[:160], "text": "", "url": clean, "created": ts, "author": "", "flair": "",
                                "all": True, "dachHint": True, "comments": None})
    M.logout()
    return out


# Nur echte Druckaufträge von Leuten ohne eigenen Drucker – kein Design, keine geschützten Figuren, keine Kaufberatung.
IP_RE = re.compile(r"\b(super ?mario|mario kart|mario bros|luigi|bowser|yoshi|zelda|triforce|hyrule|pok[eé]mon|pikachu|pok[eé] ?ball|eevee|charizard|"
                   r"kirby|metroid|amiibo|disney|pixar|mickey|minnie|elsa|toy story|marvel|avengers|spider.?man|iron ?man|captain america|hulk|dr\.? ?doom|"
                   r"thanos|deadpool|wolverine|groot|batman|batmobile|superman|dc comics|star ?wars|mandalorian|grogu|baby yoda|darth|vader|stormtrooper|"
                   r"lightsaber|boba fett|harry potter|hogwarts|percy jackson|warhammer|space marines?|40k|necron|games workshop|minecraft|sonic the hedgehog|"
                   r"hello kitty|sanrio|transformers|optimus prime|gundam|dragon ?ball|goku|naruto|one piece (anime|figure|figur|luffy)|luffy|demon slayer|jujutsu|"
                   r"my hero academia|attack on titan|master chief|fortnite|overwatch|genshin|ace combat|shrek|simpsons|spongebob|paw patrol|peppa pig|bluey|minions|"
                   r"ghostbusters|jurassic park|lord of the rings|lotr|samwise|frodo|gandalf|game of thrones|stranger things|xenomorph|alien isolation|teen titans?|tt communicator|"
                   r"runescape|world of warcraft|league of legends|elden ring|dark souls|halo infinite|zelda|anime figur\w*|funko)\b", re.I)
NOPRINTER_RE = re.compile(r"\b((buy|buying|purchase|kaufen|kaufe|anschaffen|upgrade|recommend\w*|empfehl\w*|second|zweite[nmr]?|best|bester?|budget)\s+(3d.?)?(printer|drucker)\b(?!\s*(person|guy|service|dienst))|"
                          r"(which|what|welche[nmr]?)\s+(3d.?)?(printer|drucker)\s+(should|to|soll|kaufen|buy)|printer (recommendation|advice|to buy)|kaufberatung|drucker.?empfehlung|help me (choose|pick) a|"
                          r"(i|ich)\s+(have|own|habe|besitze)\s+(a|an|einen?)\s+(3d.?)?(printer|drucker)|using my (3d.?)?(printer|p1s|x1c?|a1( mini)?|ender|prusa|bambu)|mit meinem (3d.?)?drucker|"
                          r"zweit-?drucker|second printer|\b(ich habe|ich hab|hab|hab's|i)\s+(\w+\s+){0,4}(gedruckt|printed)\b|my prints (are|keep|have)|delaminat\w*|warping|stringing|layer shift|clogg?ed|"
                          r"browser.?tool|mein neues|our new|we (built|made)|wir haben .* gebaut|offering services|\[offer(ing)?\b|for sale|zu verkaufen|verkaufe|i can print|ich drucke f(ü|ue)r|join my (production )?team|verteile|giveaway)", re.I)
DESIGN_RE = re.compile(r"(\bdesign (it|this|one|something|me|a|an|and|for me|from scratch)\b|\bhelp (me )?(to )?design\b|\bdesign\s*(\+|&|and|/)\s*(\w+\s+)?print|\bto be designed\b|\bdesigned and printed\b|"
                       r"\b(looking for|need|hiring|seeking|suche)( a| an| einen?)? (3d )?(designer|modell?er|sculptor|cad (person|designer)|3d artist|nodes artist|artist)\b|\[hiring\]|"
                       r"\bmodel(l)?(ing|ieren) (request|job|help|for me)|\bmodel (it|this|one|something) for me|\bneed (a|an) (3d |stl )?model (of|for)\b|\bmodelisation|mod[eé]lisation|"
                       r"\bsculpt (it|this|me)|\bkonstruier\w*|\bentwerfen\b|\bnachbauen\b|\breverse.?engineer\w*|\b(recreate|re-?create|replicate)\b.*\b(from|nach)\b|"
                       r"\bfrom (a |these |the )?(photos?|pictures?|sketch|drawing)\b|\bnach (einem |einer )?(foto|bild|skizze|zeichnung)\b|\bno (stl|file|model)\b|"
                       r"\bdon'?t have (a|the|any) (stl|file|model)|\bkeine (datei|stl|vorlage)\b|\bcan'?t find (the|a|any) (file|stl|model)|\bneed (someone|somebody) to (make|create|model|design)|"
                       r"\b(edit|modify|modification|tweak|merge|merging|change|fix) (of |the |my |this |an |a )?(stl|file|model|design|part)|\bmerging two\b|\b(rigging|re-?rigging)\b|"
                       r"\bcommission(s|ing)?\b|\b(add|adding)\b.{0,40}\b(to|in|into) (my|the|this) (file|stl|model)|\bminor change|\bmodification\b|\bediting\b|\bcombin(e|ing) (\d|two|2|the)|"
                       r"\b(3d )?mesh\b|\bfusion ?360|\b3d model (for|of)\b|\blooking for (a|an|the) stl\b|\bstl (file )?(modification|edit)|\bcan (someone|anyone) make me\b|\bcreate (a|an|me)\b)", re.I)
PRINT_RE = re.compile(r"\b(print|prints|printed|printing|drucken|druck|gedruckt|drucker|ausdrucken)\b", re.I)
# Soziale Netzwerke: nur Beiträge, die erkennbar um 3D-Druck gehen ("print for me" heißt dort oft Fotodruck)
CONTEXT_RE = re.compile(r"(\b3d\b|3-d|\bstl\b|\.3mf|\b3mf\b|filament|\bpla\b|petg|\btpu\b|\basa\b|3d.?druck|3d.?print|\bdrucker\b|printables|thingiverse|makerworld|thangs|cults3d)", re.I)


def reject_reason(l):
    t = (l.get("title", "") + "\n" + l.get("text", ""))
    if l.get("kind") in ("bluesky", "mastodon", "lemmy", "forum", "web") and not CONTEXT_RE.search(t):
        return "kein 3D-Druck-Bezug"
    from_request_sub = l.get("all") and l.get("source") != "r/3Drequests"
    if not from_request_sub and not PRINT_RE.search(t):
        return "kein Druckauftrag"
    if IP_RE.search(t):
        return "Urheberrecht/Marke"
    if NOPRINTER_RE.search(t):
        return "hat Drucker / sucht Drucker / Angebot"
    if DESIGN_RE.search(t):
        return "Design/Modellieren gewünscht"
    return None


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
                    leads[it["id"]] = {**leads.get(it["id"], {}), **it}
        except Exception as e:
            status[label] = {"ok": False, "err": str(e)}
    try:
        n = 0
        for q in LEMMY_SEARCH:
            for it in lemmy(None, "Lemmy-Suche", False, search=q):
                n += 1
                if REQ.search(it["title"] + " " + it["text"]):
                    leads[it["id"]] = {**leads.get(it["id"], {}), **it}
            time.sleep(1)
        status["Lemmy-Suche"] = {"ok": True, "n": n}
    except Exception as e:
        status["Lemmy-Suche"] = {"ok": False, "err": str(e)}
    for host, label in DISCOURSE:
        try:
            items = discourse(host, label); status[label] = {"ok": True, "n": len(items)}
            for it in items:
                if REQ.search(it["title"] + " " + it["text"]):
                    leads[it["id"]] = {**leads.get(it["id"], {}), **it}
        except Exception as e:
            status[label] = {"ok": False, "err": str(e)}

    optional = [
        ("Bluesky", ("BSKY_HANDLE", "BSKY_APP_PASSWORD"), lambda e: bluesky(e[0], e[1]), True),
        ("Mastodon-Suche", ("MASTODON_TOKEN",), lambda e: mastodon_search(e[0]), True),
        ("Google Alerts", ("GOOGLE_ALERTS_FEEDS",), lambda e: google_alerts(alert_urls(e[0])), False),
        ("E-Mail-Alarme", ("IMAP_HOST", "IMAP_USER", "IMAP_PASS"), lambda e: mail_alerts(e[0], e[1], e[2], os.environ.get("IMAP_FOLDER") or "Lead-Radar"), False),
    ]
    for label, keys, fn, need_req in optional:
        vals = [os.environ.get(k) for k in keys]
        if not all(vals):
            status[label] = {"ok": False, "err": "Zugang fehlt: " + ", ".join(keys)}
            continue
        try:
            items = fn(vals); status[label] = {"ok": True, "n": len(items)}
            for it in items:
                if not need_req or REQ.search(it["title"] + " " + it["text"]):
                    leads[it["id"]] = {**leads.get(it["id"], {}), **it}
        except Exception as e:
            status[label] = {"ok": False, "err": str(e)[:200]}
    for host, tag, label, dach in MASTO:
        try:
            items = mastodon(host, tag, label, dach); status[label] = {"ok": True, "n": len(items)}
            for it in items:
                if REQ.search(it["title"] + " " + it["text"]):
                    leads[it["id"]] = {**leads.get(it["id"], {}), **it}
        except Exception as e:
            status[label] = {"ok": False, "err": str(e)}

    cutoff = (time.time() - KEEP_DAYS * 86400) * 1000
    removed = {}
    kept = []
    for l in leads.values():
        if l.get("created", 0) < cutoff:
            continue
        why = reject_reason(l)
        if why:
            removed[why] = removed.get(why, 0) + 1
        else:
            kept.append(l)
    arr = sorted(kept, key=lambda l: -l.get("created", 0))[:MAX_LEADS]
    print("aussortiert:", removed)
    day = (time.time() - 86400) * 1000
    doc = {"generated": datetime.now(timezone.utc).isoformat(), "status": status,
           "last24h": sum(1 for l in arr if l.get("created", 0) >= day), "filtered": removed, "leads": arr}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=0)
    print(json.dumps(status, indent=1))
    print(f"{len(arr)} leads gespeichert")


if __name__ == "__main__":
    main()
