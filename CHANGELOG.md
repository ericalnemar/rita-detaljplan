# Ändringslogg

Formatet följer [Keep a Changelog](https://keepachangelog.com/sv/1.1.0/), versionsnumren [Semantic Versioning](https://semver.org/lang/sv/).

## Ej utgivet

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

[0.1.0]: https://github.com/ericalnemar/rita-detaljplan/releases/tag/v0.1.0
