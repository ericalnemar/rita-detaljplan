# Kom igång

Här installerar du pluginet, skapar din första plan och lär känna verktygsfälten.

<!-- FILM: kom-igang | Från installation till ett ritat planområde, ca 3 min -->

## Innan du börjar

- Du behöver **QGIS 4.0 eller senare**. Pluginet är testat med QGIS 4.2.2 på Windows.
- Pluginet är en tidig version. Läs [Kända begränsningar](../kanda-begransningar.md) innan du använder det i ett
  skarpt planärende.

## Installera pluginet

Du kan installera på två sätt. Det andra sättet gör att nya versioner syns direkt i QGIS.

### Alternativ 1: från en zip-fil

1. Ladda ned `rita_detaljplan-<version>.zip` från
   [Releases](https://github.com/ritaplan/rita-detaljplan/releases).
2. Starta QGIS och välj **Tillägg → Hantera och installera tillägg… → Installera från ZIP**.
3. Peka ut zip-filen och klicka på **Installera tillägg**.
4. Kontrollera under **Installerade** att *Rita Detaljplan* är ikryssat.

### Alternativ 2: som pluginkälla

1. Välj **Tillägg → Hantera och installera tillägg… → Inställningar**.
2. Klicka på **Lägg till…** under *Pluginkällor*.
3. Ange ett valfritt namn och den här adressen:
   `https://raw.githubusercontent.com/ritaplan/rita-detaljplan/main/plugins.xml`
4. Kryssa i **Visa experimentella tillägg**.
5. Gå till **Alla** och installera *Rita Detaljplan*.

<!-- BILD: installera-pluginkalla.png | Dialogen Hantera och installera tillägg, fliken Inställningar med pluginkällan tillagd -->

> **Uppdatera** genom att installera en nyare zip-fil på samma sätt, eller via pluginkällan.
> Hade du det äldre pluginet *Detaljplan NGP* (mappen `detaljplan_ngp`) ska du ta bort det.

När pluginet är installerat finns verktygsfältet **Rita Detaljplan** högst upp i QGIS och menyn **Rita Detaljplan**
bland QGIS menyer för tillägg.

## Skapa en ny plan

1. Välj **Rita Detaljplan → Ny detaljplan…** eller klicka på ikonen *Ny detaljplan* i verktygsfältet.
2. Fyll i dialogen:
   - **Kommun** – välj i listan. Du kan skriva för att söka bland alla 290 kommuner.
   - **Planbeteckning / filnamn** – används också som namn på filen.
   - **Lagras i** – *Lokal fil (GeoPackage)* eller *PostGIS-databas*. Välj GeoPackage om du är osäker.
     Se [Lagring och databaser](lagring.md).
   - **Projektfil i mapp** – var QGIS-projektet sparas.
   - **Koordinatsystem** – SWEREF 99.
   - **Digitaliseringsläge** – kryssa bara i om du digitaliserar en äldre plan (se nedan).
3. Klicka på **OK**.

<!-- BILD: ny-plan-dialog.png | Dialogen Ny detaljplan med kommun, planbeteckning och koordinatsystem ifyllda -->

Pluginet skapar planen och ett QGIS-projekt med snappning påslagen. Planens lager hamnar i en egen grupp i
lagerpanelen, med samma namn som planen. Andra lager som du redan har öppna, till exempel en grundkarta, ligger kvar
orörda.

**Hur projektfilen sparas:**

- Har den öppna kartan **aldrig sparats** (till exempel ett nystartat QGIS) sparas den som planens nya projektfil.
  Grundkartan och allt annat kommer då med i samma fil.
- Är kartan **redan sparad** under ett annat namn rörs den filen inte. Planens projektfil skapas då bredvid.

### Digitalisera en äldre plan

Ska du föra över en äldre, analog plan till digital form kryssar du i **Jag digitaliserar en äldre plan**. Du kan
också slå på läget senare under *Planens uppgifter*.

I digitaliseringsläget:

- krävs inga motiv till planbestämmelserna,
- visas tolkningsbestämmelserna för äldre planer direkt när du tilldelar bestämmelser.

Läget gäller bara den planen och sparas i projektet.

> **Viktigt:** Slå av digitaliseringsläget innan du levererar en ny plan. NGP kräver motiv för planer som påbörjats
> efter 2021.

## Verktygsfälten

Pluginet har två verktygsfält. Knapparna visas som ikoner; håll muspekaren över en ikon för att se vad den gör.

<!-- BILD: verktygsfalt-oversikt.png | Det övre verktygsfältet Rita Detaljplan med numrerade knappar -->

### Det övre verktygsfältet

| Knapp | Vad den gör | Läs mer |
|---|---|---|
| Ny detaljplan / Öppna | Skapar eller öppnar en plan. | [Lagring](lagring.md) |
| **Pennan** – Börja rita planbestämmelser | Öppnar alla planlager för redigering. | [Rita planen](rita-planen.md) |
| **Disketten** – Avsluta redigering | Avslutar och frågar om ändringarna ska sparas. | [Rita planen](rita-planen.md) |
| Ritknappar | Planområde, användning, egenskap, sekundär egenskap, egenskapslinje, egenskapspunkt och hjälplager. | [Rita planen](rita-planen.md) |
| Importera geometrier | Hämtar geometrier från ett annat lager eller en fil. | [Rita planen](rita-planen.md#importera-geometrier) |
| Planbestämmelser / Kopiera bestämmelser | Ger ytorna bestämmelser. | [Bestämmelser](bestammelser.md) |
| Planens uppgifter | Namn, syfte, status, beslut, handlingar och checklista. | [Planens uppgifter](planens-uppgifter.md) |
| Topologikontroll | Hittar och rättar små glapp och brytpunkter. | [Kontrollera planen](kontrollera.md) |
| Leverans och export | Leverera till NGP, spara som JSON eller skapa arkivpaket. | [Leverera](leverera.md) |
| Tagga planbeskrivning | Taggar planbeskrivningen i Word. | [Tagga planbeskrivning](tagga-planbeskrivning.md) |
| Checka ut / Checka in | För planer i en PostGIS-databas. | [Lagring](lagring.md#checka-ut-och-checka-in) |

Det övre verktygsfältet har också **Markera**, **Avmarkera alla**, **Text**, **Dölj texter**, **Fyll användning** och
**Fyll egenskap**.

### Det flytande verktygsfältet

Ett andra verktygsfält flyter halvgenomskinligt längst ned i kartfönstret, ungefär som i ett CAD-program. Det syns bara
medan du redigerar. Du kan dölja det helt med **Rita Detaljplan → Rita Detaljplan – fler verktyg**.

<!-- BILD: flytande-verktygsfalt.png | Det flytande verktygsfältet längst ned i kartfönstret under redigering -->

Här finns:

- samma knappar som ovan: **Markera**, **Avmarkera alla**, **Text**, **Dölj texter**, **Fyll användning** och
  **Fyll egenskap**,
- **Dela objekt**, **Lägg till hål**, **Slå ihop valda objekt** och **Brytpunkter**,
- **Trimma/Förläng objekt**,
- **Spårning**, **Parallell** och **Vinkelrätt** – samma knappar som i QGIS egna verktygsfält.

## Nästa steg

Fortsätt med [Rita planen](rita-planen.md).
