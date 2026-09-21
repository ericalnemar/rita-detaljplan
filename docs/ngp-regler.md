# Regler från Lantmäteriets vägledning (underlag för validering och export)

Källa: *Vägledning till Nationell informationsspecifikation Detaljplan* och specifikationen v4.1.
Gäller steg 3 (validering) och steg 4 (export). "Stoppar" = leveransen stoppas av NGP, "Varnar" = varning.

## Geometri
- **Inga multigeometrier i leveransen** (DP-0004, DP-0018, stoppar). `plangeometri` och `bestammelsegeometri`
  är listor: exportera varje del av ett multipart-objekt som en egen post. GeoPackage-lagren är Multi* och det är
  exportens uppgift att dela upp dem.
- Bestämmelsegeometrier ska ligga innanför och tillsammans täcka hela planområdet, med 10 cm tolerans åt båda håll
  (DP-0002, DP-0003, stoppar). Undantag: allmän plats med enskilt huvudmannaskap.
- Gränslinjer får inte korsa sig själva (DP-Krav-0018, stoppar).
- Bestämmelser närmare än 0,5 m (planer påbörjade efter 2021) / 2 m (före 2022) från varandra (DP-Krav-0011/0012,
  varnar). Överlapp mindre än 5 m² eller onormalt smala (DP-Krav-0013/0014, varnar).
- Osäkert läge får inte anges (DP-0010, stoppar). Vertikal avgränsning endast för ytor (DP-0015/0016, stoppar).

## Hierarki: planområde, användning, egenskap (pluginets regler, se `core/rules.py` och `core/assignments.py`)
- Användningsytor ska ligga inom planområdet (beskärs) och får inte överlappa varandra (DP-0003, DP-Krav-0013).
- Hela planområdet ska ha en användning (DP-0002): täckningen följs i verktygsfältet och kontrolleras vid avslut.
- En yta kan ha flera bestämmelser. Varje bestämmelse är ett eget planbestämmelseobjekt (egen `objektidentitet`)
  som vid leverans får ytans geometri; ytor med flera delar delas upp i en geometri per del.
- Schemat har `reglerarAnvandningsbestammelse` (UUID för användningsbestämmelser) på egenskapsbestämmelser. Den
  lagras inte utan **härleds vid export**: alla användningsbestämmelser på de användningsytor som egenskapsytan ligger
  på, eller som egenskapslinjen ligger på.
- En egenskapsyta ska ligga helt inom användningsytorna (tolerans 10 cm, beskärs annars); en egenskapslinje ska ligga
  på en användningsyta. Annars tas objektet bort direkt vid ritning.
- Användningsformen (allmän plats, kvartersmark, vattenområde) ska stämma mellan egenskap och användning. En
  användningsyta kan inte vara två olika användningsformer.
- Planområdesegenskaper ("Planområdet") får ligga på vilken användning som helst.
- Alla pågående användningsbestämmelser är ytor. Egenskaper finns i katalogen som yta, linje och punkt, men
  pluginet använder endast ytor, samt linjer för utfartsförbud och stängsel: punktbestämmelser saknar funktion i
  planen och är inte valbara.

## Bestämmelser (planbestämmelsekatalogen)
- `bestammelseformulering` = katalogens exakta text med variablerna kvar (`[höjd:decimaltal]`). Värdena skickas som
  `bestammelsevarde` i samma ordning (DP-0022, stoppar): saknas värde, eller anges värde utan variabel.
- Frivillig variabel är bara `[text:text]`; utgår den ur formuleringen anges inget värde för den.
- Decimaltal kräver `vardetyp` (min/max/exakt) och `enhet` (DP-0009, stoppar). Fler än ett decimaltal på en
  bestämmelse varnar (undantag: lutning, som har två).
- Tekniska anläggningar (`DP_KM_E2`): formulering och motiv ska vara exakt "Tekniska anläggningar"
  (DP-0019/0020/0021, stoppar).
- Formuleringen ska stämma med katalogen, annars varnar NGP (DP-Krav-0017).
- Övergångsbestämmelser kan inte levereras (finns inte i schemat).

## Planen
- Endast en detaljplan med status laga kraft per yta (DP-0001).
- Laga kraft kräver: beteckning, planbeskrivning, minst en bestämmelse, kvalitetsbeskrivning för plan och
  bestämmelse, beslutsinformation med diarienummer, beslutstyp, beslutshandling (plankarta), datum antagande,
  datum laga kraft, genomförandetid och när den startar (DP-0005, DP-0014, DP-0017).
- Påbörjad efter 2021-12-31: `datumPaborjat`, lägesbestämningsmetod i plan och tidpunkt för lägesbestämning är
  obligatoriska, och varje bestämmelse ska ha planbestämmelsebeskrivning (motiv) vid laga kraft (DP-0011/0012).
- Kommunnamnet ska stämma och planen ligga i leverantörens kommun.
- Historik får inte finnas i leveransen (BAS-005).

## Leveransflöde (Uppdatering-API)
1. `POST /mottagning` (`informationstyp: detaljplan`, `provider: <kommunkod>`)
2. `POST /mottagning/{id}/forandringar` (objektidentitet + `leverans`/`radering`)
3. `POST …/forandringar/{objektidentitet}/leverans` med `Content-Type: application/vnd.lm.detaljplan.v4+json`
4. Följ status (`mottagen` → `validerad`/`valideringsfel` → `publicerad`) och hämta valideringsrapporten.

Verifieringsmiljö: `api-ver.lantmateriet.se`, produktion: `api.lantmateriet.se`. Nycklar hanteras i API-portalen
(`apimanager-ver.lantmateriet.se`). Se `spec/uppdatering-api-1.1.yaml`.

## Boverkets planbestämmelsekatalog (API v2)
- `https://api.boverket.se/planbestammelsekatalogen`, öppet och utan nyckel.
- `/release` (lista), `/release/full/platt/{id}` (hela katalogen, ca 13 MB), `/vd/symbol/…` (symboler),
  `/vd/farg`, `/faltbeskrivning`.
- Symboler och färger används i steg 6 (plankartans teckenförklaring).
- Källhänvisning krävs: "Källa: Boverket, Planbestämmelsekatalogen".
