# Användarhandledning – Rita Detaljplan

Så här arbetar du med pluginet, moment för moment. Ny här? Börja med snabbstarten i [README](../README.md).
Det som inte är provat mot riktiga system står under [Kända begränsningar](kanda-begransningar.md).

## Arbetsflödet

1. **Rita Detaljplan → Ny detaljplan…** skapar planen och ett QGIS-projekt (SWEREF 99, snappning påslagen). Planen kan
   lagras som en **lokal GeoPackage** (standard) eller i en **PostGIS-databas**: välj då en av QGIS sparade
   PostgreSQL-anslutningar och ett schemanamn (föreslås ur plannamnet). Planen får ett eget schema med samma tabeller
   som filen, så flera planer kan ligga i samma databas. Databasen måste ha PostGIS; projektfilen (.qgz) sparas i en
   mapp och pekar på databasen. *Öppna* i verktygsfältet frågar om det ska vara en fil eller en databas när det
   finns anslutningar. **Obs:** PostGIS-stödet är testat mot en låtsasdatabas men ännu inte mot en riktig.
   **Checka ut och checka in:** att rita direkt mot en databas över nätet blir segt. En plan som öppnas från en
   databas är därför skrivskyddad. Knappen *Checka ut* (databasikonen med pil ned, eller pennan) låser planen i
   databasen och kopierar den till en lokal GeoPackage som du redigerar i full fart. *Checka in* (samma knapp, pil upp)
   skriver tillbaka hela planen i en enda transaktion, släpper låset, pekar lagren mot databasen igen och tar bort den
   lokala kopian. Bara en kan ha planen utcheckad åt gången; den som försöker checka ut en låst plan ser vem som har
   den och sedan när, och kan bryta låset om utcheckningen är övergiven (den andras ej incheckade ändringar går då inte
   längre att lämna in). Här kan du också *kasta utcheckningen*, som släpper låset utan att spara något. Kraschar
   QGIS mitt i arbetet finns kopian kvar (i QGIS profilmapp under `detaljplan_ngp/checkouts`) och erbjuds när du
   checkar ut planen igen. Låset är en rad `checkout` i planens tabell `dp_meta`. **Obs:** utcheckning och incheckning
   är testade mot en låtsasdatabas, och SQL:en har bara kontrollerats mot PostgreSQL:s grammatik, inte körts mot en
   riktig databas: prova först på en testplan.
   Kommunen väljs i en rullista (alla 290 kommuner, sökbar). Verktygsfältet **Rita Detaljplan** öppnas längst upp
   och innehåller även ikonerna för *Ny detaljplan* och *Öppna*. Det består av ikoner; texten finns i verktygstipsen.
   Hela planen ligger i en grupp i lagerpanelen som heter som planen (först filnamnet, sedan planens namn).
2. **Pennan** öppnar alla planlager för redigering, **disketten** avslutar och frågar om ändringarna ska sparas.
3. **Rita geometrin i hierarkisk ordning.** Knapparna är gråa, med förklaring i verktygstipset, tills föräldern finns:
   - **Planområde** – planens yttre gräns. Planen har ett planområde; fler ytor läggs till det. Efter första ytan
     öppnas planens uppgifter (namn, syfte, status …).
   - **Användningsområde** – kräver planområde. Det som ligger utanför beskärs, och användningsytor får inte
     överlappa varandra (överlappet klipps bort).
   - **Egenskapsområde** – kräver en användning. Beskärs mot användningen, får överlappa andra egenskapsområden.
   - **Egenskapslinje** – bara för utfartsförbud och stängsel, på en användningsyta.
   - **Fyll resten** – två klickverktyg: ett fyller den sammanhängande del av planområdet som saknar användning
     under klicket (inte nödvändigtvis hela planområdet på en gång, om det som saknas ligger i flera skilda bitar);
     det andra fyller på samma sätt det som saknar egenskapsyta i användningsområdet du klickar i. Ett klick fyller
     och stänger av verktyget igen; du behöver inte stänga av det för hand. Ytorna får sedan bestämmelser som vanligt.
   - **Tar du bort något högre upp i hierarkin försvinner det som ligger under.** Tas planområdet bort försvinner alla
     användningsytor, egenskaper och bestämmelser. Tas en användningsyta bort försvinner egenskaperna på den och deras
     bestämmelser; en egenskap som ligger på flera användningar behåller bara den del som ligger på de som finns kvar.
     Tas en egenskap bort försvinner bara den (och dess bestämmelser). Hjälplinjer påverkas aldrig. Meddelandefältet
     berättar vad som togs bort, och redigeringen kan kasseras om du ångrar dig.
   - **Hjälplinjer** – ett eget lager för konstruktionslinjer. De ritas fritt (beskärs inte) och följer aldrig
     med till NGP.
   Sammanfaller ytterlinjer ritas bara den högsta i hierarkin (planområdesgräns före användningsgräns före
   egenskapsgräns), så att inga dubbla linjer uppstår. Ytor som saknar bestämmelse ritas med rött snedstreck. Statusraden längst ned visar planområdets storlek,
   hur stor del som har en användning och hur många ytor som saknar bestämmelse.
   **Markera** (pilikonen) markerar en yta eller linje med ett klick, eller flera med en dragen rektangel (allt
   rektangeln rör vid), oavsett vilket lager som är valt i lagerpanelen. Ligger flera ytor på varandra vid ett klick
   (t.ex. planområde, användning och egenskap) får du välja vilken det gäller. Ctrl-klick eller Skift-klick (båda
   fungerar) lägger till i markeringen, en dragen rektangel likaså. Högerklick avmarkerar allt. Det markerade lagret
   blir aktivt så att flytta, nodverktyg och radera fungerar direkt.
   **Text** (bokstaven A med en markeringsram) markerar bestämmelsernas texter: klicka på en text, eller tryck ned
   musknappen på tomt ställe och dra en rektangel. Dra en markerad text för att flytta den (alla markerade flyttas
   lika långt). Texten kan flyttas utanför sin yta: gör den det ritas automatiskt en tunn, svart ledlinje till ytan.
   Delete återställer till automatisk placering och Esc avmarkerar. Flytta text kräver att redigeringen är påbörjad.
   Delar du en yta med QGIS delaverktyg behåller ena delen sina bestämmelser; den andra delen börjar utan och
   visas som "saknar bestämmelse".
