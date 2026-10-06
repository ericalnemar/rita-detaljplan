# Användarhandledning – Rita Detaljplan

Så här arbetar du med pluginet, moment för moment. Ny här? Börja med snabbstarten i [README](../README.md).
Det som inte är provat mot riktiga system står under [Kända begränsningar](kanda-begransningar.md).

## Arbetsflödet

1. **Rita Detaljplan → Ny detaljplan…** skapar planen och ett QGIS-projekt (SWEREF 99, snappning påslagen), och lägger
   bara till planens eget grupplager i den redan öppna kartan – andra lager (t.ex. en grundkarta) rörs inte. Har
   den öppna kartan aldrig sparats (du började t.ex. med ett tomt, nystartat QGIS) sparas den nu automatiskt som
   den nya projektfilen, så att grundkartan och allt annat hänger med i samma fil; är kartan redan sparad som
   något annat rörs den filen inte – planens egen projektfil skapas då ändå, men bredvid, inte i stället. Flera
   planer kan vara laddade samtidigt (**Öppna** lägger till i stället för att ersätta); den senast skapade/öppnade
   blir aktiv, och pluginets verktyg (rita, tilldela bestämmelser, kontrollera, leverera) jobbar bara mot den
   aktiva – syns i QGIS egen fönstertitel och i statusraden så fort fler än en plan är laddad. Dialogerna Planens
   uppgifter, Topologikontroll, Kontrollera planen och Leverera till NGP har dessutom en egen rad "Aktiv plan" med
   en lista att byta plan direkt i dialogen (bara synlig när det finns fler än en att välja mellan). Är fler än
   en laddad frågar **pennan** vilken som ska redigeras; vill man byta aktiv plan utan att redigera används
   **Rita Detaljplan → Byt aktiv plan…**. **Rita Detaljplan → Stäng aktiv plan** tar bort den aktiva planens
   lager ur projektet igen (rör inte filen/databasen). Samma sak som Ny detaljplan gäller
   **Importera leverans (JSON)…**. Planen kan
   lagras som en **lokal GeoPackage** (standard) eller i en **PostGIS-databas**: välj då en av QGIS sparade
   PostgreSQL-anslutningar, ett **schema** (delas av flera planer – finns det redan återanvänds det, annars skapas
   det) och en **plan-id** (planens egen identifierare inom schemat, föreslås ur plannamnet). Alla planer i samma
   schema ligger i samma tabeller (en dold `plan`-kolumn skiljer dem åt) och måste därför dela koordinatsystem –
   behövs flera SWEREF 99-zoner, använd olika schemanamn för dem. Databasen måste ha PostGIS; projektfilen (.qgz)
   sparas i en mapp och pekar på databasen. *Öppna* i verktygsfältet frågar om det ska vara en fil eller en databas
   när det finns anslutningar, och (för en databas) vilket schema och sedan vilken plan i det. **Obs:** PostGIS-stödet
   är testat mot en låtsasdatabas men ännu inte mot en riktig.
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
   och innehåller även ikonerna för *Ny detaljplan* och *Öppna*, samt **Markera**, **Avmarkera alla**, **Text**
   (markera/flytta bestämmelsernas texter), **Fyll användning** och **Fyll egenskap**. Det består av ikoner;
   texten finns i verktygstipsen.
   **Ett andra verktygsfält** flyter ovanpå kartvyn, centrerat längst ned, listlöst och halvgenomskinligt – som i
   CAD-program. Syns hela tiden under en pågående redigeringssession (och bara då) – annars är den bara i vägen.
   Kan även döljas/visas helt via **Rita Detaljplan → Rita Detaljplan – fler verktyg**.
   Innehåller **Markera**, **Avmarkera alla**, **Text**, **Fyll användning** och **Fyll egenskap** (samma knappar
   som högst upp), **Dela objekt**, **Lägg till hål**, **Slå ihop valda objekt**, **Brytpunkter** (för det aktiva
   lagret),
   **Trimma/Förläng objekt**, samt **Spårning**, **Parallell** och
   **Vinkelrätt** – bokstavligen samma knappar som i QGIS egna snappningsverktygsfält respektive panelen Avancerad
   digitalisering: Parallell/Vinkelrätt aktiverar ett läge, snappa sedan mot en befintlig linje under ritningen så
   låser QGIS själv vinkeln mot den; Spårning ritar automatiskt längs redan digitaliserade kanter fram till nästa
   snappade punkt. Snappning (inklusive snappning mot korsningar, där två ritade linjer korsar utan att dela en
   nod) slås på automatiskt så fort du börjar redigera (annars fungerar varken Parallell, Vinkelrätt eller
   Spårning) – ingen egen knapp för det. Fler knappar läggs till efter hand. Övriga verktyg
   används som vanligt som knappar i verktygsfältet högst upp:
   Planbestämmelser, Börja/Avsluta redigering, Topologikontroll, NGP, Checka ut/in. QGIS egen panel Avancerad
   digitalisering aktiveras automatiskt så fort du börjar rita, med Längd och Vinkel som flytande, redigerbara
   rutor vid muspekaren, som i AutoCAD: tryck Tab för att växla mellan dem, skriv för att ändra värdet.
   Hela planen ligger i en grupp i lagerpanelen som heter som planen (först filnamnet, sedan planens namn).
