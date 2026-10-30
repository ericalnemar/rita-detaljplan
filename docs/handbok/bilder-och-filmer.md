# Bilder och filmer i handboken

Det här är en arbetsbeskrivning för dig som skriver handboken. Den visas inte på ritaplan.xyz.

Handboken skrivs som Markdown i `docs/`. Samma filer visas på GitHub och på
[ritaplan.xyz/handbok-dp.html](https://ritaplan.xyz/handbok-dp.html), som hämtar dem direkt från GitHub. Ändrar du i `docs/`
och pushar till `main` syns ändringen på webbplatsen inom en kvart.

## Platshållare

Där en bild eller film ska in finns en kommentar. Den syns inte, varken på GitHub eller på webbplatsen:

```
<!-- BILD: ny-plan-dialog.png | Dialogen Ny detaljplan med kommun och koordinatsystem ifyllda -->
<!-- FILM: kom-igang | Från installation till ett ritat planområde, ca 3 min -->
```

Texten efter `|` beskriver vad bilden eller filmen ska visa. Lista alla platshållare som återstår med:

```bash
grep -rn "<!-- \(BILD\|FILM\):" docs/
```

## Lägga in en skärmbild

1. Ta skärmbilden i QGIS och spara den som PNG i `docs/images/handbok/`, med namnet från platshållaren.
2. Byt ut kommentaren mot en vanlig bildlänk. Skriv en alternativtext som beskriver vad bilden visar:

   ```markdown
   ![Dialogen Ny detaljplan med kommun och koordinatsystem ifyllda](../images/handbok/ny-plan-dialog.png)
   ```

Tips:

- Beskär bilden till det som är viktigt, till exempel bara dialogen.
- Bredd omkring 1200–1600 pixlar räcker. Komprimera gärna med till exempel [Squoosh](https://squoosh.app/).
- Använd en exempelplan utan känsliga uppgifter.

## Lägga in en film

Filmerna ligger på ritaplan.xyz, inte i repot. Lägg varje film och en stillbild (poster) i mappen `film/detaljplan/` på
webbplatsen:

```
ritaplan.xyz/film/detaljplan/kom-igang.mp4     filmen (H.264, MP4)
ritaplan.xyz/film/detaljplan/kom-igang.jpg     stillbild som visas innan filmen startar
ritaplan.xyz/film/detaljplan/kom-igang.vtt     undertexter (frivilligt men rekommenderat)
```

Byt sedan ut kommentaren mot en bild som länkar till filmen:

```markdown
[![Film: Från installation till ett ritat planområde (3 min)](https://ritaplan.xyz/film/detaljplan/kom-igang.jpg)](https://ritaplan.xyz/film/detaljplan/kom-igang.mp4)
```

- **På GitHub** syns stillbilden. Ett klick öppnar filmen.
- **På ritaplan.xyz** byts länken automatiskt ut mot en spelare (video.js). Finns en `.vtt`-fil med samma namn visas
  den som svenska undertexter.

Regeln är att en länk till en `.mp4`- eller `.webm`-fil på ritaplan.xyz blir en spelare.

Tips:

- Spela in i 1920 × 1080 och håll filmerna korta, helst under 3 minuter. Hellre flera korta än en lång.
- Exportera som MP4 (H.264) så fungerar filmen i alla webbläsare.
- Undertexter hjälper den som inte kan lyssna och gör filmen sökbar.

## Platshållare som återstår

| Sida | Bilder | Filmer |
|---|---|---|
| [Startsidan](../anvandning.md) | | oversikt |
| [Kom igång](kom-igang.md) | installera-pluginkalla, ny-plan-dialog, verktygsfalt-oversikt, flytande-verktygsfalt | kom-igang |
| [Rita planen](rita-planen.md) | hierarki, egenskapspunkt, importera-geometrier | rita-planen, fyll-resten, flytta-texter |
| [Bestämmelser](bestammelser.md) | tilldela-dialog | tilldela-bestammelser |
| [Planens uppgifter](planens-uppgifter.md) | planens-uppgifter | planens-uppgifter |
| [Kontrollera planen](kontrollera.md) | kontrollera-planen, topologikontroll | kontrollera |
| [Leverera planen](leverera.md) | leverans-och-export, ngp-installningar | leverera-ngp |
| [Teckenförklaring](teckenforklaring.md) | teckenforklaring-layout | teckenforklaring |
| [Tagga planbeskrivning](tagga-planbeskrivning.md) | tagga-steg-2 | tagga-planbeskrivning |
| [Arkivpaket](arkivpaket.md) | arkivpaket-dialog | arkivpaket |
| [Lagring](lagring.md) | | checka-ut-in |

## Skrivregler

- Skriv **du** till läsaren och använd aktiv form: "Klicka på …", inte "Det klickas på …".
- Använd **numrerade steg** för det man gör i ordning och **punktlistor** för det som inte har en ordning.
- Skriv knappar, menyer och fält i **fetstil** och med samma namn som i pluginet: **Planens uppgifter**,
  **Rita Detaljplan → Ny detaljplan…**.
- Använd citatblock (`>`) för viktiga varningar och tips.
- Varje sida slutar med en länk till nästa steg.
- Nya sidor läggs i `docs/handbok/` och i innehållsförteckningen i `docs/anvandning.md`. Webbplatsen bygger sin meny
  från den listan.
