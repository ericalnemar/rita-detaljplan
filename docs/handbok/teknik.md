# Under huven

Den här sidan beskriver hur Rita Detaljplan fungerar tekniskt: hur planen är lagrad, hur databasen och utcheckningen
fungerar, var inställningar sparas och vad som händer när du ritar, kontrollerar och levererar. Den riktar sig till
GIS-samordnare, databasadministratörer och andra som vill förstå eller felsöka pluginet.

Du behöver inte läsa den för att använda pluginet.

> Vilka data som skickas vart och vad som är säkerhetsgranskat beskrivs i [Säkerhetsbeskrivning](../sakerhet.md).
> Hur du kör koden och testerna står i [Utveckling](../utveckling.md).

## Översikt

Pluginet är skrivet i Python och körs i QGIS 4. Koden är uppdelad i tre delar:

```
rita_detaljplan/
  controller.py    håller reglerna igång medan du ritar (hierarki, klippning, beteckningar)
  core/            logiken: datamodell, lagring, regler, kontroll, export, NGP-klient, arkivpaket
  gui/             dialoger, verktygsfält och kartverktyg
  planbeskrivning/ programmet Tagga planbeskrivning (kan köras utan QGIS)
```

Planen är vanliga QGIS-vektorlager. Allt du ritar går genom QGIS egen redigering, med redigeringsbuffert, ångra och
spara. Pluginet lyssnar på ändringarna i lagren och rättar dem efter reglerna.

## Datamodellen

Datamodellen följer Lantmäteriets **Nationella informationsspecifikation Detaljplan 4.1**. Kolumnerna heter samma
sak som fälten i Lantmäteriets JSON-schema (`spec/detaljplan-4.1.json`), så att exporten blir en direkt
översättning. Modellen definieras på ett ställe, `core/model.py`, och används för både GeoPackage och PostGIS.

### Tabellerna

| Tabell | Geometri | Innehåll |
|---|---|---|
| `detaljplan` | MultiPolygon | Planområdet med planens uppgifter: kommun, namn, syfte, status, plantyp, kvalitet. En rad per planområde. |
| `anvandning_yta` | MultiPolygon | Användningsområden. |
| `egenskap_yta` | MultiPolygon | Egenskapsområden, även sekundära (kolumnen `sekundar` = 1). |
| `egenskap_linje` | MultiLineString | Egenskapslinjer (utfartsförbud och stängsel). |
| `bestammelse` | – | Tilldelade planbestämmelser. **En rad per bestämmelse och yta.** |
| `beslutsinformation` | – | Beslut: instans, beslutstyp, diarienummer, datum, genomförandetid (i månader). |
| `dokument` | – | Handlingar: planbeskrivning, beslutshandlingar och planeringsunderlag. |
| `hjalppunkt`, `hjalplinje`, `hjalpyta` | MultiPoint, MultiLineString, MultiPolygon | Hjälplagren. Levereras aldrig. |
| `dp_meta` | – | Nyckel–värde-tabell med planens metadata: kommun, kommunkod, schemaversion, koordinatsystem och lås. Levereras aldrig. |

### Hur tabellerna hänger ihop

```
detaljplan (objektidentitet)
 ├── anvandning_yta.detaljplan      ┐
 ├── egenskap_yta.detaljplan        ├── ytorna
 ├── egenskap_linje.detaljplan      ┘
 ├── bestammelse.detaljplan
 │     bestammelse.tabell + bestammelse.yta  →  ytan bestämmelsen ligger på
 ├── beslutsinformation.detaljplan
 └── dokument.detaljplan
```

- Varje objekt har en **`objektidentitet`**, ett UUID som skapas automatiskt. Alla kopplingar mellan tabeller går
  via `objektidentitet`, aldrig via den interna radnumreringen (`fid`).
- En bestämmelse pekar ut sin yta med två kolumner: `tabell` (vilket ytlager) och `yta` (ytans `objektidentitet`).
- Kopplingarna är också uppsatta som **relationer** i QGIS-projektet, så att formulären kan visa till exempel en plans
  beslut.

### Varför bestämmelserna ligger i en egen tabell

I Lantmäteriets format är varje planbestämmelse ett eget objekt med egen geometri. En yta med beteckningen `e1 a2` blir
alltså två planbestämmelseobjekt med samma geometri.

