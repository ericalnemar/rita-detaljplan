# Säkerhetsbeskrivning

Det här dokumentet är till för dig som ska bedöma om Rita Detaljplan kan användas i en organisation, till exempel en
kommuns IT-säkerhetsfunktion. Det beskriver vad pluginet gör, vilka data som rör sig vart, vad som är granskat och vad
som inte är det. Rapportera säkerhetsbrister enligt [SECURITY.md](../SECURITY.md).

**Omfattning:** version 0.1.44, genomgången 2026-10-02.

## Läs det här först: vad dokumentet är och inte är

- Pluginet är skrivet med AI-stöd och underhålls av en enskild person på fritiden. Det är en experimentell
  utvecklingsversion.
- Genomgången nedan är en **statisk kodgranskning** (läsning och sökning i källkoden, utförd av underhållaren med AI-stöd).
  Det är **ingen oberoende säkerhetsgranskning**, inget penetrationstest och ingen beroendeanalys med verktyg.
- Testsviten (se `tests/`) kontrollerar att funktionerna beter sig rätt och att leveransen följer Lantmäteriets scheman.
  Den bevisar inte att koden är säker.
- En organisation som har krav på säkerhetsgranskning bör låta en oberoende person gå igenom koden. Se
  [Rekommendationer](#rekommendationer-för-en-organisation).

## Sammanfattning

| Område | Bedömning |
| --- | --- |
| Körning av kod från indata (`eval`, `exec`, `subprocess`, `pickle`) | Förekommer inte i pluginets kod |
| Beroenden utanför QGIS och Pythons standardbibliotek | Inga (se [Beroenden](#beroenden)) |
| Nätverksmål | Tre: Boverket, Lantmäteriet (verifiering/produktion) och en adress som användaren själv anger |
| Hemligheter | Sparas inte av pluginet, utan i QGIS autentiseringsdatabas |
| Databasåtkomst | Via QGIS sparade anslutningar, med användarens egna databasrättigheter |
| Öppna fynd | 4 informativa (se [Fynd](#fynd)). Ett lågt fynd är åtgärdat i 0.1.44 |
| Distribution | Osignerade zip-filer och en pluginkälla som pekar på GitHub (se [Leveranskedja](#leveranskedja-och-distribution)) |

## Vad pluginet är och vilka rättigheter det har

Pluginet är ett Python-plugin i QGIS (QGIS 4.0 eller senare). Det körs i QGIS egen process med **samma rättigheter som
den inloggade användaren**. QGIS har ingen sandlåda för plugin, så detta gäller varje QGIS-plugin, oavsett hur det är
skrivet. Pluginet gör inget vid installation utom att QGIS importerar modulen; ingen kod körs från installationsskript.

Omfång: cirka 13 000 rader Python under `rita_detaljplan/` (utan tester).

## Dataflöden

| Vad | Varifrån | Vart | Hur |
| --- | --- | --- | --- |
| Planbestämmelsekatalogen | Boverkets öppna API (`api.boverket.se`) | Cache i användarens QGIS-profil | Bara när användaren väljer *Uppdatera planbestämmelsekatalogen*. Via QGIS nätverksstack |
| Planleverans (JSON) | Lokal plan | Lantmäteriets API (`api-ver.` eller `api.lantmateriet.se`), eller en adress användaren anger | Bara när användaren väljer *Leverera*. Via QGIS nätverksstack, https |
| Planleverans (fil) | Lokal plan | En JSON-fil som användaren pekar ut | Skrivs av användaren själv |
| Importerad leverans | JSON-fil som användaren väljer | Ny lokal plan | Läses som JSON, tolkas av `core/import_ngp.py` |
| Plandata | Lokal GeoPackage eller PostGIS-schema | QGIS lager | GDAL/SQLite respektive QGIS PostgreSQL-leverantör |

Nätverksanrop finns bara i `core/ngp_client.py` och `core/catalog_store.py`. Pythons `urllib` används enbart för att tolka
och kontrollera adresser (`urllib.parse`), inte för att hämta något. Pluginet skickar ingen telemetri, och det finns
inga andra nätverksmål i koden.

## Hemligheter och inloggning

- **Lantmäteriets nyckel och hemlighet** sparas inte av pluginet. Användaren väljer en autentiseringskonfiguration i QGIS
  autentiseringsdatabas (typen *Grundläggande autentisering*). Pluginet sparar bara konfigurationens id i QGIS
  inställningar (`QgsSettings`), tillsammans med miljö och adresser.
- **Åtkomsttoken** hämtas med `client_credentials`, hålls bara i minnet i klientobjektet och sparas inte på disk.
  Den förnyas vid 401.
- **Databaslösenord** hanteras av QGIS egna PostgreSQL-anslutningar. Pluginet frågar aldrig efter lösenord och väljer en
  befintlig anslutning ur QGIS lista.
- **Projektfiler (.qgz)** får av pluginet anslutningens *namn*, schema, plan-id, ett utcheckningslås (slumpmässig
  token) och, efter en leverans, mottagningens och planens id hos Lantmäteriet samt miljöns namn. Pluginet lägger inga
  lösenord eller nycklar i projektet. Hur en PostgreSQL-lagerkälla lagrar inloggning i projektfilen styrs av QGIS, inte
  av pluginet: använd en autentiseringskonfiguration. Leveransinställningarna (adresser, vald autentisering) ligger i
  användarens profil, inte i projektet, så en delad projektfil kan inte styra om inloggningsuppgifterna till en annan
  adress. Se fynd 5.
- Adresser till API:et och tokentjänsten måste börja med `https://`. Bara `http://` mot `localhost` och `127.0.0.1`
  tillåts (för tester). Omdirigeringar följs inte vid leverans.
- QGIS egna inställningar för proxy och certifikat gäller, så TLS-kontrollen är QGIS standard. Pluginet stänger aldrig av
  certifikatkontroll och använder inte certifikatfästning.

## Filer

Pluginet skriver:

- planens GeoPackage och projektfil (`.qgz`) i den mapp användaren väljer,
- en lokal arbetskopia (GeoPackage) vid utcheckning från PostGIS,
- katalogcachen `planbestammelsekatalog.json` i QGIS-profilen (skrivs först till en `.tmp`-fil och byter sedan namn),
- leveransfilen som användaren själv väljer att spara,
- inställningar via `QgsSettings`.

Pluginet raderar filer bara i en situation: den lokala arbetskopian när en plan checkas in eller utcheckningen hävs
(`core/checkout.py`).

## Databaser

**GeoPackage** nås med Pythons `sqlite3` och GDAL. Värden skickas som bundna parametrar. Tabellnamn kommer från pluginets
egen modell, inte från indata.

**PostGIS** nås med QGIS anslutningsobjekt (`executeSql`). SQL byggs som text, eftersom gränssnittet inte har bundna
parametrar. Skydden är:

- identifierare (schema, plan-id) valideras mot `^[a-z][a-z0-9_]{0,62}$` och citeras med dubbla citattecken
  (`quote()`), och schemat får inte vara `public`, `information_schema` eller börja med `pg_`,
- textvärden skrivs som SQL-literaler med fördubblade enkla citattecken (`literal()`),
- tal skrivs via `int()` och `float()`,
- ett dollarcitat i incheckningsblocket väljs så att det inte förekommer i innehållet.

Det här är korrekt förutsatt att databasen har `standard_conforming_strings = on` (förvalt sedan PostgreSQL 9.1). Se fynd 3.

Pluginet kör `DROP SCHEMA ... CASCADE` bara för att städa bort ett schema som just skapades i samma anrop och där
skapandet misslyckades halvvägs. Det rör aldrig ett schema som fanns innan.

**Behörighet:** pluginet har ingen egen åtkomstkontroll. Vem som kan läsa och ändra planer avgörs helt av
databasrollen i QGIS-anslutningen. Utcheckningens lås (se fynd 2) är en samarbetsmekanism för att undvika samtidig
redigering, inte en säkerhetsfunktion.

## Beroenden

Pluginet importerar bara QGIS (`qgis`, `osgeo`/GDAL) och Pythons standardbibliotek (bland annat `json`, `re`, `sqlite3`,
`uuid`, `getpass`, `platform`, `urllib.parse`). Det installerar inga paket med `pip` och har ingen `requirements`-fil.
Uppdateringar av beroenden följer därför QGIS egna. En medföljande kopia av planbestämmelsekatalogen och kommunlistan
ligger som JSON i `rita_detaljplan/data/` (cirka 0,9 MB, genererad av skript i `tools/`).

Testerna kräver bara QGIS och Pythons `unittest`.

## Leveranskedja och distribution

- Koden ligger öppet på GitHub under GPL-2.0-eller-senare. Commits och taggar är **inte signerade**.
- Release-filen (`rita_detaljplan-<version>.zip`) byggs reproducerbart av `tools/build_zip.py` (samma innehåll ger samma
  zip), men det publiceras **ingen kontrollsumma eller signatur** och det finns **ingen automatisk bygg- eller
  säkerhetskontroll (CI)** i repot.
- Pluginkällan (`plugins.xml`) läses från `main` på GitHub. Den som kan skriva till repot kan alltså få kod installerad hos
  alla som uppdaterar via pluginkällan. Skyddet är kontot på GitHub (rekommendation: tvåfaktorsinloggning och skyddad
  `main`).
- Pluginet är **inte** publicerat i QGIS officiella pluginarkiv och har därför inte genomgått dess granskning.

## Fynd

Allvarlighetsgrad: *låg* = kan missbrukas men med liten effekt, *information* = bra att känna till, ingen åtgärd krävs.

### 1. Ofiltrerad text i dialogrutornas rika text (låg, åtgärdad i 0.1.44)

Text från Boverkets katalog (`bestammelse_dialog.py`), planens namn och API-adressen (`delivery_dialog.py`,
`ngp_dialog.py`) och kontrollistans rader (`plan_info_dialog.py`) sätts in i dialogrutor som tolkar Qts rika text
(`setHtml`, `RichText`) utan att specialtecken först kodas.

*Effekt:* En manipulerad katalogpost (om Boverkets API eller anslutningen dit skulle vara komprometterad) eller ett
planamn med HTML kan ändra hur texten i en dialogruta ser ut, till exempel dölja eller förvränga bekräftelsetexten vid
leverans. Qts rika text kör inga skript och hämtar inga fjärrresurser, så ingen kod kan köras den vägen.
*Åtgärd:* texten kodas nu med `html.escape` (`gui/richtext.py`) innan den läggs in i dessa dialogrutor, och det finns
tester för det. Qt:s `QLabel` tolkar som standard även text som ser ut som HTML (automatiskt textformat). Alla
andra textfält har inte gåtts igenom ett och ett, så det kan finnas fler ställen med samma beteende och samma låga effekt.

### 2. Låset avslöjar användarnamn och datornamn (information)

Vid utcheckning från PostGIS skrivs operativsystemets användarnamn och datorns namn (`getpass.getuser()`,
`platform.node()`) i planens metadatatabell, så att andra kan se vem som har planen. Det syns för alla som kan läsa
schemat. Räkna det som personuppgift i er bedömning.

### 3. SQL byggs som text (information)

Se avsnittet [Databaser](#databaser). Skyddet bygger på validerade identifierare och korrekt citering. Det finns
enhetstester för `quote()` och `literal()`, men inget test med avsiktligt illasinnade indata mot en riktig databas. Mönstret är mer sårbart för framtida ändringar än bundna parametrar skulle vara.

### 4. Egen API-adress (information)

I inställningarna kan användaren välja *Egen adress* i stället för Lantmäteriets miljöer. Nyckel och hemlighet från den
valda autentiseringskonfigurationen skickas då till den tokentjänst som användaren själv har skrivit in. Det är avsiktligt
(för test och andra miljöer) men innebär att en vilseledd användare kan skicka sina uppgifter till fel adress. Adressen
måste vara `https://`.

### 5. Leveransmottagning lagras i projektfilen (information)

Efter en leverans sparas mottagningens id, planens id och miljöns namn i projektfilen, så att nästa leverans uppdaterar
samma mottagning. En manipulerad projektfil skulle kunna peka en senare leverans mot ett annat mottagnings-id. Om det
lyckas avgörs av Lantmäteriets behörighetskontroll mot användarens nyckel; det har inte testats här. Öppna därför inte
projektfiler från okända källor och leverera, som alltid, först till verifieringsmiljön.

## Det som inte omfattas

- Ingen dynamisk analys, ingen fuzzning och inget penetrationstest.
- Ingen automatisk beroende- eller sårbarhetsskanning (se [Beroenden](#beroenden): det finns inga externa beroenden att
  skanna, men QGIS, GDAL och PostgreSQL ligger utanför pluginets kontroll).
- QGIS och GDAL:s egna sårbarheter, till exempel vid inläsning av hotfyllda filer, bedöms inte här.
- Dataskydd (GDPR) bedöms inte, förutom att fynd 2 pekar på att användarnamn kan lagras.
- Tillgänglighet, drift och support.

## Rekommendationer för en organisation

1. **Låt en oberoende person granska koden** innan produktionsanvändning. Börja med `core/ngp_client.py`,
   `core/storage.py`, `core/checkout.py`, `core/catalog_store.py` och `core/settings.py`. Det är där nätverk,
   inloggning och databas finns.
2. **Installera en fast, granskad version** centralt (zip-filen), och använd inte den öppna pluginkällan i
   produktionsmiljön. Jämför filens innehåll med taggen i repot innan den godkänns.
3. **Börja i Lantmäteriets verifieringsmiljö** (`api-ver`), inte i produktion, och kontrollera leveransen där först.
4. **Begränsa databasrollen** som används i PostGIS-anslutningen till det schema och de tabeller som behövs, eftersom
   pluginet inte har någon egen behörighetskontroll.
5. **Bestäm vem som äger underhållet.** En enskild frivillig underhållare är en verksamhetsrisk. Ett kommunalt samarbete
   eller en organisation som tar över repot minskar den.
6. **Skydda GitHub-kontot** med tvåfaktorsinloggning om ni använder repot som källa, och överväg en egen kopia (fork)
   som ni själva kontrollerar.

## Så kan du verifiera uppgifterna

Sökningar mot källkoden (kör i repots rot):

```
# Inga dynamiska kodkörningar eller processer (träffar i dialogrutor är Qts egna .exec())
grep -rnE "\b(eval|exec|compile|__import__|subprocess|os\.system|pickle|marshal)\b" rita_detaljplan --include=*.py

# Alla nätverksanrop
grep -rnE "QNetwork|QgsNetworkAccessManager|QgsBlockingNetworkRequest|urlopen|socket" rita_detaljplan --include=*.py

# Alla importer som inte är QGIS eller standardbibliotek
grep -rhE "^\s*(import|from) " rita_detaljplan --include=*.py
```