2. **Pennan** öppnar alla planlager för redigering (är flera planer laddade frågas först vilken), **disketten**
   avslutar och frågar om ändringarna ska sparas.
3. **Rita geometrin i hierarkisk ordning.** Knapparna är gråa, med förklaring i verktygstipset, tills föräldern finns:
   - **Planområde** – planens yttre gräns. Planen kan ha flera planområden (t.ex. två skilda ytor); de hör till samma plan, delar
     uppgifter och kan markeras och tas bort var för sig. De får inte överlappa (överlappet klipps bort). Tas ett
     planområde bort försvinner eller beskärs användningen som låg på det. Efter första ytan öppnas planens
     uppgifter (namn, syfte, status …).
   - **Användningsområde** – kräver planområde. Det som ligger utanför beskärs, och användningsytor får inte
     överlappa varandra (överlappet klipps bort).
   - **Egenskapsområde** – kräver en användning. Beskärs mot användningen, får överlappa andra egenskapsområden. En
     egenskap kan ligga över flera användningsytor, men bara om de har samma användningsform (kvartersmark, allmän
     plats eller vattenområde) som egenskapens bestämmelse. Får en tidigare obestämd användning under egenskapen en
     annan form än bestämmelsen kräver, klipps egenskapen automatiskt till den del som fortfarande ligger rätt (med
     ett meddelande); ligger den helt på fel form lämnas den orörd och listas i *Kontrollera planen*. Samma klippning
     mot användningsgränsen görs när du ger en egenskapsyta en bestämmelse eller flyttar i dess hörn efteråt: ritar du
     en egenskapsyta på allmän plats lite för stor så att den når in på kvartersmark klipps den till allmän plats.
     Har ytan ännu ingen bestämmelse och ligger över användningar med olika former klipps den direkt till den form
     där största delen av ytan ligger (användningar som ännu saknar form räknas inte som en annan form).
   - **Sekundärt egenskapsområde** (egen knapp, ruta med streck och plustecken) – ritas som ett vanligt
     egenskapsområde men avgränsas med *sekundär egenskapsgräns* (streck och plustecken, Boverkets allmänna råd
     BFS 2020:6, 3.3). Den får korsa vanliga egenskapsgränser utan att påverka dem, t.ex. ett markreservat som skär
     genom ett område där byggnadshöjden regleras. Sammanfaller en sekundär och en vanlig egenskapsgräns ritas de
     ovanpå varandra; sammanfaller de med en användningsgräns ritas bara användningsgränsen. Bestämmelserna på ett
     sekundärt egenskapsområde levereras med `sekundarEgenskapsgrans` och gränsen kommer med i teckenförklaringen.
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
   fungerar) lägger till i markeringen, en dragen rektangel likaså. Högerklick, eller knappen *Avmarkera alla*
   bredvid, avmarkerar allt. Det markerade lagret blir aktivt så att flytta, nodverktyg och radera fungerar direkt.
   **Text** (bokstaven A med en markeringsram) markerar bestämmelsernas texter: klicka på en text, eller tryck ned
   musknappen på tomt ställe och dra en rektangel. Dra en markerad text för att flytta den (alla markerade flyttas
   lika långt). Texten kan flyttas utanför sin yta: gör den det ritas automatiskt en tunn, svart ledlinje som slutar en bit inne i ytan
   (inte på gränslinjen).
   Egenskapsbestämmelsernas text placeras i första hand inom sin egen yta, radbruten efter ytans bredd, och lägger
   sig inte över användningens text. En markerad egenskapstext har fyra handtag (hörnen): dra i ett hörn för att
   omforma textrutan; texten radbryts då efter rutans nya bredd. Bokstävernas storlek påverkas aldrig av det, den
   ställs bara in i skalningsinställningarna.
   Delete återställer till automatisk placering och form och Esc avmarkerar. *Markera*, *Avmarkera alla* och *Text*
   är gråa när ingen redigeringssession pågår (börja med pennan).
   Delar du en yta med QGIS delaverktyg behåller båda delarna ytans bestämmelser (den nya delen får kopior, med
   egna identiteter). Allt med lägre hierarki som ligger på båda sidor om delningen delas på samma
   ställe: delar du ett användningsområde delas egenskapsområden och egenskapslinjer som korsar delningen, så att varje
   del hör till användningen på sin sida; delar du planområdet delas användningar, egenskapsområden och egenskapslinjer
   på samma sätt. Delarna av en egenskap eller användning behåller sina bestämmelser. Meddelandefältet berättar vad
   som delades.