I pluginet ligger geometrin bara en gång, i ytlagret, och bestämmelserna som rader i `bestammelse`. Det gör att en yta
kan ha flera bestämmelser och att geometrin bara behöver ritas och rättas på ett ställe. Vid exporten blir varje rad
i `bestammelse` ett planbestämmelseobjekt med ytans geometri.

Viktiga kolumner i `bestammelse`:

| Kolumn | Innehåll |
|---|---|
| `planbestammelsekatalogreferens` | Bestämmelsens UUID i Boverkets planbestämmelsekatalog. |
| `bestammelseformulering` | Texten, med ifyllda värden. |
| `avviker`, `ursprungligBestammelseformulering` | Om texten har anpassats, och i så fall katalogens ursprungliga text. |
| `bestammelsevarde` | Ifyllda värden som JSON, enligt schemats `variabelvarde`. |
| `beteckning`, `beteckningsindex` | Beteckningen på plankartan (till exempel `e1`) och dess siffra. |
| `ordning` | Ordningen bland ytans bestämmelser. Styr ordningen i beteckningen. |
| `motiv` | Motivet (planbestämmelsebeskrivningen). |

### Kolumner som bara pluginet använder

Några kolumner finns bara för att pluginet ska kunna rita och hålla ordning, och följer aldrig med i leveransen:
`tabell`, `yta`, `beteckning`, `beteckningsindex`, `bestammelsekod`, `anvandningsform`, `farg`, `symbol`, `avviker`,
`bestammelser`, `label_x`, `label_y`, `label_w`, `sekundar` och `ordning`.

- `beteckning`, `farg`, `symbol` och `anvandningsform` på ytorna räknas fram ur ytans bestämmelser varje gång de
  ändras. Symbologin och etiketterna läser dem.
- `label_x`, `label_y` och `label_w` sparar en text som du flyttat eller formats om med textverktyget. Tomt betyder
  automatisk placering.

### Obligatoriska fält

Tabellerna skapas **utan** `NOT NULL`-villkor i databasen. Obligatoriska fält kontrolleras i stället i formulären och
av kontrollen före leverans. Därför kan du alltid spara en plan som inte är färdig.

Tekniska fält (UUID, kopplingar, lägesmetod med mera) är dolda i formulären och fylls i av pluginet.

### Schemaversioner

Datamodellen har en versionssiffra, som sparas i planen. När du öppnar en plan med en äldre version uppgraderas den
automatiskt. Kolumner och tabeller läggs till, men ingenting tas bort.

| Version | Ändring |
|---|---|
| 3 | Ytor och bestämmelsetabell (äldsta version som kan uppgraderas). |
| 4 | Hjälplinjer. |
| 5 | Textens läge (`label_x`, `label_y`). |
| 6 | Bestämmelsernas ordning (`ordning`). |
| 7 | Textens bredd (`label_w`) och sekundär egenskapsgräns (`sekundar`). |
| 8 | PostGIS-schemat delas mellan flera planer. |
| 9 | Hjälpytor och hjälppunkter. |

## Lagring i GeoPackage

En plan i en GeoPackage är en vanlig `.gpkg`-fil (SQLite) med alla tabeller ovan. Den kan öppnas i vilket GIS-program
som helst.

- Koordinatsystemet måste vara ett av de SWEREF 99-system som specifikationen tillåter: **EPSG:3006–3018**.
- Geometrikolumnen heter `geom` och radnumreringen `fid`.
- Metadata ligger i `dp_meta`, till exempel `schema_version`, `spec_version`, `epsg`, `kommun` och `kommunkod`.
- QGIS-projektet (`.qgz`) sparas bredvid och pekar på filen.

## Lagring i PostGIS

### Ett delat schema för flera planer

I PostGIS lagras planerna i ett **schema** som kan delas av många planer. Alla planer i schemat ligger i samma
tabeller, och kolumnen **`plan`** talar om vilken plan en rad hör till.

```
schema "detaljplaner"
  dp_schema          schemaversion och koordinatsystem, gemensamt för hela schemat
  dp_meta            plan | key | value      (en rad per plan och nyckel, även låset)
  detaljplan         fid | plan | geom | objektidentitet | kommun | namn | …
  anvandning_yta     fid | plan | geom | …
  egenskap_yta       fid | plan | geom | …
  …                  samma tabeller som i en GeoPackage, var och en med kolumnen plan
```

