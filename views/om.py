"""Page: how the emission estimate is calculated, its assumptions and uncertainty.

Numbers in the text are taken from emissions.py and settings.py, so the page
stays correct if the assumptions are changed there.
"""

import pandas as pd
import streamlit as st

import emissions as em
import settings
from formatting import num

st.title("Om beregningen")
st.markdown(
    "Tallene i denne appen er **grove anslag**, ikke målinger. Ingen skip rapporterer "
    "drivstofforbruk eller utslipp gjennom AIS. Vi vet bare hvor skipet er, hvor fort det går, "
    "hvilken type skip det er og hvor langt det er. Resten bygger på forutsetninger, "
    "som er beskrevet på denne siden."
)

st.header("Kort fortalt")
st.markdown(
    f"""
1. **Posisjon og fart** hentes fra BarentsWatch sitt åpne AIS-API omtrent hvert minutt.
2. **Motorkraft og designfart** slås opp i en tabell ut fra skipstype og lengde.
3. **Andelen av motorkraften som brukes** regnes med propelloven:
   (fart / designfart)³. Andelen er aldri over 100 % og aldri under {num(em.MIN_LOAD * 100)} %.
4. **Ligger skipet nesten stille**, under {num(em.STATIONARY_SPEED)} knop, regnes bare
   hjelpemotorene med, med en fast effekt for hver skipstype og størrelse. Unntaket er
   cruiseskip, som regnes som tilkoblet landstrøm og uten utslipp når de ligger stille.
5. **Drivstoff** regnes med {em.SFOC_MAIN} gram per kilowattime for hovedmotoren og
   {em.SFOC_AUX} gram for hjelpemotorene.
6. **CO₂**: ett tonn drivstoff gir {num(em.CARBON_FACTOR, 3)} tonn CO₂. Det er faktoren for
   marin diesel. Langs norskekysten må skip bruke drivstoff med lite svovel, så tungolje
   er lite brukt.
"""
)

ex = em.estimate_from_power(installed_kw=8000, design_speed=14, speed=10, aux_kw=0)
with st.expander("Regneeksempel"):
    st.markdown(
        f"""
Et skip med 8000 kW motor og designfart 14 knop går i 10 knop:

- Andel av motorkraften: (10 / 14)³ = {num(em.load_factor(10, 14) * 100, 1)} %
- Motorkraft i bruk: 8000 kW × {num(em.load_factor(10, 14), 3)} = **{num(ex.main_kw)} kW**
- Drivstoff: {num(ex.main_kw)} kW × {em.SFOC_MAIN} g/kWh = **{num(ex.fuel_kg_per_h)} kg i timen**
- CO₂: {num(ex.fuel_kg_per_h)} kg × {num(em.CARBON_FACTOR, 3)} = **{num(ex.co2_kg_per_h / 1000, 2)} tonn i timen**
"""
    )

st.header("Hvor motordataene kommer fra")
st.markdown(
    f"""
Motorkraft, designfart og hjelpemotoreffekt er gjennomsnitt for hver skipstype og
størrelse fra **IMOs tredje klimagass-studie** (Third IMO GHG Study 2014), som bygger på
verdensflåten i 2012. Effekten på hjelpemotorene er regnet om fra det årlige
drivstofforbruket i studien.

IMO oppgir størrelse i dødvekttonn, bruttotonn eller containerkapasitet, mens AIS bare
gir lengden. Hver størrelsesklasse er derfor oversatt til et lengdeintervall. Denne
oversettelsen er vår egen og gir ekstra usikkerhet.

IMO-tallene gjelder skip i det internasjonale skipsregisteret, som stort sett er over
100 bruttotonn. For fartøy opp til {em.SMALL_VESSEL_LENGTH} meter bruker vi egne, grove anslag.
"""
)

rows = []
for category, profile in em.PROFILES.items():
    lower = 0
    for row in profile["rows"]:
        rows.append({
            "Skipstype": category,
            "Lengde": f"{lower:.0f}–{row.max_length:.0f} m" if row.max_length != em.INF
                      else f"over {lower:.0f} m",
            "Motorkraft (kW)": row.main_kw,
            "Designfart (knop)": row.design_speed,
            "Hjelpemotorer ved kai (kW)": row.aux_kw,
            "Kilde": row.source,
        })
        lower = row.max_length
