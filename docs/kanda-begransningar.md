# Kända begränsningar – Rita Detaljplan

Pluginet är under utveckling. Här står vad som inte är provat mot riktiga system och vad som saknas.
Rapportera gärna vad du upptäcker under [Issues](https://github.com/ericalnemar/rita-detaljplan/issues).

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
- **Teckensnitt.** Teckenförklaringen använder teckensnittet Arial som standard; finns det inte på datorn tar QGIS ett
  annat. Byt teckensnitt under *Inställningar för teckenförklaring*.

## Funktioner som saknas

- Ändringsplaner, 3D (kropp) och import från andra system.
- Plankartan som helhet: pluginet skapar bara teckenförklaringen, resten av plankartemallen gör du själv i layoutläget.

## Funktionella begränsningar

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
  och checka in flera databasplaner samtidigt är bara testat mot låtsasdatabaser (se ovan), inte mot en riktig.
  Lägger man i stället till PostGIS-lager för en annan plan via QGIS **egen** lagerdialog (inte pluginets
  Öppna-knapp) går detta inte att skydda mot: lagret saknar då pluginets plan-filter och visar alla planers rader i
  samma tabell blandade, och pluginets verktyg ignorerar det helt eftersom det inte känns igen som ett planlager.