4. **Tilldela bestämmelser** med verktyget längst till höger: klicka på en yta. Verktyget stänger av sig själv när
   dialogen stängts; du behöver inte stänga av det för hand (samma sak gäller *Fyll resten* ovan).
   - Ligger flera ytor på varandra (t.ex. ett egenskapsområde över en användning) väljer du vilken yta det gäller;
     den valda ytan markeras i kartan.
   - Välj bestämmelse i den sökbara rullistan (den visar bara bestämmelser som passar ytan: rätt typ och rätt
     användningsform, uppdelade med rubriker som *Användningsbestämmelser – Kvartersmark* och en underrubrik per
     kategori). Sökrutan hittar ord var som helst i texten, inte bara det första, och flera ord i valfri ordning
     (skriv t.ex. "byggnad mark" för att hitta "Marken får inte förses med byggnad"); förslagslistan är bred så att
     långa bestämmelsetexter inte klipps av. Fyll i eventuella värden (t.ex. `30 %`, med värdetyp och enhet
     förifyllda) och klicka *Lägg till*. För bestämmelser där katalogens beteckning är en mall (t.ex.
     *Utformning av områden för dagvatten – annan*, `[beteckning:text]#`) finns också fältet *Beteckning på
     plankartan*: skriv bara bokstäverna själv (Dv), siffran läggs på automatiskt (Dv1; siffror du skriver sist tas bort)
     och en annan beteckning numreras för sig. Man kan lägga till flera: en användningsyta kan ha flera användningar (`BC`)
     och ett egenskapsområde flera egenskaper (`e1 a2`). Beteckningen skrivs inom polygonen. Rutan för redan
     tilldelade bestämmelser växer med dialogrutan (en rullist syns bara om det blir fler än den rymmer). Vill du
     använda en bestämmelse som redan finns på en annan yta i planen väljer du den i rullistan *Använd en
     bestämmelse som redan finns i planen* och klickar *Lägg till*: den får då samma text, värden och beteckning.
     En beteckning (t.ex. `f1`) hör till exakt en bestämmelse i hela planen; samma bestämmelse får samma beteckning
     överallt och en annan bestämmelse nästa lediga siffra, oavsett vilken yta den ligger på.
   - *Anpassa formulering…* låter dig anpassa ordalydelsen (med varning om att den då avviker från katalogen).
     Motivet skrivs inte här utan på fliken *Motiv till planbestämmelser* i *Planens uppgifter* (se nedan).
     *Ändra…* och *Ta bort* hanterar redan tilldelade bestämmelser (*Ändra…* öppnar samma dialog som vid tillägg,
     så formuleringen kan anpassas där också), och pilarna ▲ ▼ flyttar en bestämmelse upp eller ned i ordningen.
     Ordningen styr ordningen i beteckningen (BC eller CB) och att den första bestämmelsens färg och symbol visas
     – däremot inte indexsiffran i en beteckning som F1/F2 (den sätts när bestämmelsen läggs till och kan då bli
     omvänd mot listans ordning); *Indexera om* numrerar om siffrorna så att de följer listans nuvarande ordning.
     *Kvalitet…* öppnar bestämmelsens egen kvalitetsbeskrivning och användbarhet (samma fält som fliken *Kvalitet*
     i *Planens uppgifter*, se 5) – krävs vid laga kraft, för varje bestämmelse. *Reglerar annan plan…* (bara för
     egenskapsbestämmelser) anger att bestämmelsen reglerar (hör ihop med) en annan detaljplan, t.ex. vid
     samordning mellan grannplaner – välj bland andra laddade planer eller skriv in identiteten (UUID) direkt om
     planen inte är laddad här. Valfritt.
   Rullistan visar bara bestämmelser som passar det som ligger under: en egenskapsyta på kvartersmark får bara
   kvartersmarkens egenskaper och en på allmän plats bara allmän plats (bekräftas i en rad under rullistan).
   Du skriver aldrig UUID eller tekniska fält.
   **Referensskala:** linjer och texter dimensioneras för en fast skala (1:1000 som standard; ändra på fliken *Plan* i
   *Planens uppgifter*, under *Visning i kartan*), så att de inte blir orimligt tjocka eller tunna när du zoomar. Användningens text
   är alltid tydligt större än egenskapernas, som placeras under den.
