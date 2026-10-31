# Kända begränsningar – Rita Detaljplan

Pluginet är under utveckling. Här står vad som inte är provat mot riktiga system och vad som saknas.
Rapportera gärna vad du upptäcker under [Issues](https://github.com/ritaplan/rita-detaljplan/issues).

## Inte provat mot riktiga system

Pluginet har automatiska tester (se [Utveckling](utveckling.md)), men flera delar har bara körts mot låtsassystem:

- **Leverans till NGP.** Uppladdningen via Lantmäteriets Uppdatering-API är byggd efter specifikationen
  (`spec/uppdatering-api-1.1.yaml`) och testad mot en låtsasserver, men **aldrig mot Lantmäteriets riktiga
  verifieringsmiljö**. Adressen till tokentjänsten och mediatypen `application/vnd.lm.detaljplan.v4+json` är antaganden.
  Kräver dessutom producentbehörighet. Att spara leveransen som JSON-fil och skicka den för granskning fungerar oberoende
  av detta. Uppdatering av en redan publicerad plan (ny objektversion) stöds inte.
- **PostGIS.** Att skapa och öppna planer i en databas och att **checka ut och checka in** är testat mot en
  låtsasdatabas och prövat mot en riktig PostGIS-databas, men inte i alla tänkbara miljöer och upplägg. Prova
  först på en testplan och gör säkerhetskopia av schemat innan du checkar in en viktig plan.
- **Layoutdesignern.** Knapparna för teckenförklaring i layoutläget har testats med en låtsasdesigner, inte i alla
  QGIS-versioner. Rapportera om verktygsfältet eller menyposten saknas hos dig.
- **QGIS-version och system.** Testat med QGIS 4.2.2 på Windows. Andra versioner och Linux/macOS är inte provade.
- **Arkivpaket.** Bevarandemetadatan (`metadata/PREMIS.xml`) är giltig mot Library of Congress schema för PREMIS 3.0 och följer
  Boverkets dataelementkatalog (maj 2026), dess värdelistor och obligatoriska element, men är inte provad mot något e-arkiv.
  Boverkets två exempelfiler är inte giltiga mot schemat (de har bland annat ett `objectCategory`-element som schemat inte
  har) och pluginet följer dem därför inte; se [arkivpaket-revision.md](arkivpaket-revision.md). Katalogen vill lägga planens
  uppgifter i `objectCharacteristics` på planen, men PREMIS tillåter inte det på en representation: pluginet lägger dem i
  `significantProperties` (i ett eget namnrymd med ett eget schema i paketets `schemas/`). Planen är en **representation**,
  som Boverkets specifikation anger, och filerna är filer; en PREMIS-expert menar att modelleringen går att diskutera (till
  exempel mellannivån och relationen mellan planen och filerna, som här är `has Part`/`is Part Of`) och att den kan variera
  med hur ett bevarandesystem är uppbyggt. PREMIS kräver inga bestämda objekttyper. Paketet är **inget E-ARK-/FGS-paket** (ingen `METS.xml`), så en kommun med
  e-arkiv får lägga PREMIS-filen i sitt eget paketeringsflöde, som Boverkets manual beskriver. Formaten saknar
  registernyckel (PRONOM) och metadatafilen har ingen egen kontrollsumma. **Pluginet gör inga filer till PDF/A och kontrollerar
  inte att de är det.** Plankartan och planbeskrivningen ska läggas med som färdiga PDF/A-filer, kontrollerade av användaren
  (till exempel med veraPDF).
- **Teckensnitt.** Teckenförklaringen använder teckensnittet Arial som standard; finns det inte på datorn tar QGIS ett
  annat. Byt teckensnitt under *Inställningar för teckenförklaring*.

## Funktioner som saknas

- Ändringsplaner, 3D (kropp) och import från andra system.
- Plankartan som helhet: pluginet skapar teckenförklaringen och exempellayouter (A1–A4, liggande och stående, med karta,
  norrpil, skalstock och titelruta) att utgå från. Kommunens egen plankartemall, med grafisk profil och grundkarta, gör
  du själv i layoutläget.

## Funktionella begränsningar

- **Egenskapspunkter** (schema 10) är nya och inte provade i NGP:s verifieringsmiljö. Exporten följer schemat
  (`bestammelsegeometri` av typen `punkt`). Markens höjd visas med höjden som beteckning ("+31,8") och som en enda rad
  i teckenförklaringen ("+0,0 Markens höjd över nollplanet"); det är pluginets tolkning av hur höjder brukar visas på
  plankartor. Programmet *Tagga planbeskrivning* listar punktbestämmelserna men ritar inte punkterna i sin karta.
- **De nya lagren i äldre planer.** Hjälpytor och hjälppunkter (schema 9) och egenskapspunkter (schema 10) läggs till när
  en äldre plan öppnas med *Öppna detaljplan (GeoPackage)…*. Öppnar du ett äldre projekt (.qgz) direkt saknar det de nya
  lagren tills planen öppnats på det sättet; knappen för att rita egenskapspunkter är då grå och säger det.
  Uppgraderingen av ett PostGIS-schema är skriven men inte provad mot en riktig databas, som resten av PostGIS-delen.

- **Tagga planbeskrivning söker bara motiv under rubriker med temat *Motiv till detaljplanens regleringar*.** Motiv som står
  utspridda under andra teman (till exempel under varje användning i beskrivningen av planen) hittas inte automatiskt. En
  motivrubrik som skrivits på ett annat sätt känns igen om den liknar de vanliga (*Motiv*, *Motiveringar*, *Skäl till
  bestämmelserna* …); annars väljer du temat för rubriken i listan. Specifikationen kräver inte den avgränsningen.

- Endast 2D. Volymgeometri (kropp) stöds inte än.
- Endast användnings- och egenskapsbestämmelser stöds (inga pågående bestämmelser i katalogen är administrativa).
- Lägesmetodens variant är en gemensam lista; koppling variant ↔ metod valideras först i steg 3.
- Bestämmelsevärden lagras som JSON-text i fältet `bestammelsevarde`; ändra dem via bestämmelseväljaren.
- Multipart-geometrier lagras som Multi* i GeoPackage men NGP godkänner inte multigeometrier; exporten (steg 4)
  delar upp dem. Se [ngp-regler.md](ngp-regler.md) för alla regler som valideringen ska följa.
- Objekt som läggs till på annat sätt än med ritverktygen (t.ex. inklistrade) kontrolleras mot hierarkin på samma sätt.
- Flyttar man en egenskap efter att den ritats varnas man om att den inte längre ligger på en användning, men den
  tas inte bort automatiskt (däremot tas egenskaper bort när användningen de ligger på tas bort). Flyttas en användning eller ett planområde beskärs användningen respektive varnas man. Den fullständiga kontrollen görs i valideringen (steg 3).
- **Flera planer kan vara laddade samtidigt, men bara en är aktiv åt gången.** Ny detaljplan/Öppna/Importera lägger
  till planen bredvid en ev. redan laddad plan och gör den nya aktiv; pluginets verktyg (rita, tilldela, kontrollera,
  leverera) jobbar bara mot den aktiva. Är fler än en laddad frågar pennan vilken som ska redigeras (byter aktiv
  plan). *Stäng aktiv plan* tar bort den aktiva planens lager ur projektet (rör inte filen/databasen). Att checka ut
  och checka in flera databasplaner samtidigt är testat både mot låtsasdatabaser och mot en riktig PostGIS-databas.
  Lägger man i stället till PostGIS-lager för en annan plan via QGIS **egen** lagerdialog (inte pluginets
  Öppna-knapp) går detta inte att skydda mot: lagret saknar då pluginets plan-filter och visar alla planers rader i
  samma tabell blandade, och pluginets verktyg ignorerar det helt eftersom det inte känns igen som ett planlager.