Varje lager i QGIS är tabellen **filtrerad** på planens id, till exempel `"plan" = 'kv_larkan'`. Därför ser du bara
din plans rader, trots att tabellen innehåller flera planer.

- Varje tabell har ett index på `plan` och ett rumsligt index (GiST) på `geom`.
- Koordinatsystemet (SRID) sitter i geometrikolumnens definition och är därför **gemensamt för hela schemat**. Behöver
  du planer i olika SWEREF 99-zoner lägger du dem i olika scheman.
- Schema- och plan-id får bara innehålla gemener a–z, siffror och understreck, och måste börja med en bokstav.
  Schemanamnen `public`, `information_schema` och `pg_*` är inte tillåtna.

### Inloggning

Pluginet använder en av **QGIS sparade PostgreSQL-anslutningar**. Inloggningen sköts av QGIS, och pluginet sparar
inga lösenord.

Databasen måste ha tillägget PostGIS (`CREATE EXTENSION postgis`). Användaren behöver kunna skapa schema och tabeller
första gången, och sedan läsa, skriva och ta bort rader i schemats tabeller.

### När en plan skapas

1. Pluginet kontrollerar att databasen har PostGIS.
2. Finns schemat redan kontrolleras att det har samma koordinatsystem och att plan-id:t är ledigt. Ett schema med en
   äldre schemaversion uppgraderas.
3. Schemat och tabellerna skapas om de saknas (`CREATE … IF NOT EXISTS`). Misslyckas det för ett nytt schema tas det
   halvfärdiga schemat bort igen.
4. Planens metadata skrivs till `dp_meta`.

### Lägga till lager själv

Lägger du till ett av schemats lager med QGIS egen dialog saknar det filtret på `plan`. Då visas alla planers rader
blandade, och pluginet känner inte igen lagret som ett planlager. Använd alltid pluginets **Öppna**.

## Utcheckning och incheckning

Att rita direkt mot en databas över nätverket blir långsamt, eftersom reglerna läser om planens ytor efter varje
ändring. Därför arbetar du mot en lokal kopia.

```
  Databas (PostGIS)                         Din dator
  ─────────────────                         ─────────
  planen, skrivskyddad      ── checka ut ──▶  lås i dp_meta + lokal GeoPackage
                                              (du ritar här, i full fart)
  planen, uppdaterad        ◀── checka in ──  allt skrivs i en transaktion,
                                              låset släpps, kopian tas bort
```

### Skrivskydd

En plan som öppnas direkt från databasen är **skrivskyddad**. Annars skulle ändringar som gjorts utan utcheckning
skrivas över vid nästa incheckning.

### Låset

Låset är en rad i `dp_meta` med nyckeln `checkout`. Värdet är JSON:

```json
{"token": "3f9c…", "user": "anna", "host": "PLAN-PC-12", "since": "2026-10-29T09:14:02"}
```

- `token` är en slumpad nyckel som bara din utcheckning känner till.
- `user` och `host` är ditt användarnamn och datorns namn, och visas för den som försöker checka ut samma plan.
- När låset sätts låses `dp_meta` kort (`LOCK TABLE … IN EXCLUSIVE MODE`), så att två personer inte kan checka ut
  samma plan samtidigt.

### Checka ut

1. Låset sätts.
2. Alla planens tabeller kopieras till en ny GeoPackage i QGIS profilmapp, under `detaljplan_ngp/checkouts`. Kopian har
   samma `token` i sin egen `dp_meta`.
3. Planens lager i projektet pekas om till kopian. Lagren behåller sitt id, sin stil, sina formulär och relationer.

### Checka in

Incheckningen är **ett enda SQL-block** (`DO $$ … $$`) som körs i en transaktion:

1. Kontrollera att låset fortfarande har din `token`. Annars avbryts allt.
2. För varje tabell: ta bort planens rader (`DELETE … WHERE "plan" = …`) och lägg in de lokala raderna (`INSERT`,
   200 rader åt gången).
3. Ta bort låset.

Går något fel rullas allt tillbaka, och både låset och den lokala kopian finns kvar. Andra planers rader i samma
tabeller rörs aldrig.

Raderna får nya `fid` i databasen, eftersom kopians numrering börjar om på 1 och skulle krocka med andra planers rader.
Det gör ingenting, eftersom alla kopplingar går via `objektidentitet`.

### Kasta, bryta och återuppta

