# Ändringslogg

Formatet följer [Keep a Changelog](https://keepachangelog.com/sv/1.1.0/), versionsnumren [Semantic Versioning](https://semver.org/lang/sv/).

## Ej utgivet

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
