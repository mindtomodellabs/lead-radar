# Lead-Radar rund um die Uhr (GitHub, kostenlos)

Dieses Paket macht zwei Dinge:

- **GitHub Action** (`collect.py`): ruft alle 30 Minuten Reddit, Lemmy und Mastodon ab und schreibt die Anfragen in `leads.json`.
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

## Reddit (wichtig)

Reddit hat freie Zugänge eingestellt: neue API-Zugänge gibt es nur noch nach Antrag (seit Nov. 2025),
RSS-Feeds enden am 13.11.2026, und die API soll künftig kostenpflichtig werden. Das Skript versucht Reddit
weiter, aber rechne damit, dass es scheitert. Reddit prüfst du über die Links unter „Manuelle Quellen“.
Falls du einen genehmigten Zugang bekommst: Client-ID und Secret unter **Settings → Secrets and variables → Actions**
als `REDDIT_CLIENT_ID` und `REDDIT_CLIENT_SECRET` speichern, das Skript nutzt sie automatisch.

## Gut zu wissen

- GitHub pausiert geplante Actions in Repos, die 60 Tage lang keine Aktivität hatten. Wenn du eine Mail
  „scheduled workflow disabled“ bekommst: im Actions-Tab auf **Enable workflow** klicken.
- Quellen ändern: Listen `SUBS_ALL`, `SUBS_SEARCH`, `LEMMY`, `MASTO` oben in `collect.py` (und `SOURCES` in `index.html`).
- Es werden nur öffentliche Feeds gelesen. Nichts wird gepostet, niemand wird angeschrieben.