4. **Tilldela bestämmelser** med verktyget längst till höger: klicka på en yta. Verktyget stänger av sig själv när
   dialogen stängts; du behöver inte stänga av det för hand (samma sak gäller *Fyll resten* ovan).
   - Ligger flera ytor på varandra (t.ex. ett egenskapsområde över en användning) väljer du vilken yta det gäller;
     den valda ytan markeras i kartan.
   - Välj bestämmelse i den sökbara rullistan (den visar bara bestämmelser som passar ytan: rätt typ och rätt
     användningsform, uppdelade med rubriker som *Användningsbestämmelser – Kvartersmark* och en underrubrik per
     kategori). Sökrutan hittar ord var som helst i texten, inte bara det första, och flera ord i valfri ordning
     (skriv t.ex. "byggnad mark" för att hitta "Marken får inte förses med byggnad"); förslagslistan är bred så att
     långa bestämmelsetexter inte klipps av. Fyll i eventuella värden (t.ex. `30 %`, med värdetyp och enhet
     förifyllda) och klicka *Lägg till*. Man kan lägga till flera: en användningsyta kan ha flera användningar (`BC`)
     och ett egenskapsområde flera egenskaper (`e1 a2`). Beteckningen skrivs inom polygonen. Rutan för redan
     tilldelade bestämmelser är liten (en rullist syns bara om det blir fler än den rymmer).
   - *Formulering och motiv…* låter dig anpassa ordalydelsen (med varning om att den då avviker från katalogen) och
     skriva ett motiv. *Ändra…* och *Ta bort* hanterar redan tilldelade bestämmelser, och pilarna ▲ ▼ flyttar en bestämmelse upp eller
     ned i ordningen. Ordningen styr ordningen i beteckningen (BC eller CB) och att den första bestämmelsens färg och
     symbol visas.
   Rullistan visar bara bestämmelser som passar det som ligger under: en egenskapsyta på kvartersmark får bara
   kvartersmarkens egenskaper och en på allmän plats bara allmän plats (bekräftas i en rad under rullistan).
   Du skriver aldrig UUID eller tekniska fält.
   **Referensskala:** linjer och texter dimensioneras för en fast skala (1:1000 som standard; ändra på fliken *Plan* i
   *Planens uppgifter*, under *Visning i kartan*), så att de inte blir orimligt tjocka eller tunna när du zoomar. Användningens text
   är alltid tydligt större än egenskapernas, som placeras under den.
6. **Kontrollera planen** (knappen *Kontrollera planen…* i NGP-dialogen, se 8) granskar planen mot Lantmäteriets regler (se
   [ngp-regler.md](ngp-regler.md)) och listar avvikelser som *fel* (stoppar leveransen), *varningar* och
   *att fylla i*. Dubbelklicka på en rad för att markera ytan och zooma till den. Kontrollen körs också när du sparar
   och avslutar redigeringen (resultatet visas i meddelandefältet). Den kontrollerar bland annat att hela planområdet
   har användning (DP-0002/0003), överlapp, glapp och smala ytor (DP-Krav-0011–0014), självkorsande gränser
   (DP-Krav-0018), att egenskaper ligger inom användningen och har rätt användningsform, att varje bestämmelse har rätt
   värden, värdetyp och enhet (DP-0022/0009), tekniska anläggningar (DP-0019/0020), att osäkert läge inte anges
   (DP-0010) samt kraven vid laga kraft. Beslutsinformation och dokument kan ännu inte fyllas i i pluginet, så
   kontrollerna av dem gäller först när de kan anges (steg 4).
