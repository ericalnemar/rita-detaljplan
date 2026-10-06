# Ändringslogg

Formatet följer [Keep a Changelog](https://keepachangelog.com/sv/1.1.0/), versionsnumren [Semantic Versioning](https://semver.org/lang/sv/).

## Ej utgivet

## [0.1.47] – tagga planbeskrivning

- **Tilldela bestämmelser: rutan *Ytans bestämmelser* fyller ut sin ruta.** Listan har ingen fast högsta höjd längre
  utan växer när du gör dialogrutan större.
- **Tilldela bestämmelser: ny rullista *Använd en bestämmelse som redan finns i planen*.** Den visar bestämmelser som
  redan används på andra ytor av samma typ i planen (och som passar ytans användningsform). Välj en och klicka
  *Lägg till* så läggs den på ytan med samma text, värden och beteckning, utan att du skriver den igen.
- **Beteckningarna (t.ex. f1) hör till exakt en bestämmelse i hela planen.** Numreringen räknade redan över hela planen
  när du lägger till eller ändrar bestämmelser. Nu kontrollerar *Kontrollera planen* också att ingen beteckning delas
  av två olika bestämmelser (som kan finnas kvar i äldre planer), och *Indexera om* rättar det genom att ge den
  bestämmelse som lades till senare nästa lediga siffra. Dessutom kan en ny eller ändrad bestämmelse aldrig få samma
  beteckning som en annan bestämmelse (den får då nästa lediga siffra), och en dubblett som ändå finns rättas när du
  sparar.
- **Du kan nu välja egen beteckning för bestämmelser där katalogens beteckning är en mall.** Det gäller bland annat
  *DP_AP_Eg_UtformAP_Dagv_Annan* och de andra "Annan"- och "Äldre"-bestämmelserna för utformning av allmän plats
  (36 bestämmelser, t.ex. `[beteckning:text]#`). Tidigare gick bara texten att fylla i, och plankartan visade
  mallen ("beteckning:text1") som beteckning. Nu finns fältet *Beteckning på plankartan* i tilldelningsrutan och i
  rutan för att anpassa bestämmelsen; siffran läggs på automatiskt (Dv blir Dv1, Dv2 …) och en annan beteckning
  numreras för sig. Skriv bara bokstäverna: siffror du skriver sist tas bort (dagvatten1 blir dagvatten, och
  bestämmelserna får dagvatten1, dagvatten2 …), så att två olika bestämmelser aldrig får samma beteckning.
  Beteckningen krävs. Du ändrar den med *Ändra*, och en bestämmelse som sparats med mallen som
  beteckning får ett tomt fält som du fyller i.
- **Rättat: användningsgränsen mellan två användningar kunde bli hälften så bred.** Gränsen mellan två användningar
  ritas bara av den ena grannen, och om den andra grannens fyllning ritades efter täckte den hälften av linjen, så den
  blev lika smal som en egenskapsgräns. Det drabbade bara vissa ytor, och först efter sparande eftersom ordningen på
  ytorna då ändras. Nu ritas alla fyllningar först och alla kantlinjer efteråt, så gränsen blir lika bred överallt.
  Ett projekt som sparats av en äldre version ritas om med den nya symbologin (planens referensskala behålls) när
  det öppnas.
- **Rättat: en egenskapsyta som ritats över gränsen till en annan användningsform klipps nu mot användningsgränsen.**
  Tidigare vägrades bestämmelsen med "Bestämmelsen gäller allmän plats men användningsytan är kvartersmark". Nu klipps
  ytan till den del som ligger på användningar med rätt användningsform (med ett meddelande), för allmän plats,
  kvartersmark och vattenområde. Samma sak händer om man flyttar i ytans hörn efteråt. Ligger inget alls på rätt
  form vägras bestämmelsen som förut, och ytan lämnas orörd. En egenskapsyta som ännu saknar bestämmelse och ligger
  över användningar med olika former klipps direkt till den form där största delen av ytan ligger.
- **Ny knapp i verktygsfältet: Tagga planbeskrivning.** Öppnar programmet *Tagga planbeskrivning* i ett eget fönster
  med den aktiva planen förvald (även ändringar som inte sparats än). Programmet taggar planbeskrivningen i Word enligt
  BFS 2020:8 och Lantmäteriets Planbeskrivning 2.0: förslag på tema, grupp och undergrupp för varje avsnitt som
  granskas, motiv som kopplas till planens bestämmelser (med en karta över var bestämmelsen gäller), kontroll mot
  BFS 2020:8 och en leverans- och granskningskopia av dokumentet. *Importera till planen* lägger syftet och motiven ur
  planbeskrivningen på planen och bestämmelserna. Programmet ligger i `rita_detaljplan/planbeskrivning/` och kan också
  köras fristående, utan QGIS (`python -m rita_detaljplan.planbeskrivning`, kräver PySide6). Se användarhandledningen,
  punkt 12, och [utveckling](docs/utveckling.md).
- **Programmet heter nu Tagga planbeskrivning överallt** (fönstrets titel och rubrik, tidigare *Planbeskrivning
  Taggning*), och fönstret har samma ikon som knappen i verktygsfältet. Sparade val i programmet följer med.
- **Checklistan "Före leverans till NGP" har en rad om motiv**: "Alla planbestämmelser har ett motiv (krävs vid laga kraft)",
  med antalet som saknar motiv. Den följer motivfliken medan dialogen är öppen, så den blir grön direkt när motiven
  skrivits. Fasta motiv (tekniska anläggningar) räknas inte.

## [0.1.46] – hjälplinjen som heldragen cyan

- **Hjälplinjerna ritas nu som en heldragen, svagt genomskinlig cyan linje** i stället för en streckad blå. Ikonen på
  hjälplinjeknappen är uppdaterad på motsvarande sätt. Gäller även planer som skapats tidigare.

## [0.1.45] – id på varje objekt i leveransen

- **Leveransen (JSON) har nu ett `id` på varje objekt** (planen och varje bestämmelse), lika med objektets
  `objektidentitet`. Schemat i Nationell informationsspecifikation Detaljplan 4.1 kräver inte `id` på GeoJSON-objekten,
  men verktyg som tolkar leveransen som vanlig GeoJSON, till exempel Focus Detaljplan, vägrade importera planen utan
  det. Övrigt innehåll är oförändrat.

## [0.1.44] – säkerhetsbeskrivning och kodad text i dialogrutor

- **Ny [säkerhetsbeskrivning](docs/sakerhet.md)** för den som ska bedöma pluginet i en organisation: vad det gör, vilka
  data som rör sig vart, hemligheter, databas, beroenden, kända fynd och rekommendationer.
- **Säkerhet: text i dialogrutor kodas nu innan den visas som rik text.** Text från Boverkets katalog, planens namn och
  API-adressen (bestämmelseväljaren, leveransbekräftelsen, leveransdialogen och kontrollistan i planens uppgifter) kunde
  tidigare innehålla HTML som ändrade hur dialogrutan såg ut. Qts rika text kör inga skript, så ingen kod kunde köras.

## [0.1.43] – meddelanden som stängs av sig själva, pluginkälla

- **Meddelanden i överkanten av kartfönstret stängs nu av sig själva:** information och "klart" efter 5 sekunder,
  varningar och fel efter 10 sekunder.
- **Repot kan användas som pluginkälla i QGIS.** Ny `plugins.xml` (genereras av `tools/build_plugins_xml.py`) som
  QGIS pluginhanterare kan läsa, så att pluginet går att installera och uppdatera direkt i QGIS utan att ladda ner
  zip-filen för hand. Se README för URL:en.

## [0.1.42] – redigering fungerar igen efter omstart

- **Fix: pennan gjorde ingenting när ett sparat projekt öppnades igen.** Felet kom in med stödet för flera planer
  (0.1.39): när QGIS läser in ett sparat projekt är lagerträdet ännu inte återställt när lagren läggs till, så
  pluginet hittade inga planlager och kopplade aldrig på dem. Nu kopplas planen på när projektet är färdigläst.

## [0.1.41] – reglerar annan detaljplan

- **Ny knapp "Reglerar annan plan…" i tilldelningsdialogen, för egenskapsbestämmelser.** Anger att bestämmelsen
  reglerar (hör ihop med) en annan detaljplan (`reglerarDetaljplan`, Nationell informationsspecifikation
  Detaljplan 4.1), t.ex. vid samordning mellan grannplaner. Fältet fanns i modellen och exporterades aldrig till
  NGP eftersom det inte gick att fylla i. Välj bland andra laddade planer, eller skriv in identiteten (UUID)
  direkt om planen inte är laddad här.

## [0.1.40] – snappning mot korsningar slås på automatiskt

- **Snappning mot korsningar ("Tillåt snappning mot korsande linjer") slås nu på automatiskt när redigeringen
  startar**, precis som den vanliga snappningen – annars missar man lätt att två ritade linjer (t.ex. en
  egenskapsgräns över en användningsgräns) ska mötas exakt där de korsar utan att dela en nod.

## [0.1.39] – flera planer samtidigt, kvalitetsbeskrivning och ett tomt projekt sparas som sin egen fil

- **Flera planer kan nu vara laddade i samma projekt samtidigt.** Tidigare hamnade båda planernas lager osorterat i
  projektet om man öppnade en andra plan medan en första redan var laddad, och pluginets verktyg kunde då tyst agera
  på fel plans lager (de letade bara efter "ett lager för tabellen X", oavsett vilken plan det hörde till). Nu är
  alltid en av de laddade planerna **aktiv** – det är bara den pluginets verktyg (rita, tilldela, kontrollera,
  leverera) jobbar mot – och Ny detaljplan/Öppna/Importera lägger till planen bredvid eventuella redan laddade
  planer i stället för att ersätta dem, och gör den nya aktiv.
- **Ny meny: Stäng aktiv plan.** Tar bort den aktiva planens lager ur projektet (rör inte filen/databasen den kom
  från). En av de andra laddade planerna, om någon, blir aktiv i stället.
- **Pennan frågar vilken plan som ska redigeras om fler än en är laddad.** Annars (det vanliga) startar
  redigeringen direkt som förut.
- **Ny meny: Byt aktiv plan…** Byter aktiv plan utan att starta en redigeringssession – t.ex. för att kontrollera
  eller leverera en annan laddad plan än den man senast redigerade.
- Checka ut/in håller nu reda på varje laddad databasplans egen utcheckningsstatus när man växlar aktiv plan, så
  att flera utcheckade databasplaner kan vara laddade samtidigt utan att blanda ihop varandras lås. Att checka ut
  och checka in flera planer samtidigt är bara testat mot låtsasdatabaser, inte mot en riktig (se
  [Kända begränsningar](docs/kanda-begransningar.md)).
- **Syns nu vilken plan som är aktiv när flera är laddade**: QGIS egen fönstertitel (och projektets namn) följer
  den aktiva planen och statusraden visar "Plan: <namn>" längst fram. Syns bara när det faktiskt finns fler än en
  laddad plan att blanda ihop.
- **Planens uppgifter, Topologikontroll, Kontrollera planen och Leverera till NGP har en egen rad för att se och
  byta aktiv plan**, direkt i dialogen (en lista högst upp, bara synlig när fler än en plan är laddad).
  Topologikontroll, Kontrollera planen och Leverera till NGP läser om sina resultat för den nya planen; Planens
  uppgifter (som har mycket mer tillstånd över flera flikar) stänger och öppnar sig på nytt för den.
- **Ny flik "Kvalitet" i Planens uppgifter**, och en ny knapp "Kvalitet…" i tilldelningsdialogen (per bestämmelse):
  digitaliseringsnivå, beskrivning av nivå, korrigerade gränser, kontrollerat planeringsunderlag, användbarhet
  och beskrivning av användbarhet (Nationell informationsspecifikation Detaljplan 4.1). Fälten fanns redan i
  modellen och exporterades till NGP, men gick inte att fylla i någonstans i pluginet och skickades alltid tomma.
  Digitaliseringsnivå och användbarhet förifylls med *komplett* respektive *god* (det vanliga: ritas direkt i
  rätt lägesnoggrannhet) – ändra bara om det inte stämmer.
- **Kontrollerar nu kvalitetsbeskrivning vid laga kraft** (digitaliseringsnivå och användbarhet, för planen och
  för varje bestämmelse): syns i checklistan i Planens uppgifter och som fel i Kontrollera planen om de saknas.
  Detta krav fanns redan dokumenterat (se [ngp-regler.md](docs/ngp-regler.md)) men kontrollerades inte förut.
- **Rättat: började man i ett tomt, osparat QGIS-projekt (t.ex. med en grundkarta tillagd) och skapade en ny
  detaljplan, hamnade planens egna projektfil på disk med bara planens lager – den öppna kartan (med grundkartan)
  förblev osparad.** Nu sparas det öppna projektet som den nya planens projektfil i det fallet, så att allt hänger
  ihop i en och samma fil. Är kartan redan sparad som något annat rörs den filen inte (planens egen projektfil
  skapas då bredvid, som tidigare) – det är bara ett tomt/aldrig sparat projekt som adopterar den nya filen.
  Gäller både Ny detaljplan och Importera leverans.

## [0.1.36] – bortstädning av döda ritkommandon från den gamla kommandoraden

- **Tagit bort oanvändbar kod**: PL/Cirkel/Rektangel/Flytta/Kopiera/Längd/Vinkel (de gamla ritkommandona från den
  textbaserade kommandoraden) gick inte längre att nå sedan kommandoraden själv togs bort, men knapparna/koden
  bakom dem låg kvar oanvänd. Upptäcktes vid en dokumentationsgenomgång: användarhandledningen beskrev dem
  fortfarande som en fungerande del av verktygsfältet. Koden (och motsvarande tester) är nu helt borttagen, och
  användarhandledningen uppdaterad för att matcha det verkliga verktygsfältet.

## [0.1.35] – CAD-aktiveringen fäster nu även efter en full omstart

- **Rättat: Avancerad digitalisering slog ibland inte på med pennan längre efter en omstart av både QGIS och
  datorn.** Ett första försök (köra aktiveringen om varje gång verktygsfälten uppdateras, inte bara vid
  redigeringsstart och verktygsbyte – samma idé som löste ikonstorleken, 0.1.28) räckte inte heller: loggning
  visade att `enable_action.trigger()` kördes men inte fastnade (knappens ikryssade läge ändrades inte) när den
  anropades direkt synkront från verktygsbytet – QGIS hann inte bli klar med sin egen aktivering av det just
  valda ritverktyget än, samma sorts race som `dock.hide()` hade (0.1.31). Själva triggningen skjuts nu upp till
  nästa varv av händelseloopen (`QTimer.singleShot(0, ...)`), så QGIS hinner bli klar först.

## [0.1.32] – Topologikontroll varnar nu även för obestämda ytor

- **Topologikontroll visar nu även "Saknar bestämmelse" som fel**, för ytor som är ritade (och alltså täcker sin
  del av planen geometriskt) men inte fått någon bestämmelse – syntes annars bara som ett rött snedstreck i
  kartan tills man körde hela valideringen (Kontrollera planen). Samma kontroll som redan fanns där
  (`validation.check_hierarchy`), nu bruten ut till en egen funktion (`validation.unassigned_areas`) som
  återanvänds av topologikontrollen.

## [0.1.31] – panelen döljs inte längre när Avancerad digitalisering slås på

- **Rättat: Avancerad digitalisering slog ibland inte på med pennan längre.** Det uppskjutna `dock.hide()` som
  döljer sidopanelen efter aktivering (så den inte dyker upp av sig själv) visade sig ibland hindra att
  aktiveringen fäster på riktigt. Panelen döljs inte längre alls – bättre att den syns än att funktionen inte
  går igång. Gäller både Avancerad digitalisering och Floater.

## [0.1.30] – fyll-knapparna tillbaka i det övre verktygsfältet

- **Fyll användning och Fyll egenskap sitter nu i både det övre verktygsfältet och i den nedre raden** – samma
  knappar på båda ställena (som Markera/Avmarkera alla/Text sedan tidigare).

## [0.1.29] – indexera om bestämmelser, redigera efter tillägg, finare linjesymboler

- **Ny knapp "Indexera om" i tilldelningsdialogen.** Indexsiffran i en beteckning (t.ex. F1/F2) sätts när
  bestämmelsen läggs till och följer INTE med om man flyttar om ordningen i listan med ▲/▼ efteråt (▲/▼ styr bara
  teckenordningen i beteckningen, t.ex. BC/CB) – det kunde bli "F2 F1" i stället för "F1 F2". Knappen numrerar om
  siffrorna efter listans nuvarande ordning. Samma bestämmelse ska ha samma beteckning överallt i planen, så
  omindexeringen räknas om på alla ytor som delar den, men bara inom det talområde ytans egna bestämmelser redan
  använder (F1/F2 byter bara plats med varandra – andra ytors bestämmelser med samma bokstav men andra tal rörs
  inte).
- **Formuleringen på en redan tillagd bestämmelse kan redigeras.** Detta gick redan att göra via knappen
  "Ändra…" i tilldelningsdialogen (samma dialog som vid tillägg, med samma kryssruta "Anpassa formuleringen") –
  inget nytt behövde byggas.
- **Egenskapslinjens teckenförklaring (utfartsförbud, stängsel) visar nu också gränslinjen punkterna ligger på**
  (normalt en användningsgräns), inte bara lösryckta punkter som tidigare – stilbibliotekets symbol har bara
  punkter, ingen egen linje. Punkternas diameter är också något mindre (8→6 punkter).
- **Rättat: symbolerna på fastighetsindelningslinjen kunde hamna tätt intill varandra.** Där kantlinjen delas upp
  i flera bitar (gemensamma kanter mot planområdet/användningen klipps bort, se
  `symbology.hierarchical_boundary`) tvingade symbolen fram en extra markör i varje bits båda ändar utöver de
  jämnt fördelade – vilket gav två tvärställda fyrkanter tätt intill varandra där bitarna möttes. Bara jämnt
  fördelade markörer nu, och något mindre (6→5 punkter).
- **Användningsrutorna i teckenförklaringen (t.ex. G₁) är lite bredare som standard** (15→18 mm vid A1).
- **Rättat: stor lucka mellan bestämmelse och formulering för koder utan egen symbol (t.ex. F1/F2) när planen
  också hade utfartsförbud eller stängsel.** Gränslinjen med punkter (se ovan) behöver en bredare bit för att
  punkterna ska synas, men den bredden drog tidigare med sig textstarten för HELA teckenförklaringens kolumn –
  även rader som inte alls ritar en linje. Koder och färg-/mönsterrutor håller nu sitt eget textstartläge,
  oberoende av hur breda gränslinjerna behöver vara.

## [0.1.28] – ikonstorleken höll inte efter en omstart av QGIS

- **Rättat: 0.1.27:s ikonstorleksfix höll bara tills QGIS startades om.** `iface.iconSize()` gav ett för litet
  värde när verktygsfältet byggs i `initGui()` direkt efter en omstart av QGIS (innan huvudfönstret hunnit
  tillämpa den sparade inställningen på riktigt) – ett engångsvärde vid start räckte alltså inte. Läses nu om
  varje gång verktygsfälten uppdateras (`refresh()`, som körs vid varje ändring, bl.a. när en plan öppnas), inte
  bara en gång vid start.

## [0.1.27] – rätt ikonstorlek i den nedre verktygsraden

- **Rättat: den nedre verktygsraden kunde bli mycket mindre än resten av QGIS** om man ställt in en annan
  ikonstorlek än standard (Inställningar → Alternativ → Allmänt). Både den och verktygsfältet högst upp använde
  ett fast värde (28×28) i stället för QGIS egen, aktuella ikonstorlek (`iface.iconSize()`) – verktygsfältet
  högst upp fick ändå rätt storlek eftersom QGIS självt justerar sina egna, dockade verktygsfält, men den
  flytande nedre raden (inte dockad i QGIS) gjorde det inte. Båda hämtar nu `iface.iconSize()` i stället.

## [0.1.26] – delat PostGIS-schema, kartan ersätts inte längre

- **Rättat: avaktiverar man en aktiv ritknapp (Planområde/Användning/Egenskapsyta m.fl.) fortsatte QGIS eget
  ritverktyg ändå fånga klick i kartan**, trots att knappen visade "av" – man kunde fortsätta rita samma objekt.
  Gäller både när man klickar knappen igen för att stänga av den, och när den blir otillgänglig medan den är
  aktiv (t.ex. om hierarkin ändras mitt i en pågående ritning). Byter nu till panorera-verktyget på riktigt i
  båda fallen, vilket avslutar den pågående digitaliseringen precis som att byta ritverktyg alltid gör.
- **Nytt andra verktygsfält, flytande ovanpå kartvyn längst ned.** Ett urval knappar i stället för ett textfält
  med kommandonamn (den tidigare kommandoraden, där man skrev ett kommando och tryckte Enter, är borttagen – det
  visade sig svårt att göra pålitligt). Byggd som ett riktigt verktygsfält (samma sorts `QToolBar` och
  ikonstorlek, 28×28, som verktygsfältet högst upp), men flytande som en listlös, halvgenomskinlig panel
  centrerad längst ned i kartvyn – inte dockad i QGIS huvudfönster (ett dockat försök gjordes och byttes tillbaka;
  gick inte att dra runt, det behövdes inte). **Osynlig som standard, visas hela tiden under en pågående
  redigeringssession** (och bara då) – annars är den bara i vägen. Innehåller hittills **Markera**,
  **Avmarkera alla**, **Text** (samma knappar som i verktygsfältet högst upp, se nästa punkt), **Fyll
  användning**, **Fyll egenskap**, **Dela objekt**, **Lägg till hål**, **Slå ihop valda objekt**,
  **Brytpunkter** (för det aktiva lagret), **Trimma/Förläng objekt**, samt **Spårning**, **Parallell** och
  **Vinkelrätt**; fler knappar läggs till efter hand.
- **Markera, Avmarkera alla och Text sitter i både verktygsfältet högst upp och i den nedre raden** – samma
  knappar på båda ställena (en `QAction` kan sitta i flera verktygsfält samtidigt).
- **Parallell/Vinkelrätt/Spårning är exakt samma knappar som QGIS egna** – Parallell/Vinkelrätt är desamma som i
  panelen Avancerad digitalisering (`mParallelAction`/`mPerpendicularAction`), Spårning densamma som i
  snappningsverktygsfältet (`EnableTracingAction`) – inte egna ombyggnader av dem. Tidigare försök att själv klicka
  fram en kant och räkna ut/låsa vinkeln för Parallell/Vinkelrätt gav bl.a. en oändligt lång, "fastnaglad" linje som
  läckte in i en helt annan, senare ritning, och visade inte rätt ikryssat/aktivt läge i verktygsraden. Eftersom det
  nu är bokstavligen samma knappar visar de alltid samma (korrekta) läge, oavsett var man klickar dem – och all
  logik sköts av QGIS själv, precis som när man använder panelerna direkt.
- **Längd/Vinkel visas nu som flytande, redigerbara rutor vid muspekaren under ritning, som i AutoCAD**
  ("Floater" – en funktion som redan fanns i QGIS egen panel Avancerad digitalisering, bara aldrig påslagen som
  standard). Tryck Tab för att växla mellan rutorna, skriv för att ändra värdet. Påslagen automatiskt, ingen egen
  knapp behövs. XY-koordinaterna i den är avstängda (bara längd/vinkel är relevanta för planritning), och själva
  panelen (sidopanelen, inte rutorna på kartan) hålls dold – den behöver inte dyka upp bara för att man börjar
  redigera.
- **Avancerad digitalisering slås på automatiskt när man börjar redigera** (annars är den avstängd som standard
  och Parallell/Vinkelrätt/Floater fungerar inte förrän man råkar öppna panelen själv) – utan att panelen
  (sidopanelen) dyker upp av sig själv. **Rättat:** slog inte på riktigt förrän vi bytte från att bara kalla
  Python-metoden `dock.enable()` till att trigga den riktiga på/av-knappen (`mEnableAction`) – samma mönster som
  löste Floater tidigare – och det räckte inte heller: "fäster" bara på riktigt när ett ritverktyg faktiskt är
  aktivt, så den slås på både vid redigeringsstart och varje gång ett ritverktyg (PL, pennan m.fl.) väljs. Inte
  ens det räckte: att dölja panelen direkt efter aktiveringen avbröt QGIS egen uppdatering av knapparna i den
  (konstruktionsläge, parallell, vinkelrätt m.fl. förblev gråa) – döljandet skjuts nu upp till nästa varv av
  händelseloopen i stället.
- **Snappning slås på automatiskt när man börjar redigera** – Parallell/Vinkelrätt/Spårning kräver det för att
  fungera alls, men det behövs ingen egen knapp för det i verktygsraden.
- **Dela objekt** och **Trimma/Förläng objekt** tillagda i den nedre verktygsraden (QGIS egna verktyg, inte
  ombyggda).
- **PostGIS: delat schema per flera planer.** Tidigare fick varje plan ett eget schema. Nu väljer man ett schema och
  en plan-id: planer i samma schema delar tabeller (en `plan`-kolumn skiljer deras rader åt) och måste därför dela
  koordinatsystem. Nya planer i ett befintligt schema lägger bara till sina rader; inget schema tas bort vid fel om
  det redan fanns sedan tidigare. Öppna-dialogen listar först scheman, sedan planerna i det valda schemat.
  Utcheckning/incheckning låser och skriver bara den egna planens rader i de delade tabellerna.
- **Rättat:** incheckning av en andra plan i samma schema kunde krascha med "duplicate key value violates unique
  constraint" på `fid`. Den lokala kopian har sin egen, från noll räknade `fid`, som INTE längre skrivs in rakt av i
  den delade tabellens gemensamma `fid`-sekvens vid incheckning (databasen tilldelar själv en ny). Ingenting i
  pluginet pekar mellan tabeller via `fid` – all koppling sker via `objektidentitet` (UUID).
- **Ny detaljplan…/Importera leverans (JSON)…** ersätter inte längre hela projektet. De lägger bara till planens
  grupplager i den redan öppna kartan (t.ex. en grundkarta ligger kvar); fanns det redan en plan från pluginet laddad
  ersätts den (för att undvika tvetydighet om vilken plan verktygen jobbar mot), men allt annat rörs inte.
- **Nya ritkommandon i verktygsfältet, som i CAD-program:** PL (rita – väljer typ om flera är möjliga), Cirkel och
  Rektangel (på ett ytlager, med QGIS egna formverktyg), Flytta och Kopiera (på det som är markerat), samt Längd,
  Vinkel, Parallell och Vinkelrätt (öppnar/fokuserar QGIS egen panel Avancerad digitalisering; Parallell/Vinkelrätt
  låter dig klicka på en befintlig linje eller kant i kartan och låser vinkelfältet till den kantens vinkel, eller
  90° mot den). Spåra och offset-under-spårning behövs inte byggas separat: de finns redan i QGIS egen Avancerad
  digitalisering, aktiva så fort man ritar med pennan.

## [0.1.25] – kommandorad

- **Ny kommandorad**, som i CAD-program: dockas längst ned i huvudfönstret. Skriv ett kommandonamn eller en kortform
  (t.ex. `m` för Markera, `eg` för Egenskapsyta) och tryck Enter för att aktivera verktyget – samma knappar som i
  verktygsfältet, med samma villkor för när de får användas. Rutan visar vilket verktyg som är aktivt just nu, eller
  (med röd text) varför ett kommando inte gick. Escape kör kommandot `esc` (avmarkera alla). Döljs/visas via
  **Rita Detaljplan → Kommandorad**.

## [0.1.24] – avmarkera alla är grå utan redigeringssession

- **Avmarkera alla** är grå (liksom Markera och Text) när ingen redigeringssession pågår, i stället för att vara
  tillgänglig så fort en plan är öppen.

## [0.1.23] – importikonen bort ur verktygsfältet, avmarkera alla tillbaka

- **Importera leverans (JSON)** finns bara i menyn Rita Detaljplan igen, inte längre som ikon i verktygsfältet.
- **Avmarkera alla** är tillbaka som knapp i verktygsfältet, bredvid *Markera* (utöver högerklick, som fortfarande
  fungerar).

## [0.1.22] – egenskaper klipps automatiskt vid fel användningsform

- **Rättat:** en egenskapsyta som ritats över två användningsytor innan båda fått sin bestämmelse, där den ena sedan
  fick en annan användningsform (t.ex. allmän plats) än egenskapens bestämmelse (t.ex. kvartersmark), klipps nu
  automatiskt till den del som fortfarande ligger på rätt form. Tidigare visades bara en varning och egenskapen
  låg kvar oförändrad över båda ytorna.
- Ligger egenskapen helt på fel användningsform (inget giltigt kvar att klippa till) lämnas den orörd som förut, och
  syns i *Kontrollera planen*.

## [0.1.21] – rätt yta markeras, längre ledlinje

- **Rättat:** *Visa i kartan* för "planområdet saknar användning" markerade alltid hela (det först ritade)
  planområdet, inte den del som faktiskt saknade användning. Med flera planområden kunde det till och med peka på
  fel planområde. Nu markeras den exakta, felande delen, och rätt planområde när det finns flera.
- Ledlinjen som ritas när en bestämmelses text dragits utanför sin yta slutar nu längre in i ytan (3,5 mm i stället
  för 1,5 mm på papperet i referensskalan).

## [0.1.20] – importknapp i verktygsfältet

- **Importera leverans (JSON)** finns nu också som ikon i verktygsfältet, bredvid *Ny detaljplan* och *Öppna*, inte
  bara i menyn.

## [0.1.19] – importera en leverans (JSON)

- Ny meny-post **Importera leverans (JSON)…**: skapar en ny detaljplan från en leverans i Lantmäteriets JSON-format
  (samma form som pluginet exporterar, Nationell informationsspecifikation Detaljplan 4.1). Filen kan komma från ett
  annat verktyg, t.ex. ArcGIS Pro, så länge den följer specifikationens struktur.
- Planområdet, användnings- och egenskapsytorna (med sina bestämmelser, motiv och eventuella egen formulering),
  beslutsinformationen och handlingarna läses in. Bestämmelser vars katalogreferens inte finns i den laddade
  planbestämmelsekatalogen kan inte tolkas: ytan skapas ändå utan den bestämmelsen, och det listas i meddelandefältet.
- Har leveransen fler än ett beslut importeras bara det första (bara en rad kan redigeras i pluginet ännu).

## [0.1.18] – ledlinjen slutar inne i ytan

- Ledlinjen som ritas när en bestämmelses text dragits utanför sin yta slutar nu en bit inne i ytan (1,5 mm på
  papperet) i stället för på begränsningslinjen. Är ytan smal slutar den högst vid ytans mitt.

## [0.1.17] – enklare sparfråga

- Frågan när man avslutar redigeringen (spara eller kasta) visar inte längre en lista över vad som återstår före
  leverans till NGP eller laga kraft. Det syns redan i *Planens uppgifter* och i kontrollen mot NGP.

## [0.1.16] – handlingar enligt specifikationen

- Kraven på handlingar följer nu Lantmäteriets specifikation (Nationell informationsspecifikation Detaljplan 4.1):
  vid laga kraft krävs en planbeskrivning (DP-0005) och minst en beslutshandling som **innehåller** plankartan
  (DP-0014, DP-0017). Före laga kraft är de valfria men saknas de visas en varning (tidigare fel).
- En beslutshandling kan ha flera innehåll (plankarta, beslutsprotokoll, övrigt), som specifikationen tillåter: ett
  protokoll som också innehåller plankartan räcker vid laga kraft. Äldre planer med ett enda värde läses som förut.
- Felkoderna är rättade: saknad planbeskrivning är DP-0005 och saknad plankarta DP-0014 (tidigare DP-0005 för båda).

## [0.1.15] – delade ytor behåller bestämmelserna, kalender, krav på handlingar

- Delas en yta (t.ex. en användningsyta) behåller nu **båda delarna ytans bestämmelser**; tidigare följde bara
  egenskapsbestämmelserna med. Den nya delen får kopior med egna identiteter.
- **Markera** och **Text** är gråa när ingen redigeringssession pågår (och släpps när redigeringen avslutas).
- Alla **datumrutor** har en kalenderknapp som öppnar en kalender att välja datum i. I rutan för laga kraft läggs det
  valda datumet till efter de som redan står där.
- **Planbeskrivning och beslutshandling** (vanligtvis plankartan) krävs för leverans till NGP: de saknas i
  checklistan och i *Kontrollera planen* (fel). När status är laga kraft får fliken *Handlingar* ett kryss tills
  beslutshandlingen är plankartan.

## [0.1.14] – motiv till planbestämmelser i Planens uppgifter

- Ny flik **Motiv till planbestämmelser** i *Planens uppgifter*: alla använda planbestämmelser listas (en rad per
  bestämmelse) och motivet fylls i på ett ställe. Motivet gäller alla ytor som har bestämmelsen, och en bestämmelse
  som läggs på en ny yta får det motiv som redan finns.
- Motivet krävs först vid laga kraft: då blir tomma motiv gula och fliken får ett kryss. Sparandet blockeras aldrig.
- Motivrutan är borttagen ur *Välj planbestämmelse*, och knappen heter nu *Anpassa formulering…*. Ändrar man värdena
  på en bestämmelse behåller den sitt motiv.

## [0.1.13] – delning följer hierarkin

- Delar man en användningsyta med QGIS delaverktyg delas nu även egenskapsytor och egenskapslinjer som ligger på båda
  sidor om delningen, så att varje del hör till användningen på sin sida. Delar man ett planområde delas användningar,
  egenskapsytor och egenskapslinjer på samma sätt. Delarna av en egenskap behåller sina bestämmelser.
- En del av ett delat planområde är ett eget planområde med egen identitet.

## [0.1.12] – sekundär egenskapsgräns

- Ny knapp för **sekundära egenskapsområden**. De avgränsas med sekundär egenskapsgräns (streck och plustecken enligt
  Boverkets allmänna råd BFS 2020:6), som får korsa en vanlig egenskapsgräns utan att påverka den.
- Sammanfaller en sekundär och en vanlig egenskapsgräns ritas de ovanpå varandra (tidigare dolde en gräns den andra);
  sammanfaller de med en användningsgräns ritas bara användningsgränsen.
- Bestämmelser på sekundära egenskapsområden levereras till NGP med `sekundarEgenskapsgrans`, och *Sekundär
  egenskapsgräns* kommer med bland gränslinjerna i teckenförklaringen när planen har sådana.

## [0.1.11] – egenskapstexter inom sin yta och omformbara textrutor

- Egenskapsbestämmelsernas text placeras i första hand inom den egna egenskapsytan och radbryts efter ytans bredd, men
  lägger sig inte över användningens text (tidigare hamnade den en bit under användningens text, ofta utanför ytan).
- Med textverktyget kan textrutan för en egenskapsbestämmelse omformas: markera texten och dra i ett av hörnen.
  Texten radbryts efter rutans bredd. Bokstävernas storlek ändras aldrig av verktyget, bara i skalningsinställningarna.
- Planer får schemaversion 7 (två nya fält för textens bredd och för sekundär egenskapsgräns). Äldre planer uppgraderas
  automatiskt när de öppnas.

## [0.1.10] – ny topologikontroll, genomförandetid högst 15 år, sparande

- **Topologikontrollen** är grå medan en redigering pågår (den görs på den sparade planen) och dialogen har fått samma
  utseende som *Kontrollera planen*: en lista med fel och varningar, utan förklaringstext överst. Förslagen på
  ändringar av brytpunkter och glapp står i listan (ikryssade); planområde utan användning visas som fel och kvartersmark
  utan egenskapsområden som varning.
- **Genomförandetiden** kan högst vara 15 år (180 månader); högre värden går inte att välja.
- **Rättat:** efter att man sparat startade pluginet om redigeringen av användningsytorna och nollställde texternas
  läge, så man behövde spara flera gånger. Nu räcker en gång och texternas läge finns kvar.

## [0.1.9] – flera planområden

- En plan kan ha flera separata planområden. Ett nytt planområde läggs inte längre in i det första utan är en egen yta
  som hör till samma plan (samma uppgifter) och kan markeras och tas bort för sig. Överlapp med ett befintligt
  planområde klipps bort; en yta helt inom ett befintligt planområde tas bort.
- Tas ett av flera planområden bort försvinner eller beskärs användningarna som låg på det (och därmed deras
  egenskaper och bestämmelser); resten av planen påverkas inte.
- Leveransen är fortfarande en plan, med planområdena som delar av dess geometri.

## [0.1.8] – datum försvinner inte längre, obligatoriska rutor är gula

- **Rättat:** ett sparat datum (t.ex. *Datum påbörjat*) visades efter nästa sparande som en obegriplig kod i rutan och
  hindrade sparande. Datumen läses nu in som ÅÅÅÅ-MM-DD, även för datum på handlingar.
- Obligatoriska rutor i *Planens uppgifter* (kommun, namn, syfte, genomförandetid, datum påbörjat) är gula tills de
  fyllts i och har en röd asterisk vid namnet. Ett felskrivet datum får en svagt röd ruta.
- *Datum påbörjat* finns nu i checklistan inför leverans.

## [0.1.7] – bättre sökning och mindre rutor i Tilldela bestämmelser

- Sökrutan för att välja bestämmelse hittar nu ord var som helst i texten, inte bara det första, och flera ord i
  valfri ordning (t.ex. "byggnad mark" hittar "Marken får inte förses med byggnad"). Rubriker visas aldrig som
  sökträffar.
- Förslagslistan och rullistan är bredare, så långa bestämmelsetexter inte klipps av, och fler rader syns utan att
  behöva rulla.
- Rutan med redan tilldelade bestämmelser är mindre; en rullist syns bara om den behövs.

## [0.1.6] – rektangelmarkering, klickbar fyllning och rörlig text

- **Markera** kan nu även dra en rektangel för att markera flera ytor/linjer på en gång. Ctrl-klick fungerar nu som
  Skift-klick för att lägga till i markeringen, och högerklick avmarkerar allt. Knappen *Avmarkera alla* är borttagen
  (räcker inte längre ett syfte).
- **Fyll resten** för användning är nu ett klickverktyg precis som för egenskapsytor: klicka i den del av planområdet
  som saknar användning. Är det uppdelat i flera skilda bitar fylls bara den du klickar i.
- **Fyll resten** och **Planbestämmelser** stänger nu av sig själva när de använts en gång; man behöver inte längre
  klicka på knappen igen för att sluta.
- **Bestämmelsernas text** kan flyttas utanför sin yta. Gör den det ritas automatiskt en tunn, svart ledlinje till
  ytan.

## [0.1.5] – topologikontrollen är tillbaka

- Knappen för topologikontroll finns i verktygsfältet igen: föreslår att flytta brytpunkter till planområdets eller
  varandras brytpunkter, och stänger små glapp mellan gränser – även mellan en egenskapsyta och den användning den
  ligger på (den vanligaste orsaken till att en gräns ser olika tjock ut på olika ställen i kartan).
- Dialogen visar nu också om hela planområdet har en användning, med en knapp som fyller det som saknas.

## [0.1.4] – borttagning följer hierarkin

- Tar du bort planområdet försvinner alla användningsytor, egenskaper och bestämmelser. Tar du bort en användningsyta försvinner egenskaperna på den och deras bestämmelser; en egenskap som ligger på flera användningar beskärs till det som finns kvar. Meddelandefältet berättar vad som togs bort.

## [0.1.3] – ett namn på verktygsfältet

- Menyposten som visar och döljer verktygsfältet, och verktygsfältets namn i QGIS lista över verktygsfält, heter bara *Rita Detaljplan*.

## [0.1.2] – namn på verktygsfälten

- Verktygsfältet i kartvyn heter nu *Rita Detaljplan* (tidigare *Planbestämmelser*).
- Verktygsfältet i layoutdesignern och dess post i *Visa*-menyn heter *Rita Detaljplan* (tidigare *Verktygsfält för Rita Detaljplan*).

## [0.1.1] – metadata för QGIS pluginförråd

- Beskrivningen i `metadata.txt` är på engelska och e-postadress har lagts till, vilket QGIS pluginförråd kräver.
- Ingen ändring av funktionen.

## [0.1.0] – första publika versionen

Tidig utvecklingsversion (experimentell). Pluginet hette tidigare *Detaljplan NGP*.

### Ritande och bestämmelser
- Ny detaljplan i lokal GeoPackage eller PostGIS-schema (SWEREF 99), med QGIS-projekt och snappning.
- Hierarki planområde → användning → egenskap med regler som beskär och kontrollerar ytor medan man ritar.
- Fyllverktyg, markeringsverktyg (med Avmarkera alla), textverktyg för bestämmelsernas etiketter, referensskala.
- Bestämmelseväljare mot Boverkets planbestämmelsekatalog (medföljande kopia, kan uppdateras), flera bestämmelser per yta,
  automatiska beteckningar.
- Symbologi enligt Boverkets föreskrifter, inklusive fastighetsindelning, prickmark, plusmark och ringprickad mark.
- Planens uppgifter i en dialog: plan, beslut och handlingar. Genomförandetid är obligatorisk.

### Kontroll och leverans
- Validering mot Lantmäteriets regler (fel, varningar, sådant som återstår) med hopp till felet i kartan.
- Export av leveransen enligt detaljplan 4.1 och uppladdning via Uppdatering-API:et (**ej provad mot riktig miljö**).

### Teckenförklaring
- Skapas i QGIS layoutläge från planens bestämmelser, med genomförandetid sist.
- Inställningar för teckensnitt, storlekar, rutor och avstånd. Eget, stängbart verktygsfält i layoutdesignern.

### Databas
- Utcheckning och incheckning av databasplaner med lås och lokal kopia (**ej provad mot riktig databas**).

### Kända brister
Se [docs/kanda-begransningar.md](docs/kanda-begransningar.md).

[0.1.25]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.25
[0.1.24]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.24
[0.1.23]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.23
[0.1.22]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.22
[0.1.21]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.21
[0.1.20]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.20
[0.1.19]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.19
[0.1.18]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.18
[0.1.17]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.17
[0.1.16]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.16
[0.1.15]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.15
[0.1.14]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.14
[0.1.13]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.13
[0.1.12]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.12
[0.1.11]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.11
[0.1.10]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.10
[0.1.9]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.9
[0.1.8]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.8
[0.1.7]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.7
[0.1.6]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.6
[0.1.5]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.5
[0.1.4]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.4
[0.1.3]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.3
[0.1.2]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.2
[0.1.1]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.1
[0.1.0]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.0