5. **Planens uppgifter** (ikonen med kryssrutan) visar en checklista över vad som krävs före leverans: kommun, namn,
   syfte, status och plantyp (markerade med *), att planområdet är ritat, att användningsytorna täcker hela
   planområdet och att alla ytor har bestämmelse. Sparande blockeras aldrig; checklistan visas också när du
   avslutar redigeringen så att du ser vad som återstår.
   **Fliken Kvalitet** har planens kvalitetsbeskrivning (digitaliseringsnivå, beskrivning av nivå, korrigerade
   gränser, kontrollerat planeringsunderlag) och användbarhet (med beskrivning) – enligt Nationell
   informationsspecifikation Detaljplan 4.1. Digitaliseringsnivå och användbarhet krävs vid laga kraft (markerade
   med *, ingår i checklistan) men är förifyllda med *komplett* respektive *god* (det vanliga: planen ritas
   direkt i rätt lägesnoggrannhet, inte digitaliserad från ett sämre underlag) – ändra bara om det inte stämmer.
   Övriga är valfria och tomma. Varje bestämmelse har sin egen, likaledes förifylld, i tilldelningsdialogen
   (*Kvalitet…*, se 4).
6. **Kontrollera planen** (knappen *Kontrollera planen…* i NGP-dialogen, se 8) granskar planen mot Lantmäteriets regler (se
   [ngp-regler.md](ngp-regler.md)) och listar avvikelser som *fel* (stoppar leveransen), *varningar* och
   *att fylla i*. Dubbelklicka på en rad för att markera ytan och zooma till den. Kontrollen körs också när du sparar
   och avslutar redigeringen (resultatet visas i meddelandefältet). Den kontrollerar bland annat att hela planområdet
   har användning (DP-0002/0003), överlapp, glapp och smala ytor (DP-Krav-0011–0014), självkorsande gränser
   (DP-Krav-0018), att egenskaper ligger inom användningen och har rätt användningsform, att varje bestämmelse har rätt
   värden, värdetyp och enhet (DP-0022/0009), tekniska anläggningar (DP-0019/0020), att osäkert läge inte anges
   (DP-0010) samt kraven vid laga kraft (beslutsinformation, handlingar och kvalitetsbeskrivning för plan och
   bestämmelse, se 5 och 7).