7. **Genomförandetid** är obligatorisk: varje detaljplan ska ha en. Den anges (i år eller månader, 5–15 år enligt PBL
   4 kap. 21 §) på fliken *Plan* i *Planens uppgifter*, ingår i checklistan, ger stoppande fel vid validering om den saknas
   och skrivs ut längst ner i teckenförklaringen.
   **Beslut och handlingar** ligger som flikar i samma dialog som *Planens uppgifter* (en enda knapp). Fliken *Beslut*
   har beslutsinformationen (instans, beslutstyp, diarienummer, datum för påbörjat, antagande och laga kraft,
   …) och fliken *Handlingar* planbeskrivning, beslutshandlingar (plankarta, protokoll) och
   planeringsunderlag, med namn, datum, händelse och länk (https). Referensidentiteten för en handling sätts när den
   laddats upp till NGP (steg 5). Felskrivna datum blockerar sparandet; saknade uppgifter gör det aldrig.
8. **NGP** (molnet med pil) öppnar en dialog där du väljer att *leverera planen till NGP* eller *spara den som JSON-fil*.
   Dialogen öppnas alltid, även om leveransinställningarna inte är gjorda: då är uppladdning avstängd med en förklaring
   av vad som saknas (och en knapp till inställningarna) medan filalternativet fungerar ändå. Dialogen visar resultatet
   av kontrollen (antal fel och varningar) och har knappen *Kontrollera planen…* som visar avvikelserna (punkt 6).
   Inställningarna för leveransen nås härifrån och via *Rita Detaljplan → Inställningar för leverans till NGP…*.
   - **Spara som JSON-fil** skriver leveransen enligt detaljplan 4.1 (`application/vnd.lm.detaljplan.v4+json`): ett
     detaljplanobjekt och ett planbestämmelseobjekt per tilldelad bestämmelse. Multigeometrier delas upp i en post per
     del, `reglerarAnvandningsbestammelse` härleds ur geometrin, kolumner som bara pluginet använder följer inte med och
     hjälplinjer exporteras aldrig. Koordinater skrivs som [öst, nord] med millimeters precision. Resultatet är
     kontrollerat mot Lantmäteriets schema (`spec/detaljplan-4.1.json`) i testerna, men ännu inte mot NGP:s
     verifieringsmiljö; kontrollera i första hand koordinatordningen och ringarnas riktning där.
   - **Leverera till NGP** skickar planen via Lantmäteriets Uppdatering-API (registrerar en mottagning, laddar upp
     planen, väntar på valideringen och visar statusen och valideringsrapporten). Först ställer du in miljö
     (Verifiering eller Produktion) och en autentiseringskonfiguration under *Inställningar…* i NGP-dialogen (eller
     *Rita Detaljplan → Inställningar för leverans till NGP…*): nyckel och hemlighet från Lantmäteriets API-portal lagras i QGIS autentiseringsdatabas (typ
     *Grundläggande autentisering*) och inte av pluginet. *Testa anslutning* kontrollerar att tjänsten är uppe och att
     inloggningen fungerar. Dialogen anger miljö, kommunkod (från planens kommun) och att en plan i produktion
     publiceras (då krävs en ikryssad bekräftelse). Leveransen körs i bakgrunden. Får planen valideringsfel rättar du
     felen och levererar igen: planen laddas då upp på samma mottagning. **Kräver producentbehörighet och är inte
     verifierad mot Lantmäteriets miljö**: klienten följer specifikationen (`spec/uppdatering-api-1.1.yaml`) och är
     testad mot en låtsasserver. Adressen till tokentjänsten (OAuth 2, `client_credentials`) och mediatypen
     `…detaljplan.v4+json` (specifikationens lista nämner bara v1–v3) är antaganden som kan behöva ändras.
     Uppdatering av en redan publicerad plan (ny objektversion) stöds inte än.