- **Kasta utcheckningen** tar bort låset och kopian utan att skriva något till databasen.
- **Bryta låset** tar bort låset oavsett vems det är. Den som hade planen utcheckad kan då inte checka in, eftersom
  den utcheckningens `token` inte längre finns.
- **Återuppta** efter en krasch: när du checkar ut letar pluginet efter en lokal kopia vars `token` fortfarande
  matchar låset i databasen, och erbjuder dig att fortsätta med den.

## Projektfilen, inställningar och cache

| Vad | Var | Innehåll |
|---|---|---|
| **Planens data** | GeoPackage eller PostGIS | Allt som levereras, plus `dp_meta`. |
| **Projektet** (`.qgz`) | Där du valde | Lagren, stilarna, formulären och relationerna. Markeringar av vilken grupp som är en plan och vilken plan som är aktiv, vilket lager som är vilken tabell, digitaliseringsläget, databasanslutningen, schemat och plan-id:t, och utcheckningens sökväg och nyckel. |
| **Inställningar** | QGIS användarprofil | Standardreferensskala, inställningar för leverans till NGP (miljö, adresser, namnet på autentiseringskonfigurationen), om tolkningsbestämmelser ska visas och inställningarna för teckenförklaringen. |
| **Inloggning till NGP** | QGIS autentiseringsdatabas | Nyckel och hemlighet, krypterade av QGIS. Pluginet sparar dem inte själv. |
| **Planbestämmelsekatalogen** | QGIS profilmapp, `detaljplan_ngp/` | Den senast hämtade katalogen. Saknas den används kopian som följer med pluginet. |
| **Utcheckade kopior** | QGIS profilmapp, `detaljplan_ngp/checkouts/` | Lokala kopior av utcheckade databasplaner. |

Inställningsnycklarna börjar med `detaljplan_ngp/`, eftersom pluginet tidigare hette Detaljplan NGP. Då fortsätter
äldre projekt och inställningar att fungera.

## Vad som händer när du ritar

Styrenheten (`controller.py`) kopplar sig till planlagrens signaler i QGIS: ett objekt läggs till, en geometri ändras,
ett objekt tas bort, redigeringen startar eller slutar. Vid varje ändring rättar den planen efter hierarkin:

- En ny användningsyta klipps mot planområdet och mot andra användningsytor.
- En ny egenskapsyta klipps mot användningsytorna och mot rätt användningsform.
- Tas en yta bort tas det som ligger på den bort, tillsammans med dess rader i `bestammelse`.
- Delas en yta delas det som ligger på den på samma ställe, och bestämmelserna kopieras med nya identiteter.

Alla ändringar görs i lagrens **redigeringsbuffert**. Inget skrivs till filen eller databasen förrän du sparar, och du
kan alltid kasta redigeringen.

### Toleranser

| Värde | Används till |
|---|---|
| 0,10 m | Hur långt en egenskap får sticka utanför sin användning. Samma som NGP tillåter. |
| 0,01 m² | Mindre överlapp räknas som avrundningsfel. |
| 5 m² | Användningsområden som överlappar med 5 m² eller mer ger fel. Mindre överlapp ger en varning (DP-Krav-0013). |
| 0,5 m | Ytor smalare än 0,5 m ger en avvikelse (DP-Krav-0014). |
| 0,5 m / 2,0 m | Minsta glapp mellan två användningsområden: ett glapp måste vara minst så brett, eller inte finnas alls. 0,5 m för planer påbörjade från 2022, 2,0 m för äldre (DP-Krav-0011/0012). |

### Beteckningarna

Beteckningen på en yta byggs av ytans bestämmelser:

- Användningar skrivs ihop: `B` + `C` = `BC`.
- Egenskaper skrivs med mellanrum: `e1 a2`.
- Indexerade beteckningar (`e#`, `f#` …) numreras per bokstav i hela planen. Samma bestämmelse, med samma text och
  värden, får samma siffra överallt. En annan bestämmelse får nästa lediga siffra.

## Symbologin

