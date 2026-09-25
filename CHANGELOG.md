# Ändringslogg

Formatet följer [Keep a Changelog](https://keepachangelog.com/sv/1.1.0/), versionsnumren [Semantic Versioning](https://semver.org/lang/sv/).

## Ej utgivet

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