7. **Genomförandetid** är obligatorisk: varje detaljplan ska ha en. Den anges (i år eller månader, 5–15 år enligt PBL
   4 kap. 21 §) på fliken *Plan* i *Planens uppgifter*, ingår i checklistan, ger stoppande fel vid validering om den saknas
   och skrivs ut längst ner i teckenförklaringen.
   **Motiv till planbestämmelser** är en flik i samma dialog. Den listar alla använda planbestämmelser (en rad per
   bestämmelse, även om den ligger på flera ytor) och du skriver motivet (planbestämmelsebeskrivningen) för den
   markerade. Motivet gäller alla ytor som har bestämmelsen, och läggs du till samma bestämmelse på en ny yta får
   den motivet direkt. Det krävs först vid laga kraft: när status är *laga kraft* blir tomma motiv gula och fliken
   får ett kryss. Före dess kan du fylla i dem när som helst; sparandet blockeras aldrig. För *Tekniska
   anläggningar* är motivet fast.
   **Beslut och handlingar** ligger som flikar i samma dialog som *Planens uppgifter* (en enda knapp). Fliken *Beslut*
   har beslutsinformationen (instans, beslutstyp, diarienummer, datum för påbörjat, antagande och laga kraft,
   …) och fliken *Handlingar* planbeskrivning, beslutshandlingar (plankarta, protokoll) och
   planeringsunderlag, med namn, datum, händelse och länk (https). Referensidentiteten för en handling sätts när den
   laddats upp till NGP (steg 5). **Enligt specifikationen krävs vid laga kraft en planbeskrivning (DP-0005) och minst en beslutshandling som
   innehåller plankartan (DP-0014, DP-0017)**. En beslutshandling kan innehålla flera saker (plankarta,
   beslutsprotokoll och/eller övrigt, t.ex. laga kraftbevis): kryssa i dem som stämmer, så räcker ett protokoll som
   också innehåller plankartan. Före laga kraft är handlingarna valfria för NGP, men saknas de visas en varning i
   *Kontrollera planen*, en not på fliken *Handlingar* och en rad i checklistan. Vid laga kraft är det fel som
   stoppar leveransen, och fliken får ett kryss tills kraven är uppfyllda. Alla
   datumrutor har en kalenderknapp till höger som öppnar en kalender att välja datum i. Felskrivna datum blockerar sparandet (rutan blir svagt röd); saknade uppgifter gör det
   aldrig. Obligatoriska rutor som är tomma (kommun, namn, syfte, genomförandetid, datum påbörjat) är gula och har en
   röd asterisk vid namnet; de blir vita när de fyllts i.
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
9. **Teckenförklaring** skapas i QGIS layoutläge, inte i huvudverktygsfältet: öppna en layout och tryck på knappen
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
10. **Topologikontroll** (brytpunkter med en cirkel) analyserar planen och föreslår ändringar av brytpunkter och små
   glapp: att en brytpunkt i en användnings- eller egenskapsyta som ligger nära (men inte exakt på) planområdets eller
   en annan ytas brytpunkt eller gräns flyttas dit, att planområdets brytpunkter läggs till i användningen där de
   saknas, och att glapp mellan ytor i samma lager stängs (den senare ritade ytan anpassar sig till den tidigare).
   Det är precis det som gör att en gräns annars kan se olika tjock ut på olika ställen: två nästan men inte exakt
   sammanfallande linjer ritas båda, i stället för att den ena döljs som den ska när de ligger på varandra. Du väljer
   tolerans och vilka förslag som ska göras (markera i kartan med *Visa i kartan* innan du bestämmer dig); de valda
   ändringarna görs automatiskt i redigeringsbufferten (ett ångra-steg per lager) och sparas när redigeringen
   avslutas. Planområdet ändras aldrig. Resultatet visas som en lista på samma sätt som *Kontrollera planen*: förslagen
   (ikryssade) och avvikelserna att planområdet saknar användning (fel, med en knapp som fyller det som saknas, samma
   som *Fyll resten*), att en redan ritad yta saknar bestämmelse (fel – annars syns det bara som ett rött snedstreck i
   kartan tills man kör hela valideringen) och att kvartersmark saknar egenskapsområden (varning; det behöver inte
   vara ett fel). *Visa i kartan* för ett planområde utan användning markerar den exakta delen som saknar användning (inte hela
   planområdet), och pekar på rätt planområde när planen har flera. Knappen är grå medan en redigering pågår:
   kontrollen görs på den sparade planen.
11. **Rita Detaljplan → Importera leverans (JSON)…** (i menyn, inte i verktygsfältet) skapar en ny detaljplan
   från en leverans i Lantmäteriets
   JSON-format (samma form som pluginet självt exporterar, se Nationell informationsspecifikation Detaljplan 4.1) i
   stället för att rita den: planområdet, användnings- och egenskapsytorna med sina bestämmelser, beslutsinformationen
   och handlingarna. Filen kan komma från ett annat verktyg, t.ex. ArcGIS Pro, så länge den följer specifikationens
   struktur. Kommun och planbeteckning föreslås från filen; övrigt (mapp, koordinatsystem) väljer du som för en ny
   plan (1). Bestämmelser vars katalogreferens inte finns i den laddade planbestämmelsekatalogen kan inte tolkas: ytan
   skapas ändå, utan just den bestämmelsen, och meddelandefältet listar vad som hoppades över. Planen sparas inte
   automatiskt efter importen; klicka på disketten som vanligt.
12. **Tagga planbeskrivning** (dokumentet med en etikett, efter NGP-knappen) öppnar programmet *Tagga
   planbeskrivning* i ett eget fönster, med den aktiva planen redan vald. Programmet taggar planbeskrivningen (Word, `.docx`)
   enligt BFS 2020:8 och Lantmäteriets Planbeskrivning 2.0 i fyra steg: välj planbeskrivningen, granska de taggar som
   föreslås för varje avsnitt, koppla motiven till planens bestämmelser (kartan visar var en bestämmelse gäller), och
   kontrollera och spara. Det sparar en *leveranskopia* (bokmärken och XML-del) och en *granskningskopia* (taggarna som
   kommentarer i Word); originalet ändras aldrig. *Importera till planen* i sista steget lägger syftet och motiven ur
   planbeskrivningen på planen och dess bestämmelser (de ersätter det som stod), i redigeringsbufferten: spara planen
   som vanligt efteråt. Har du ändrat i planen medan fönstret är öppet hämtar *Läs om från QGIS* bestämmelserna igen.
   Knappen är grå tills planområdet är ritat. Programmet finns också som ett fristående program, utan QGIS.

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