Stilen bygger på stilbiblioteket [Detaljplaner (Bfs 2020:6)](https://hub.qgis.org/styles/238/) (CC0).

- **Hierarkin i kartan:** varje lager ritar sin kantlinje med en *geometrigenerator* som tar bort de delar som redan
  ritas av ett högre lager. Därför syns bara den högsta gränsen där linjer sammanfaller, och en gemensam kant ritas en
  gång.
- **Lagerordningen:** användningens färg ligger underst och egenskapernas mönster ovanpå.
- **Blandningsläge:** användningen ritas med *Multiplicera*, så att grundkartan syns genom färgen.
- **Färger:** Boverkets katalog anger färgnamn (Gul, Blågrå …) men inga färgkoder. Vilken färg varje namn får styrs av
  `FARGER` i `core/symbology.py`.
- **Referensskala:** linjebredder och textstorlekar anges i millimeter på papper i referensskalan. När du byter
  referensskala byggs stilen om.

## Planbestämmelsekatalogen

Katalogen hämtas från Boverkets öppna API (`https://api.boverket.se/planbestammelsekatalogen`).

1. Pluginet läser katalogen från cachen i QGIS profilmapp, om den finns, är hel och inte är äldre än kopian som följer
   med pluginet.
2. Annars används kopian som följer med pluginet (`data/planbestammelsekatalog.json`).
3. **Uppdatera planbestämmelsekatalogen** hämtar hela katalogen, även upphörda bestämmelser, och sparar den i cachen.

Hämtningen går via QGIS nätverksinställningar, så proxy och certifikat från QGIS gäller.

## Exporten till Lantmäteriets format

Exporten (`core/export_ngp.py`) läser planen och skriver en `FeatureCollection` med mediatypen
`application/vnd.lm.detaljplan.v4+json`:

- **ett detaljplanobjekt** med planens uppgifter, plangeometri, beslutsinformation, planbeskrivning och underlag,
- **ett planbestämmelseobjekt** per rad i `bestammelse`, med ytans eller linjens geometri.

Under exporten

- delas **multigeometrier** upp, eftersom NGP inte godtar dem (DP-0004, DP-0018). Varje del blir en egen post.
- räknas **`reglerarAnvandningsbestammelse`** fram ur geometrin: vilka användningsbestämmelser en egenskap ligger på.
- skrivs **koordinaterna** som [öst, nord] med millimeters precision och ytterringarna **moturs**.
- utelämnas tomma fält, pluginets egna kolumner och hjälplagren.

Exporten ändrar ingenting i planen. **Importera leverans (JSON)** gör samma sak åt andra hållet.

## Leveransen till NGP

Klienten (`core/ngp_client.py`) följer Lantmäteriets specifikation för Uppdatering-API 1.1
(`spec/uppdatering-api-1.1.yaml`). En leverans går i fyra steg:

1. `POST /mottagning` – registrerar en mottagning för informationstypen `detaljplan`.
2. `POST /mottagning/{id}/forandringar` – registrerar en förändring med planens `objektidentitet`.
3. `POST …/forandringar/{objekt}/leverans` – laddar upp hela `FeatureCollection` från exporten.
4. `GET /mottagning/{id}` – frågar efter status var tredje sekund i upp till fem minuter, och hämtar
   valideringsrapporten.

| Miljö | Adress |
|---|---|
| Verifiering | `https://api-ver.lantmateriet.se/distribution/geodatakatalog/uppdatering/v1` |
| Produktion | `https://api.lantmateriet.se/distribution/geodatakatalog/uppdatering/v1` |

Inloggningen är OAuth 2 (`client_credentials`), med nyckel och hemlighet från QGIS autentiseringsdatabas. Anropen går via
QGIS nätverkslager och körs i en bakgrundsuppgift, så att QGIS inte låser sig.

> **Antaganden:** tokentjänstens adress och mediatypen v4 anges inte i specifikationen. Båda kan ändras i
> inställningarna. Klienten är testad mot en låtsasserver men inte mot Lantmäteriets miljö.

## Kontrollen

Kontrollen (`core/validation.py`) läser hela planen och ger en lista med avvikelser, var och en med regelkod,
allvarlighetsgrad (fel, varning eller att fylla i) och vilken yta den gäller. Den ändrar ingenting.

Reglerna och deras källor finns i [Regler från Lantmäteriets vägledning](../ngp-regler.md).

## Arkivpaketet

Arkivpaketet (`core/archive.py`) skapar en mapp med `metadata/PREMIS.xml`, `schemas/` och `content/`. Planens
GeoPackage kopieras med SQLites backup-funktion, så kopian blir konsekvent även om QGIS har filen öppen. Kontrollsummorna
är SHA-256.

Mer om modelleringen och avvägningarna finns i [Revision av arkivpaketet](../arkivpaket-revision.md) och
[Kända begränsningar](../kanda-begransningar.md).
