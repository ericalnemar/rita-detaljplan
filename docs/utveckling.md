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
[CHANGELOG](../CHANGELOG.md), kör testerna, bygg zip-filen, generera pluginkällan (`python tools/build_plugins_xml.py`,
skriver `plugins.xml` som checkas in med versionen), tagga (`git tag v0.1.0`) och lägg zip-filen på en Release.
`plugins.xml` är det QGIS pluginhanterare läser när repot används som pluginkälla (se [README](../README.md)); den pekar
på zip-filen i Releasen, så skapa Releasen direkt efter att du pushat.

## Struktur

```
rita_detaljplan/       pluginet (det som installeras)
  controller.py       håller reglerna igång medan man ritar (hierarki, session, tilldelning)
  core/               logik utan GUI: model, codelists (genererad), geopackage, project, symbology, rules,
                      assignments (tilldela bestämmelser), catalog + bestammelse + rows (ren Python), catalog_store
  icons/              ikoner till verktygsfältet (SVG)
  data/               medföljande kopia av planbestämmelsekatalogen och stilbiblioteket
  gui/                dialoger
  planbeskrivning/    Tagga planbeskrivning (se nedan)
spec/                 Lantmäteriets scheman (källa till kodlistor och konformitetstester)
tools/                generatorer och utvecklingsskript
tests/                enhetstester (spec-konformitet + QGIS-funktionstester)
```

### Tagga planbeskrivning

Knappen *Tagga planbeskrivning* öppnar programmet i `rita_detaljplan/planbeskrivning/`, som taggar planbeskrivningar
(Word) enligt BFS 2020:8 och Lantmäteriets Planbeskrivning 2.0:

```
planbeskrivning/
  pbkarna/            kärnan, ren Python (ingen Qt, ingen QGIS): taggar och XML-del (planbeskrivning.py), läsa och
                      tagga .docx (planbeskrivning_docx.py), kontroll mot BFS 2020:8, läsa en plan ur GeoPackage/
                      QGIS-projekt (plankarta.py, geometri.py), utbytesfil (utbyte.py)
  pbapp/              fönstret: session.py (logiken utan Qt), pages.py (de fyra stegen), theme.py, widgets.py, main.py
    qt/               Qt-importer: PyQt6 via qgis.PyQt i QGIS, PySide6 fristående
gui/planbeskrivning_host.py   QgisHost: ger programmet den aktiva planen och tar emot syfte och motiv
```

Programmet går också att köra fristående, utan QGIS (med PySide6 installerat, `pip install PySide6`):

```
python -m rita_detaljplan.planbeskrivning [planbeskrivning.docx] [plan.qgz]
python tools/skapa_exempel.py      # exemplet kv. Lärkan i exempel/ (knappen Öppna exemplet i fristående läge)
```

Testerna (`tests/test_planbeskrivning*.py`) körs med resten av sviten. Kärnans och fönstrets tester behöver inte QGIS
men körs då med PySide6. Den klickbara skissen av gränssnittet finns i `docs/planbeskrivning-skiss.html`.

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