10. **Teckenförklaring** skapas i QGIS layoutläge, inte i huvudverktygsfältet: öppna en layout och tryck på knappen
   *Teckenförklaring* i pluginets egna verktygsfält i layoutdesignern (det kan döljas under *Visa*-menyn eller med högerklick
   på verktygsfälten, och valet kommer ihåg). Bara teckenförklaringen skapas (rubrikerna PLANBESTÄMMELSER, GRÄNSLINJER,
   ANVÄNDNING AV …, EGENSKAPSBESTÄMMELSER FÖR … med kategorier och längst ner GENOMFÖRANDETID; färgrutor och mönster med
   samma symboler som kartan; beteckningar med nedsänkta siffror). Kartan, titelblock och övrig plankartemall gör du
   själv. Markera först ett objekt, t.ex. en rektangel, så fyller teckenförklaringen den ytan; annars läggs den längst
   till höger på sidan. Den blir en grupp som du kan flytta, och trycker du igen ersätts den på sin plats. Är den för
   lång för ytan görs den mindre eller delas i två kolumner, med en varning. Prick-, ring- och plusmark ritas så att
   hela markörer syns i rutan.
   Knappen bredvid, *Inställningar för teckenförklaring*, ställer in teckensnitt, storlek på rubriker och texter, rutornas
   och linjernas storlek, avstånd (mellan ruta och text, rader, underrubriker, rubriker och kolumner), om den inledande
   texten ska vara med och om allt ska skalas efter sidans bredd (måtten gäller A1). Standardvärdena ger utseendet
   utan ändringar, inställningarna sparas i QGIS-profilen och en teckenförklaring som redan finns görs om på sin plats.
11. **Topologikontroll** (brytpunkter med en cirkel) analyserar planen och föreslår ändringar av brytpunkter och små
   glapp: att en brytpunkt i en användnings- eller egenskapsyta som ligger nära (men inte exakt på) planområdets eller
   en annan ytas brytpunkt eller gräns flyttas dit, att planområdets brytpunkter läggs till i användningen där de
   saknas, och att glapp mellan ytor i samma lager stängs (den senare ritade ytan anpassar sig till den tidigare).
   Det är precis det som gör att en gräns annars kan se olika tjock ut på olika ställen: två nästan men inte exakt
   sammanfallande linjer ritas båda, i stället för att den ena döljs som den ska när de ligger på varandra. Du väljer
   tolerans och vilka förslag som ska göras (markera i kartan med *Visa i kartan* innan du bestämmer dig); de valda
   ändringarna görs automatiskt i redigeringsbufferten (ett ångra-steg per lager) och sparas när redigeringen
   avslutas. Planområdet ändras aldrig. Dialogen visar också om hela planområdet har en användning, med en knapp som
   fyller det som saknas (samma som *Fyll resten*).
5. **Planens uppgifter** (ikonen med kryssrutan) visar en checklista över vad som krävs före leverans: kommun, namn,
   syfte, status och plantyp (markerade med *), att planområdet är ritat, att användningsytorna täcker hela
   planområdet och att alla ytor har bestämmelse. Sparande blockeras aldrig; checklistan visas också när du
   avslutar redigeringen så att du ser vad som återstår.

## Datamodellen i korthet

Ytorna är rena geometrilager (`anvandning_yta`, `egenskap_yta`, `egenskap_linje`, `detaljplan`). Bestämmelserna
ligger i tabellen `bestammelse` med en rad per bestämmelse och yta; vid leverans blir varje rad ett eget
planbestämmelseobjekt med ytans geometri. Samma bestämmelse (samma text och värden) får samma beteckning överallt i
planen (e1, e2 …). Kopplingen mellan egenskap och användning (`reglerarAnvandningsbestammelse`) härleds ur geometrin
när planen exporteras.

## Symbologi, katalog och öppna plan

- **Symbologi** från stilbiblioteket [Detaljplaner (Bfs 2020:6)](https://hub.qgis.org/styles/238/) (CC0, av Alnemar):
  användningsytor färgas efter Boverkets färgnamn, egenskaper får egenskapsgräns, prickmark-mönster samt utfarts- och
  stängselsymboler, planområdet får planområdesgräns, och beteckningen skrivs ut som etikett. Färgnamnens
  färgkoder styrs av `FARGER` i `core/symbology.py`. **Hierarkin i kartan** följer lagerordningen: planområdesgränsen
  ligger över användningsgränsen som ligger över egenskapsgränsen, så den högsta syns där linjer sammanfaller.
  Användningslagret ritas med blandningsläget Multiplicera så att egenskapsmönster syns under dess färg.
- **Uppdatera planbestämmelsekatalogen…** hämtar senaste release från Boverket i bakgrunden (inklusive upphörda
  bestämmelser). Pluginet innehåller en kopia (908 pågående bestämmelser) och fungerar därför också utan nätverk.
  Nätverksanropen går via QGIS egna nätverksinställningar (proxy m.m.).
- **Öppna detaljplan…** läser in en befintlig plan-GeoPackage i det öppna projektet.

Katalogen är hämtad från [Boverkets öppna data](https://www.boverket.se/sv/om-boverket/oppna-data/planbestammelser/).
Källa: Boverket, Planbestämmelsekatalogen.
