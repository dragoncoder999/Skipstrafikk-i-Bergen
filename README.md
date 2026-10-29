# Skipstrafikk rundt Bergen

Viser skipstrafikken rundt Bergen på et kart i sanntid og anslår CO₂-utslippene fra hvert skip. Posisjonene kommer fra BarentsWatch sitt åpne AIS-API. Utslippene er grove anslag, se kommentarene i `emissions.py`.

## Kjøre lokalt

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Nøklene legges i `nokler.env`. Filen lastes aldri opp til GitHub.

For å samle inn historikk lokalt kjører du dette i en egen terminal:

```bash
python collector.py
```

Uten Turso-nøkler i `nokler.env` lagres dataene i `data/skipstrafikk.db`.

Tester:

```bash
python -m unittest
```

## Innsamling i skyen

Gratisversjonen av Render sletter lokale filer hver gang tjenesten starter på nytt. Derfor samles dataene inn av GitHub Actions hvert 10. minutt og lagres i Turso, som er en SQLite-database i skyen. Appen på Render leser derfra.

### 1. Turso

1. Opprett en gratis konto på https://turso.tech.
2. Lag en database. Velg en region i Europa.
3. Kopier databasens URL. Den begynner med `libsql://`.
4. Lag et token med lese- og skrivetilgang.
5. Legg begge inn i `nokler.env` som `TURSO_DATABASE_URL` og `TURSO_AUTH_TOKEN` for å teste lokalt.

### 2. GitHub

1. Lag et **offentlig** repo. GitHub Actions er gratis for offentlige repoer.
2. Last opp koden.
3. Gå til *Settings → Secrets and variables → Actions* og legg inn fire repository secrets:
   - `BARENTSWATCH_CLIENT_ID`
   - `BARENTSWATCH_CLIENT_SECRET`
   - `TURSO_DATABASE_URL`
   - `TURSO_AUTH_TOKEN`
4. Gå til fanen *Actions*, velg «Samle inn skipsdata» og trykk *Run workflow* for å teste. Etter det går jobben av seg selv hvert 10. minutt.

### 3. Render

1. Lag en ny tjeneste fra repoet. `render.yaml` beskriver oppsettet.
2. Legg inn de samme fire nøklene som miljøvariabler.

### Verdt å vite

- GitHub kan forsinke eller hoppe over planlagte jobber når det er mye trafikk. Hull i innsamlingen telles ikke med, så summene blir litt for lave. Siden «Utslipp over tid» viser hvor mange timer som har data.
- I offentlige repoer slår GitHub av planlagte jobber etter 60 dager uten aktivitet i repoet. Da må jobben slås på igjen i *Actions*-fanen.
- Data eldre enn 30 døgn slettes. Grensen settes i `settings.py`.

## Filer

| Fil | Innhold |
|---|---|
| `app.py` | Startpunkt, navigasjon og sidepanel |
| `views/kart.py` | Kart i sanntid med varmekart |
| `views/utslipp.py` | Utslipp per time og døgn |
| `views/om.py` | Forklaring av beregningen, forutsetninger og usikkerhet |
| `settings.py` | Område, intervaller og andre innstillinger |
| `ais_client.py` | Innlogging og henting fra BarentsWatch |
| `ship_types.py` | Gruppering av AIS-skipstyper |
| `emissions.py` | Utslippsberegningen og forutsetningene for den |
| `storage.py` | Lagring i SQLite eller Turso |
| `collector.py` | Innsamling av posisjoner |
| `.github/workflows/collect.yml` | Planlagt innsamling i GitHub Actions |
