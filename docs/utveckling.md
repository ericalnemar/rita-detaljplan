# Utveckling – Rita Detaljplan

För dig som vill köra koden, testerna eller bidra. Se även [CONTRIBUTING](../CONTRIBUTING.md).

## Utveckling

Kräver QGIS 4.x (testat med 4.2.2). Kodlistorna genereras från `spec/` med vanlig Python:

```
python tools/generate_codelists.py       # kodlistor från spec/
python tools/update_bundled_catalog.py   # ny kopia av planbestämmelsekatalogen (kräver nätverk)
```

Kör testerna med QGIS egen Python (sätt `QGIS_ROOT` om QGIS ligger någon annanstans):

```
tests\run_tests.bat
```

Installera pluginet i din QGIS-profil under utveckling (skapar en länk, ändrar inget annat):

```
powershell -File tools\install_dev.ps1
```

Starta om QGIS och aktivera **Rita Detaljplan** under *Tillägg → Hantera tillägg*.

Bygg installationspaketet (zip-filen som läggs på GitHub Releases) med:

```
python tools/build_zip.py     # skapar dist/rita_detaljplan-<version>.zip
```

Versionen läses ur `rita_detaljplan/metadata.txt`. Så gör du en ny version: uppdatera `version` där och i
[CHANGELOG](../CHANGELOG.md), kör testerna, bygg zip-filen, tagga (`git tag v0.1.0`) och lägg zip-filen på en Release.

## Struktur

```
rita_detaljplan/       pluginet (det som installeras)
  controller.py       håller reglerna igång medan man ritar (hierarki, session, tilldelning)
  core/               logik utan GUI: model, codelists (genererad), geopackage, project, symbology, rules,
                      assignments (tilldela bestämmelser), catalog + bestammelse + rows (ren Python), catalog_store
  icons/              ikoner till verktygsfältet (SVG)
  data/               medföljande kopia av planbestämmelsekatalogen och stilbiblioteket
  gui/                dialoger
spec/                 Lantmäteriets scheman (källa till kodlistor och konformitetstester)
tools/                generatorer och utvecklingsskript
tests/                enhetstester (spec-konformitet + QGIS-funktionstester)
```

## Datamodellen och NGP

Leveransen till NGP är JSON (GeoJSON-baserad `FeatureCollection`, mediatyp
`application/vnd.lm.detaljplan.v4+json`) via Lantmäteriets uppdaterings-API: registrera mottagning →
registrera förändringar → ladda upp domänobjekt → vänta på asynkron validering. Verifieringsmiljö:
`api-ver.lantmateriet.se`. Se `spec/` för scheman och API-beskrivning.

Testerna i `tests/test_spec_conformance.py` kontrollerar att modellens fält finns i schemat, att
obligatoriska fält är markerade och att kodlistorna är aktuella.

## Vägkarta

1. ✅ Skelett, datamodell, "Ny detaljplan"
2. ✅ Bestämmelseväljare mot Boverkets planbestämmelsekatalog (öppna data, UUID och formuleringar)
3. ✅ Validering enligt DP-Krav och DP-regler (stoppande fel och varningar)
4. ✅ Export till NGP-JSON (`detaljplan-4.1`) + mot schemat
5. ✅ Uppladdning till NGP (VER) med statusuppföljning och valideringsrapport (overifierad mot NGP)
6. ✅ Teckenförklaring som verktyg i layoutläget (plankartemallen gör användaren själv)
7. ⬜ Ändringsplaner, 3D (kropp), import från andra system