with st.expander("Hele tabellen"):
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={
            "Motorkraft (kW)": st.column_config.NumberColumn(format="localized"),
            "Designfart (knop)": st.column_config.NumberColumn(format="localized"),
            "Hjelpemotorer ved kai (kW)": st.column_config.NumberColumn(format="localized"),
        },
    )

st.header("Summering over tid")
st.markdown(
    f"""
Omtrent hvert {settings.COLLECT_MINUTES}. minutt lagres et øyeblikksbilde av alle skipene i
området. Hvert skip får utslippet sitt for tiden siden forrige bilde. Summene per time og
døgn er summen av disse bildene.

- Posisjoner som er eldre enn {settings.MAX_POSITION_AGE_MINUTES} minutter tas ikke med,
  fordi skipet trolig har forlatt området eller slått av AIS.
- Er det gått mer enn {settings.MAX_GAP_MINUTES} minutter siden forrige bilde, telles ikke
  tiden imellom. Hull i innsamlingen gir derfor for lave summer.
- Skip som går raskt gjennom området mellom to bilder, blir ikke med.
- Data eldre enn {settings.KEEP_DAYS} døgn slettes.
"""
)

st.header("Hvor usikkert er anslaget?")
st.markdown(
    """
**For ett enkelt skip** kan anslaget bomme med en faktor på to eller mer. Motoren,
skroget og drivstoffet til akkurat det skipet er ukjent, og tabellen gir bare et
gjennomsnitt for skip av samme type og omtrent samme størrelse.

**For summen over mange skip** jevner tilfeldige feil seg delvis ut, men noen feil går
systematisk samme vei.

Anslaget blir trolig **for høyt** fordi

- mange ferjer og hurtigbåter rundt Bergen går helt eller delvis på batteri eller gass,
  mens vi regner alle som dieseldrevne
- skip som ligger på landstrøm, regnes som om hjelpemotorene går. Unntaket er cruiseskip:
  Bergen Havn har et stort landstrømanlegg, og fra 2026 skal alle cruiseskip bruke
  landstrøm når de ligger til kai. Cruiseskip som ligger stille, regnes derfor uten
  utslipp. Det kan gi litt for lave tall for cruiseskip som ligger for anker.

Anslaget blir trolig **for lavt** fordi

- hjelpemotorer og kjeler under fart ikke regnes med
- det åpne AIS-API-et ikke har med fiskefartøy under 15 meter og fritidsbåter under 45 meter
- hull i innsamlingen ikke telles med

I tillegg kommer at

- IMO-tallene er gjennomsnitt for verdensflåten i 2012, ikke for kystflåten i dag
- propelloven er en forenkling. Vær, strøm, last og begroing på skroget er ikke med.
- AIS-kodene for skipstype er grove. Et lasteskip kan for eksempel være alt fra en liten
  brønnbåt til et stort bulkskip.

Tallene egner seg best til å **sammenligne**, for eksempel mellom skipstyper, tider på
døgnet eller områder. De egner seg dårlig som et presist mål på de faktiske utslippene.
"""
)

st.header("Offisielle tall")
st.markdown(
    """
**Kystverket** har siden 2012 publisert egne utslippstall for skipstrafikk basert på AIS
gjennom **Havbase**. Havbase er i ferd med å bli faset ut og erstattes av **MarU**
(Maritim utslippsmodell). MarU bruker skipsspesifikke data fra skipsregistre og metoden
fra IMOs fjerde klimagass-studie, og regner også med batteri og landstrøm.

Tallene i denne appen er bare et grovt anslag. Trenger du pålitelige tall, bruk
Kystverkets: [kystverket.no/klima-og-barekraft/maru](https://www.kystverket.no/klima-og-barekraft/maru/)
"""
)

st.header("Datakilder")
area = settings.AREA
st.markdown(
    f"""
- **Skipsposisjoner:** BarentsWatch sitt åpne AIS-API
  ([developer.barentswatch.no](https://developer.barentswatch.no/docs/AIS/live-ais-api)).
- **Motordata:** Third IMO GHG Study 2014, tabell med gjennomsnitt for 2012.
- **Område:** breddegrad {num(area['min_lat'], 2)}–{num(area['max_lat'], 2)} og
  lengdegrad {num(area['min_lon'], 2)}–{num(area['max_lon'], 2)}.
- **Kildekode:** [github.com/dragoncoder999/Skipstrafikk-i-Bergen](https://github.com/dragoncoder999/Skipstrafikk-i-Bergen)
"""
)
