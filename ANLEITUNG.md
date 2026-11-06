# Lead-Radar rund um die Uhr (GitHub, kostenlos)

Dieses Paket macht zwei Dinge:

- **GitHub Action** (`collect.py`): ruft alle 15 Minuten Lemmy, Mastodon, Foren, Bluesky, Google Alerts, E-Mail-Alarme und (bis 13.11.2026) Reddit ab und schreibt die Anfragen in `leads.json`.
- **GitHub Pages** (`index.html`): zeigt dieselbe Radar-App. Dort gibt es keine Abruf-Sperre, deshalb holt die Seite beim Öffnen zusätzlich live direkt aus deinem Browser.

Dauer: ca. 10 Minuten. Kosten: 0 € (öffentliches Repo, GitHub Free).

## Schritte

1. Auf github.com einloggen (oder kostenloses Konto anlegen) → oben rechts **+** → **New repository**.
   Name: `lead-radar`, Sichtbarkeit **Public**, „Add a README“ NICHT anhaken → **Create repository**.
2. Auf der leeren Repo-Seite **uploading an existing file** anklicken. Den gesamten Inhalt dieses Ordners hineinziehen
   (`index.html`, `collect.py`, `leads.json`, `ANLEITUNG.md` **und** den Ordner `.github`) → **Commit changes**.
   Tipp: Der Ordner `.github` ist auf dem Mac/PC evtl. versteckt (Mac: ⌘ + ⇧ + . im Finder). Fehlt er nach dem Upload,
   lege die Datei per **Add file → Create new file** an, Name `.github/workflows/collect.yml`, und kopiere den Inhalt hinein.
3. **Settings → Actions → General** → unter „Workflow permissions“ **Read and write permissions** wählen → **Save**.
4. **Actions**-Tab → „Lead-Radar sammeln“ → **Run workflow**. Nach ca. 1 Minute sollte ein grüner Haken erscheinen
   und `leads.json` einen neuen Commit haben. Im Log siehst du je Quelle, ob sie geklappt hat.
5. **Settings → Pages** → Source: **Deploy from a branch**, Branch **main**, Ordner **/ (root)** → **Save**.
   Nach 1–2 Minuten ist dein Radar unter `https://DEIN-NAME.github.io/lead-radar/` erreichbar.
6. Diese Adresse im Radar unter **Einstellungen → Adresse deines Live-Radars** eintragen und am Handy als
   Lesezeichen bzw. „Zum Home-Bildschirm“ speichern.

## Mehr Quellen freischalten (Zugänge als GitHub-Secrets)

Ohne Zugang laufen schon: Lemmy (Communities + Suche), Mastodon-Hashtags, Bambu-Lab-Forum
und Reddit (nur noch bis 13.11.2026). Mit diesen vier Zugängen kommen deutlich mehr Leads dazu.
Jeden Wert speicherst du unter **Settings → Secrets and variables → Actions → New repository secret**.
Secrets sind auch in einem öffentlichen Repo geheim, niemand außer dir sieht sie.

1. **Bluesky-Suche**: Konto auf bsky.app anlegen → **Einstellungen → Datenschutz und Sicherheit → App-Passwörter** →
   neues App-Passwort erstellen. Secrets: `BSKY_HANDLE` (z. B. `deinname.bsky.social`) und `BSKY_APP_PASSWORD`.
2. **Mastodon-Volltextsuche**: Konto auf mastodon.social → **Einstellungen → Entwicklung → Neue Anwendung**,
   Name „Lead-Radar“, nur Berechtigung **read** anhaken → Speichern → „Dein Zugangs-Token“ kopieren.
   Secret: `MASTODON_TOKEN`.
3. **Google Alerts** (findet auch Kleinanzeigen-Gesuche und Forenbeiträge, die Google kennt): google.com/alerts →
   Suchbegriff eingeben, z. B. `"3D Druck" gesucht`, `"suche jemanden" "3D Drucker"`, `"3D drucken lassen"`,
   `"wer kann mir" "3D drucken"` → **Optionen anzeigen → Zustellen an: RSS-Feed** → Alert erstellen.
   Danach beim Alert auf das RSS-Symbol klicken und die Adresse kopieren. Alle Feed-Adressen untereinander in
   **ein** Secret: `GOOGLE_ALERTS_FEEDS`.
4. **E-Mail-Alarme, z. B. Kleinanzeigen** (wichtigste deutsche Quelle):
   - Am besten ein eigenes Gmail-Konto nur für das Radar anlegen, Zwei-Faktor-Anmeldung einschalten und unter
     **Google-Konto → Sicherheit → App-Passwörter** ein App-Passwort erzeugen.
   - Mit diesem Konto bei Kleinanzeigen nach „3D Druck“ suchen, **Anzeigentyp: Gesuche**, Umkreis wählen →
     **Suche speichern** mit E-Mail-Benachrichtigung. Genauso für „3D drucken“, „STL drucken“, „Ersatzteil drucken“.
   - In Gmail einen Filter anlegen: Absender enthält `kleinanzeigen` → Label **Lead-Radar** anwenden.
   - Secrets: `IMAP_HOST` = `imap.gmail.com`, `IMAP_USER` = die Gmail-Adresse, `IMAP_PASS` = das App-Passwort,
     optional `IMAP_FOLDER` (Standard `Lead-Radar`).
   - Der Bot liest nur die Mails der letzten 3 Tage in diesem Label, ändert nichts und übernimmt nur Titel und Link der Anzeigen.

Nach dem Speichern: **Actions → Lead-Radar sammeln → Run workflow**. Im Radar unter **Quellen** siehst du je Quelle
einen grünen oder roten Punkt.

## Sortierung „Beste Chance zuerst“

Jeder Lead bekommt einen Chancen-Wert: frisch (letzte Stunden), **noch keine Antworten**, Nähe (DACH), Bezahlung
erwähnt, passt in den P1S. Die Antwortzahl liefern Lemmy, Mastodon, Bluesky und die Foren. Bei Kleinanzeigen, Google
Alerts und Reddit-RSS steht „Antworten unbekannt“. Der Knopf **Noch unbeantwortet** zeigt nur Leads mit 0 Antworten.

## Reddit (wichtig)

Reddit hat freie Zugänge eingestellt: Seit 31.10.2026 nimmt Reddit keine neuen API-Anträge mehr an,
RSS-Feeds enden am 13.11.2026 und der restliche öffentliche API-Zugang endet im März 2027. Das Skript versucht Reddit
weiter, aber rechne damit, dass es scheitert. Reddit prüfst du über die Links unter „Manuelle Quellen“.
Falls du einen genehmigten Zugang bekommst: Client-ID und Secret unter **Settings → Secrets and variables → Actions**
als `REDDIT_CLIENT_ID` und `REDDIT_CLIENT_SECRET` speichern, das Skript nutzt sie automatisch.

## Gut zu wissen

- GitHub pausiert geplante Actions in Repos, die 60 Tage lang keine Aktivität hatten. Wenn du eine Mail
  „scheduled workflow disabled“ bekommst: im Actions-Tab auf **Enable workflow** klicken.
- Quellen ändern: Listen `SUBS_ALL`, `SUBS_SEARCH`, `LEMMY`, `MASTO` oben in `collect.py` (und `SOURCES` in `index.html`).
- Es werden nur öffentliche Feeds gelesen. Nichts wird gepostet, niemand wird angeschrieben.
