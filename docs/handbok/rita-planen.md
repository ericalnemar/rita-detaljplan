# Rita planen

Planen ritas i en bestämd ordning: först planområdet, sedan användningsområden och sist egenskapsområden. Pluginet
håller ordning på hierarkin åt dig medan du ritar.

<!-- FILM: rita-planen | Rita planområde, användningsområden och egenskapsområden, ca 4 min -->

## Börja och avsluta redigeringen

1. Klicka på **pennan** (*Börja rita planbestämmelser*). Alla planlager öppnas för redigering. Är flera planer
   laddade får du först välja vilken du vill redigera.
2. Rita och tilldela bestämmelser.
3. Klicka på **disketten** (*Avsluta redigering*). Du får välja om ändringarna ska sparas eller kastas.

När du avslutar körs en kontroll av planen och checklistan i *Planens uppgifter* visas, så att du ser vad som återstår.
Sparandet stoppas aldrig av att något saknas.

## Ordningen: planområde → användning → egenskap

Ritknapparna är gråa tills det som ska ligga under finns. Håll muspekaren över en grå knapp för att se varför.

<!-- BILD: hierarki.png | Planområde, användningsområden och egenskapsområden ovanpå varandra -->

### 1. Planområde

Planområdet är planens yttre gräns.

- En plan kan ha **flera planområden**, till exempel två skilda ytor. De hör till samma plan och delar uppgifter.
- Planområden får inte överlappa varandra. Det som överlappar klipps bort.
- När du ritat det första planområdet öppnas *Planens uppgifter*, där du fyller i namn, syfte, status med mera.

### 2. Användningsområde

- Kräver ett planområde.
- Det som hamnar utanför planområdet klipps bort.
- Användningsområden får inte överlappa varandra. Det som överlappar klipps bort.

### 3. Egenskapsområde

- Kräver ett användningsområde. Det som hamnar utanför användningen klipps bort.
- Egenskapsområden **får** överlappa varandra.
- Ett egenskapsområde kan ligga över flera användningsområden, men bara om de har samma **användningsform** som
  egenskapens bestämmelse: kvartersmark, allmän plats eller vattenområde.

Pluginet klipper egenskapsområdet så att det hamnar rätt:

- Ritar du en egenskapsyta på allmän plats lite för stor, så att den når in på kvartersmark, klipps den till
  allmän plats.
- Har ytan ännu ingen bestämmelse och ligger över användningar med olika form, klipps den till den form där största
  delen av ytan ligger.
- Får en användning under egenskapen senare en annan form än bestämmelsen kräver, klipps egenskapen till den del som
  fortfarande ligger rätt. Ligger den helt fel lämnas den orörd och visas i *Kontrollera planen*.

### Sekundärt egenskapsområde

Ritas som ett vanligt egenskapsområde men avgränsas med **sekundär egenskapsgräns** (streck och plustecken, enligt
Boverkets allmänna råd BFS 2020:6, 3.3). Använd det när ett område ska korsa vanliga egenskapsgränser, till exempel ett
markreservat som skär genom ett område där byggnadshöjden regleras.

- Sammanfaller en sekundär och en vanlig egenskapsgräns ritas båda ovanpå varandra.
- Sammanfaller den med en användningsgräns ritas bara användningsgränsen.
- Gränsen kommer med i teckenförklaringen.

### Egenskapslinje

Bara för **utfartsförbud** och **stängsel**. Ritas på en användningsyta.

### Egenskapspunkt

För bestämmelser som gäller i en punkt, framför allt **markens höjd över (eller under) nollplanet**.

1. Klicka på **Rita egenskapspunkt** (en punkt med texten +0,0).
2. Klicka i kartan där höjden gäller. Punkten måste ligga på en användningsyta, annars tas den bort.
3. Ge punkten en bestämmelse med **Planbestämmelser**, till exempel *Markens höjd över nollplanet ska vara … meter*,
   och fyll i höjden.

På kartan visas punkten som en liten svart prick med höjden bredvid, till exempel **+31,8**. Under nollplanet visas
höjden med minustecken. I teckenförklaringen blir alla höjder en enda rad: **+0,0 Markens höjd över nollplanet**.

<!-- BILD: egenskapspunkt.png | En egenskapspunkt med höjden +31,8 på kvartersmark -->

### Hur gränserna ritas

Där linjer sammanfaller ritas bara den högsta i hierarkin: planområdesgräns före användningsgräns före
egenskapsgräns. Då blir det inga dubbla linjer.

- Ytor som saknar bestämmelse ritas med **rött snedstreck**.
- Statusraden längst ned visar planområdets storlek, hur stor del som har en användning och hur många ytor som saknar
  bestämmelse.

## Fyll resten

Med **Fyll användning** och **Fyll egenskap** fyller du det som saknas med ett klick, i stället för att rita det.

1. Klicka på **Fyll användning**.
2. Klicka i en del av planområdet som saknar användning. Den sammanhängande delen fylls med ett nytt
   användningsområde.
3. Verktyget stänger av sig självt efter klicket.

**Fyll egenskap** fungerar på samma sätt för den del av ett användningsområde som saknar egenskapsyta.

Ligger det som saknas i flera skilda bitar fyller du en bit per klick. Ge sedan ytorna bestämmelser som vanligt.

<!-- FILM: fyll-resten | Fyll resten av planområdet med användning, ca 1 min -->

## Ta bort något

Det som ligger under i hierarkin försvinner när du tar bort det som ligger över:

