# Arkivpaket

**Skapa arkivpaket** samlar planen och dess handlingar i en mapp som är förberedd för långtidsbevarande. Paketet har
bevarandemetadata enligt Boverkets dataelementkatalog (maj 2026, PREMIS 3.0) och kontrollsummor för alla filer.

<!-- FILM: arkivpaket | Skapa och kontrollera ett arkivpaket, ca 2 min -->

## Skapa ett arkivpaket

1. **Avsluta och spara** redigeringen. Paketet visar planen som den är sparad.
2. Välj **Rita Detaljplan → Skapa arkivpaket…**, eller *Skapa arkivpaket* i dialogen *Leverans och export*.
3. Lägg till handlingarna med **Lägg till filer…**: plankartan, planbeskrivningen och övriga handlingar.
4. Fyll gärna i **Utförd av**. Det är frivilligt och förs in som den som skapade paketet.
5. Skapa paketet.

<!-- BILD: arkivpaket-dialog.png | Dialogen Skapa arkivpaket med plankarta och planbeskrivning tillagda -->

> **Plankartan och planbeskrivningen ska vara PDF/A.** Pluginet gör inga filer till PDF/A och kontrollerar inte att de
> är det. Ta fram dem som PDF/A själv och kontrollera dem, till exempel med det kostnadsfria programmet
> [veraPDF](https://verapdf.org/). Pluginet säger bara till om en PDF inte uppger sig vara PDF/A, eller om en fil är ett
> Word-dokument.

### Det här kommer med ur planen

- En **kopia av planens GeoPackage**, som en ögonblicksbild. Originalet rörs inte.
- **Leveransfilen** (JSON, detaljplan 4.1), samma som *Spara som JSON-fil*.

En plan i en databas har ingen fil att kopiera. Leveransfilen innehåller då hela planen.

## Så ser paketet ut

Paketet blir en ny mapp. En mapp som redan finns skrivs aldrig över.

```
<plannamn>_arkivpaket_<datum>/
    metadata/
        PREMIS.xml      all bevarandemetadata: planen, filerna, händelserna och aktörerna
    schemas/            scheman för att kunna validera utan internet
    content/            själva filerna: planen, plankartan, planbeskrivningen med flera
```

### metadata/PREMIS.xml

En fil som är giltig mot Library of Congress schema för PREMIS 3.0. Den beskriver

- **planen** som en helhet, med planens uppgifter: beteckning, namn, status, typ, datum för laga kraft, användbarhet,
  kommun och kommunkod (det som är ifyllt),
- **varje fil**: kontrollsumma (SHA-256), storlek, format och version, programmet som skapade filen, när och var i
  paketet den ligger,
- **händelserna**: paketet skapades, kontrollsummor beräknades, filerna exporterades,
- **aktörerna**: Rita Detaljplan och den som skapade paketet.

### schemas/

- PREMIS-schemat (`premis-v3-0.xsd`),
- schemat för planens uppgifter (`detaljplan-1.xsd`), som är pluginets eget,
- Lantmäteriets JSON-scheman för Detaljplan 4.1, när leveransfilen finns med.

Med dem kan `PREMIS.xml`, planens uppgifter och leveransfilen valideras utan internet.

> Boverkets katalog kompletterar kommunens egen metadata och arkivredovisning, men ersätter dem inte. Paketet är inget
> E-ARK- eller FGS-paket. Har kommunen ett e-arkiv lägger du PREMIS-filen i e-arkivets eget paketeringsflöde. Läs mer i
> [Kända begränsningar](../kanda-begransningar.md) och [Revision av arkivpaketet](../arkivpaket-revision.md).

## Kontrollera ett arkivpaket

Välj **Rita Detaljplan → Kontrollera arkivpaket…** och peka ut paketmappen. Kontrollen räknar om kontrollsummorna och
visar om en fil har

- **ändrats**,
- **försvunnit**, eller
- **lagts till**

sedan paketet skapades. Den kontrollerar också att länkarna i metadatan hänger ihop, och säger till om paketet skapats
med en äldre version (0.1.55–0.1.59) vars metadata inte är giltig mot PREMIS-schemat.

Kontrollen ändrar ingenting.
