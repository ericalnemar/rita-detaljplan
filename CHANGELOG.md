# Ändringslogg

Formatet följer [Keep a Changelog](https://keepachangelog.com/sv/1.1.0/), versionsnumren [Semantic Versioning](https://semver.org/lang/sv/).

## Ej utgivet

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

[0.1.6]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.6
[0.1.5]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.5
[0.1.4]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.4
[0.1.3]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.3
[0.1.2]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.2
[0.1.1]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.1
[0.1.0]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.0