| Du tar bort | Det här försvinner också |
|---|---|
| Ett planområde | Användningsytor, egenskaper och bestämmelser på det. |
| Ett användningsområde | Egenskaperna på det och deras bestämmelser. En egenskap som ligger på flera användningar behåller delen som ligger på dem som finns kvar. |
| Ett egenskapsområde | Bara egenskapen och dess bestämmelser. |

Hjälplagren påverkas aldrig. Meddelandefältet berättar vad som togs bort. Ångrar du dig kan du kasta redigeringen.

## Dela en yta

Delar du en yta med QGIS delaverktyg (**Dela objekt**) behåller båda delarna ytans bestämmelser. Det som ligger under i
hierarkin delas på samma ställe:

- Delar du ett användningsområde delas egenskapsområden och egenskapslinjer som korsar delningen.
- Delar du planområdet delas användningar, egenskapsområden och egenskapslinjer.

Meddelandefältet berättar vad som delades.

## Hjälplager

Överst i planens grupp finns tre hjälplager: **Hjälppunkter**, **Hjälplinjer** och **Hjälpytor**. Använd dem för
konstruktionslinjer och referenser.

- De ritas fritt och klipps aldrig.
- De påverkas inte av hierarkin.
- De följer **aldrig** med i leveransen till NGP.

Knappen för hjälplinje har en pil. Klicka på pilen för att välja **hjälpyta** eller **hjälppunkt**. Knappen byter då
ikon och ritar med det du valde senast.

### Gör ett hjälpobjekt till ett planobjekt

1. Klicka på en hjälpyta, hjälplinje eller hjälppunkt med verktyget **Planbestämmelser**.
2. Välj en bestämmelse.
3. Objektet **flyttas** till rätt planlager: en hjälpyta blir en användnings- eller egenskapsyta, en hjälplinje blir
   en egenskapslinje och en hjälppunkt en egenskapspunkt.

Har du höjder i en inmätning eller DWG kan du alltså importera dem som hjälppunkter (se nedan) och sedan ge dem
höjdbestämmelsen en i taget.

Samma regler gäller som när du ritar, så ytan kan klippas. Går det inte, till exempel för att ytan ligger utanför
planområdet, får du en förklaring och hjälpobjektet ligger kvar. Markerar du flera hjälpobjekt kan de få samma
bestämmelse på en gång.

## Importera geometrier

Har du underlag i ett annat format, till exempel en DWG från en konsult, kan du hämta in geometrierna till
hjälplagren.

1. Klicka på **Importera geometrier** (lådan med pil nedåt) eller välj **Rita Detaljplan → Importera geometrier…**.
2. Välj ett lager som redan finns i QGIS, eller lägg till en datakälla i dialogen: GeoPackage, Shape, DWG/DXF,
   databaser, WFS med flera.
3. Kryssa i **Bara markerade objekt** om du bara vill ta med det du markerat i källan.
4. Starta importen.

<!-- BILD: importera-geometrier.png | Dialogen Importera geometrier med en DWG-fil vald -->

Det här händer:

- Bara **geometrin** följer med, inga attribut.
- Ytor hamnar i *Hjälpytor*, linjer i *Hjälplinjer* och punkter i *Hjälppunkter*.
- Geometrin omvandlas till planens koordinatsystem, kurvor görs raka och höjdvärden tas bort.
- Källan ändras inte.

Spara med **Avsluta redigering**, eller ångra med Ctrl+Z i lagret.

## Rita exakt

När du börjar rita slås snappning på automatiskt, även mot korsningar där två linjer korsar varandra utan gemensam
punkt. QGIS panel *Avancerad digitalisering* slås också på.

- **Längd och vinkel:** rutorna för längd och vinkel följer muspekaren, som i AutoCAD. Tryck **Tab** för att växla
  mellan dem och skriv för att ändra värdet.
- **Parallell / Vinkelrätt:** slå på läget och snappa mot en befintlig linje medan du ritar. QGIS låser då vinkeln mot
  den linjen.
- **Spårning:** ritar automatiskt längs kanter som redan finns, fram till nästa snappade punkt.

## Markera och flytta texter

**Markera** (pilen) markerar ytor och linjer, oavsett vilket lager som är valt i lagerpanelen.

- Klicka för att markera en yta, eller dra en rektangel för att markera allt den rör vid.
- Ligger flera ytor på varandra får du välja vilken du menar.
- **Ctrl-klick** eller **Skift-klick** lägger till i markeringen.
- **Högerklick** eller **Avmarkera alla** tar bort markeringen.

Det markerade lagret blir aktivt, så att du direkt kan flytta, redigera brytpunkter eller radera.

**Text** (bokstaven A med en ram) markerar och flyttar bestämmelsernas texter:

1. Klicka på en text, eller dra en rektangel.
2. Dra den markerade texten dit du vill ha den. Alla markerade texter flyttas lika långt.
3. Flyttar du en text utanför sin yta ritas en tunn ledlinje in i ytan.
4. Dra i ett hörn på en egenskapstext för att ändra textrutans form. Texten radbryts efter den nya bredden.

Tryck **Delete** för att återställa automatisk placering och **Esc** för att avmarkera. Textstorleken ändras inte här,
utan styrs av referensskalan (se [Planens uppgifter](planens-uppgifter.md#referensskala)).

**Dölj texter** (A med ett rött streck) stänger tillfälligt av beteckningarna på kartan när de är i vägen.
Klicka igen för att visa dem.

<!-- FILM: flytta-texter | Markera, flytta och forma om bestämmelsetexter, ca 1 min -->

## Nästa steg

Fortsätt med [Bestämmelser](bestammelser.md).
