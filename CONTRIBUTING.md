# Bidra till Rita Detaljplan

Tack för att du vill hjälpa till! Pluginet är ungt och all återkoppling är värdefull, särskilt från dig som ritar
detaljplaner dagligen.

## Rapportera fel eller önska något

Öppna ett ärende under [Issues](https://github.com/ericalnemar/rita-detaljplan/issues) och välj mall. Ange gärna QGIS-version,
operativsystem, om planen ligger i GeoPackage eller PostGIS, vad du gjorde och vad som hände. **Bifoga aldrig en plan med
uppgifter du inte får dela.** Skärmbilder av felmeddelanden hjälper mycket.

## Köra koden och testerna

Kräver QGIS 4.x. Se [docs/utveckling.md](docs/utveckling.md) för installation från källkoden. Kör alla tester med QGIS egen
Python:

```
tests\run_tests.bat
```

Sätt `QGIS_ROOT` om QGIS ligger någon annanstans än `C:\Program Files\QGIS 4.2.2`. Testerna körs utan skärm
(`QT_QPA_PLATFORM=offscreen`) och tar ett par minuter. Öppna aldrig riktiga modala dialoger i tester: ersätt dem
med `mock.patch`.

## Kodstil

- **Gränssnittet är på svenska, koden på engelska** (namn på funktioner och variabler), kommentarer och docstrings på
  svenska där de förklarar varför.
- Följ stilen i omgivande kod. Liten och tydlig kod före smart kod.
- Ny funktion eller rättning ska ha ett test. Rena delar (utan QGIS) läggs i `rita_detaljplan/core/`, GUI i `gui/`.
- Ändrar du datamodellen, se `model.py` och höj `SCHEMA_VERSION` med en uppgraderingsväg för äldre planer.
- Nycklarna som sparas i användarens profil och projekt har prefixet `detaljplan_ngp` av bakåtkompatibilitetsskäl. Byt
  inte dem.

## Pull requests

1. Forka repot och skapa en gren.
2. Se till att `tests\run_tests.bat` går igenom.
3. Beskriv vad ändringen gör och varför, och lägg en rad i [CHANGELOG.md](CHANGELOG.md) under *Ej utgivet*.
4. Öppna en pull request.

Genom att bidra godkänner du att ditt bidrag licensieras under samma licens som projektet (GPL-2.0-or-later).
