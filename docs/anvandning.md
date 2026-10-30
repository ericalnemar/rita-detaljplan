# Användarhandbok – Rita Detaljplan

Rita Detaljplan är ett QGIS-plugin för att rita detaljplaner enligt Boverkets föreskrifter, kontrollera dem mot
Lantmäteriets regler och leverera dem till Nationella geodataplattformen (NGP).

Handboken går igenom arbetet steg för steg, i den ordning du normalt gör det. Är du ny börjar du med
[Kom igång](handbok/kom-igang.md).

<!-- FILM: oversikt | Rita Detaljplan på två minuter: en plan från början till slut -->

## Innehåll

1. [Kom igång](handbok/kom-igang.md) – installera, skapa en plan och lär känna verktygsfälten
2. [Rita planen](handbok/rita-planen.md) – planområde, användning, egenskap, hjälplager och import
3. [Bestämmelser](handbok/bestammelser.md) – välja, ändra och kopiera planbestämmelser
4. [Planens uppgifter](handbok/planens-uppgifter.md) – namn, syfte, genomförandetid, motiv, beslut och handlingar
5. [Kontrollera planen](handbok/kontrollera.md) – kontrollen mot Lantmäteriets regler och topologikontrollen
6. [Leverera planen](handbok/leverera.md) – leverera till NGP, spara som JSON och importera en leverans
7. [Teckenförklaring och plankarta](handbok/teckenforklaring.md) – teckenförklaringen och en exempellayout för plankartan
8. [Tagga planbeskrivning](handbok/tagga-planbeskrivning.md) – tagga planbeskrivningen enligt BFS 2020:8
9. [Arkivpaket](handbok/arkivpaket.md) – förbered planen för långtidsbevarande
10. [Lagring, databaser och flera planer](handbok/lagring.md) – GeoPackage, PostGIS och utcheckning
11. [Under huven](handbok/teknik.md) – datamodellen, databasen, utcheckningen och leveransen tekniskt

## Arbetsgången i korthet

1. **Ny detaljplan** – välj kommun, koordinatsystem och var planen ska lagras.
2. **Rita planområdet** med pennan och fyll i *Planens uppgifter*.
3. **Rita användningsområden** som täcker hela planområdet.
4. **Rita egenskapsområden** och egenskapslinjer.
5. **Tilldela bestämmelser** till alla ytor.
6. **Skriv motiven** och fyll i beslut och handlingar.
7. **Avsluta redigeringen** och **kontrollera planen**.
8. **Leverera** till NGP eller spara som JSON-fil.
9. **Skapa plankartan** med exempellayouten, eller teckenförklaringen i en egen layout.
10. **Skapa ett arkivpaket** för arkivering.

## Mer information

- [Kända begränsningar](kanda-begransningar.md) – läs innan du använder pluginet i ett skarpt ärende
- [Regler från Lantmäteriets vägledning](ngp-regler.md) – underlaget för kontrollen och exporten
- [Säkerhetsbeskrivning](sakerhet.md) – vilka data som skickas vart
- [Utveckling](utveckling.md) – köra koden och testerna
- [Ändringslogg](../CHANGELOG.md)
- [Rapportera fel eller önskemål](https://github.com/ritaplan/rita-detaljplan/issues)

Under **Rita Detaljplan → Om Rita Detaljplan…** ser du vilken version du har, och där finns länkar hit och till
[ritaplan.xyz](https://ritaplan.xyz).

## För den tekniskt intresserade

Hur planen är lagrad, hur databasen och utcheckningen fungerar och vad som händer vid export och leverans beskrivs i
[Under huven](handbok/teknik.md).
