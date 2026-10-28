# Källor och material från andra

Rita Detaljplan är licensierat under GPL-2.0-or-later (se [LICENSE](LICENSE)). Följande material kommer från andra och
har egna villkor. Kontrollera villkoren själv om du sprider eller bygger vidare på repot.

| Material | Var | Källa | Villkor |
|---|---|---|---|
| Scheman och API-beskrivning för detaljplan 4.1 | `spec/` | Lantmäteriet, Nationell informationsspecifikation Detaljplan (NGP) | Lantmäteriets villkor; källa anges här. Filerna används för att generera kodlistor och för konformitetstester. |
| Planbestämmelsekatalog | `rita_detaljplan/data/planbestammelsekatalog.json` | Boverket, [öppna data](https://www.boverket.se/sv/om-boverket/oppna-data/planbestammelser/) | Öppna data, fri användning med källhänvisning: *Källa: Boverket, Planbestämmelsekatalogen*. |
| PREMIS 3.0 XML-schema | `rita_detaljplan/data/schemas/premis-v3-0.xsd` (och en kopia i varje arkivpaket) | Library of Congress, [PREMIS](https://www.loc.gov/standards/premis/) | Library of Congress villkor; källa anges här. Oförändrad kopia. Används för att validera arkivpaketets bevarandemetadata. |
| Stilbibliotek Detaljplaner (Bfs 2020:6) | `rita_detaljplan/data/styles/` | [QGIS Hub, stil 238](https://hub.qgis.org/styles/238/) av Alnemar | CC0 1.0, se `LICENSE-CC0.txt` i mappen. |
| Kommunlista med kommunkoder | `rita_detaljplan/data/kommuner.json` | SCB, Regionala indelningar (<https://api.scb.se>) | SCB:s öppna statistik; källa anges i filen. |
| Text i bannrarna | `docs/images/banner-*.svg`, `social-preview.png` | Typsnitten Archivo och IBM Plex Mono ([Google Fonts](https://fonts.google.com/)) | SIL Open Font License 1.1. Texten är omvandlad till konturer; typsnittsfilerna följer inte med i repot. |

Pluginet är **inte** en officiell produkt från Lantmäteriet eller Boverket och har ingen koppling till dem utöver att det
följer deras öppna specifikationer.
