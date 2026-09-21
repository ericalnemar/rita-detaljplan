# Rita Detaljplan

Ett QGIS-plugin för att **rita detaljplaner** enligt Lantmäteriets
[Nationell informationsspecifikation Detaljplan v4.1](https://www2.lantmateriet.se/globalassets/temawebbar/ngp/natspec-detaljplan-v4.1.pdf)
och Boverkets planbestämmelsekatalog, kontrollera dem mot Lantmäteriets regler och **leverera dem till Nationella
geodataplattformen (NGP)**. Målgrupp: planarkitekter och kartritare hos kommuner och konsulter.

Öppen källkod, [GPL-2.0-or-later](LICENSE). Gränssnittet är på svenska.

> **Version 0.1: tidig utvecklingsversion.** Det mesta fungerar och är testat med automatiska tester, men leverans till NGP
> är **inte provad mot Lantmäteriets riktiga miljö** och PostGIS-delen inte mot en riktig databas. Läs
> [Kända begränsningar](docs/kanda-begransningar.md) innan du använder pluginet till något viktigt, och rapportera gärna fel
> under [Issues](https://github.com/ericalnemar/rita-detaljplan/issues).

<!-- Skärmbilder: lägg bilderna i docs/images/ och ta bort kommentaren runt raden nedan.
![Verktygsfältet och en plan i QGIS](docs/images/verktygsfalt.png)
-->

## Vad pluginet gör

- **Ritar planen i hierarki:** planområde → användning → egenskap, med snappning, fyllverktyg och regler som håller ytorna
  konsekventa medan du ritar.
- **Bestämmelser ur Boverkets katalog:** välj bland pågående planbestämmelser, fyll i värden och tilldela en eller flera
  bestämmelser per yta. Beteckningar (a1, e2 …) sätts automatiskt.
- **Symbologi enligt Boverkets föreskrifter** med färger, mönster, gränser och etiketter, dimensionerade för vald
  referensskala.
- **Kontrollerar planen** mot Lantmäteriets regler (fel, varningar och sådant som återstår) och visar var i kartan.
- **Levererar till NGP** via Uppdatering-API:et, eller sparar leveransen som JSON-fil.
- **Skapar detaljplanens teckenförklaring** i QGIS layoutläge (rubriker, färgrutor, mönster, genomförandetid), med
  inställningar för teckensnitt, storlekar och avstånd.
- **Lagrar planen** i en lokal GeoPackage eller i ett PostGIS-schema, med **utcheckning och incheckning** (lås och
  lokal kopia) så att ritandet går snabbt även mot en databas.

## Installera

Kräver **QGIS 4.0 eller senare** (testat med 4.2.2 på Windows).

1. Ladda ned `rita_detaljplan-<version>.zip` från [Releases](https://github.com/ericalnemar/rita-detaljplan/releases).
2. Starta QGIS och välj **Tillägg → Hantera och installera tillägg… → Installera från ZIP**.
3. Peka ut zip-filen och klicka **Installera tillägg**.
4. Under **Installerade** ska *Rita Detaljplan* vara ikryssat. Verktygsfältet **Planbestämmelser** och menyn
   **Rita Detaljplan** visas.

Uppdatera genom att installera en nyare zip på samma sätt. Ta bort ett äldre plugin som hette *Detaljplan NGP* (mappen
`detaljplan_ngp`) om du hade det.

Vill du köra direkt från källkoden, se [Utveckling](docs/utveckling.md).

## Snabbstart

1. **Rita Detaljplan → Ny detaljplan…**: välj kommun, koordinatsystem (SWEREF 99) och var planen ska lagras.
2. Klicka på **pennan** (*Börja rita planbestämmelser*) och rita **planområdet**.
3. Fyll i **Planens uppgifter** (namn, syfte, status, **genomförandetid** …) i dialogen som öppnas.
4. Rita **användningsområden** som täcker planområdet, och därefter **egenskapsområden** och linjer.
5. Klicka med **Planbestämmelser**-verktyget på en yta och välj bestämmelser ur katalogen.
6. Avsluta redigeringen (sparar planen). Kontrollera planen och leverera via **NGP**-knappen (moln med pil).
7. Vill du ha en **teckenförklaring**: öppna en layout och klicka **Teckenförklaring** i verktygsfältet *Rita Detaljplan*.

Fler detaljer, moment för moment: [Användarhandledning](docs/anvandning.md).

## Dokumentation

- [Användarhandledning](docs/anvandning.md): alla moment och verktyg
- [Kända begränsningar](docs/kanda-begransningar.md): vad som inte är provat eller saknas
- [Regler från Lantmäteriets vägledning](docs/ngp-regler.md): underlag för kontrollen och exporten
- [Utveckling](docs/utveckling.md): köra koden och testerna, struktur, vägkarta
- [Ändringslogg](CHANGELOG.md)

## Bidra

Fel, önskemål och frågor tas emot under [Issues](https://github.com/ericalnemar/rita-detaljplan/issues). Vill du bidra med
kod, läs [CONTRIBUTING](CONTRIBUTING.md). Säkerhetsfrågor: se [SECURITY](SECURITY.md).

## Licens och källor

GPL-2.0-or-later, se [LICENSE](LICENSE). Material från andra, som Lantmäteriets scheman, Boverkets
planbestämmelsekatalog och stilbiblioteket, står i [NOTICE](NOTICE.md).

Pluginet är inte en officiell produkt från Lantmäteriet eller Boverket.
