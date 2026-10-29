# Bestämmelser

Varje användnings- och egenskapsyta ska ha minst en planbestämmelse. Bestämmelserna väljs ur Boverkets
planbestämmelsekatalog, och beteckningarna (B, e1, f2 …) sätts automatiskt.

<!-- FILM: tilldela-bestammelser | Tilldela, ändra och kopiera bestämmelser, ca 4 min -->

## Tilldela en bestämmelse

1. Klicka på verktyget **Planbestämmelser** i verktygsfältet.
2. Klicka på en yta i kartan. Ligger flera ytor på varandra, till exempel en egenskap över en användning, väljer du
   vilken du menar. Den valda ytan markeras i kartan.
3. Välj en bestämmelse i den sökbara listan.
4. Fyll i eventuella värden, till exempel `30 %`. Värdetyp och enhet är redan ifyllda.
5. Klicka på **Lägg till**.
6. Lägg till fler bestämmelser på samma yta om det behövs, och stäng dialogen.

Verktyget stänger av sig självt när du stänger dialogen.

<!-- BILD: tilldela-dialog.png | Dialogen för att tilldela bestämmelser, med sökrutan och en vald bestämmelse -->

### Hitta rätt bestämmelse

Listan visar bara bestämmelser som passar ytan, alltså rätt typ och rätt användningsform. De är uppdelade under
rubriker som *Användningsbestämmelser – Kvartersmark*, med en underrubrik per kategori.

- Sökrutan hittar ord var som helst i texten, och flera ord i valfri ordning. Skriv till exempel `byggnad mark` för att
  hitta *Marken får inte förses med byggnad*.
- En egenskapsyta på kvartersmark visar bara kvartersmarkens egenskaper, och en på allmän plats bara allmän plats.
  Det bekräftas på en rad under listan.
- Digitaliserar du en äldre plan kan du kryssa i **Visa tolkningsbestämmelser (för äldre planer)**. Valet sparas till
  nästa gång.

Du behöver aldrig skriva UUID eller andra tekniska fält.

### Flera bestämmelser på samma yta

En yta kan ha flera bestämmelser: en användningsyta kan ha flera användningar (`BC`) och ett egenskapsområde flera
egenskaper (`e1 a2`). Beteckningen skrivs inne i ytan.

Pilarna **▲ ▼** ändrar ordningen. Ordningen styr

- i vilken ordning bokstäverna står i beteckningen (`BC` eller `CB`),
- vilken bestämmelses färg och symbol som visas.

Indexsiffran (som i F1 och F2) sätts när bestämmelsen läggs till och följer inte med automatiskt när du byter ordning.
Klicka på **Indexera om** för att numrera om siffrorna efter listans ordning.

### Hur beteckningarna fungerar

- En beteckning, till exempel `f1`, hör till **exakt en** bestämmelse i hela planen.
- Samma bestämmelse får samma beteckning överallt.
- En annan bestämmelse får nästa lediga siffra.

För bestämmelser där katalogens beteckning är en mall (till exempel *Utformning av områden för dagvatten – annan*)
finns fältet **Beteckning på plankartan**. Skriv bara bokstäverna, till exempel `Dv`. Siffran läggs till automatiskt
(`Dv1`).

## Återanvänd en bestämmelse

Har du redan använt en bestämmelse på en annan yta i planen:

1. Välj den i listan **Använd en bestämmelse som redan finns i planen**.
2. Klicka på **Lägg till**.

Den får samma text, värden och beteckning som på den andra ytan.

## Samma bestämmelse på flera ytor

1. Markera flera ytor av samma typ med **Markera** (Ctrl-klick eller dra en rektangel).
2. Klicka på en av dem med **Planbestämmelser**.
3. Kryssa i **Lägg även på de andra markerade ytorna**.
4. Välj bestämmelse och klicka på **Lägg till**.

Bestämmelsen läggs på alla ytorna med samma beteckning. En yta där den inte passar hoppas över, och du får veta
varför.

## Kopiera bestämmelser mellan ytor

Verktyget **Kopiera bestämmelser** (två överlappande ytor, bredvid *Planbestämmelser*) kopierar **alla**
egenskapsbestämmelser från en yta till en annan.

1. Klicka på verktyget.
2. Klicka på ytan du vill kopiera **från**. Den markeras med grönt.
3. Klicka på ytan som ska få samma bestämmelser. Du kan fortsätta klicka på fler ytor.
4. Högerklicka eller tryck **Esc** för att välja en ny yta att kopiera från.

Bra att veta:

- Målytans egna bestämmelser ligger kvar. De kopierade läggs sist, och det som ytan redan har kopieras inte igen.
- Bestämmelser som inte passar målytan hoppas över, och meddelandet säger vilka och varför.
- En kopia är samma bestämmelse, så den får samma beteckning och samma motiv.
- Fungerar bara för egenskapsbestämmelser, och bara mellan samma sort: yta till yta eller linje till linje.

## Egenskap för hela användningsområdet

Har du valt en **användningsyta** finns rubriken *Egenskap för hela användningsområdet* i listan. Där finns de åtta
egenskapsbestämmelser i katalogen som gäller "inom användningsområdet", det vill säga största och minsta byggnads- och
bruttoarea.

Pluginet skapar då en egenskapsyta med samma form som användningsytan och lägger bestämmelsen på den. Ändrar du
användningsytan efteråt får du en varning om att egenskapsytan inte längre har samma form.

## Ändra, anpassa och ta bort

I dialogen finns knappar för de bestämmelser som ytan redan har:

| Knapp | Vad den gör |
|---|---|
| **Ändra…** | Öppnar bestämmelsen igen, så att du kan ändra värden eller formulering. |
| **Ta bort** | Tar bort bestämmelsen från ytan. |
| **Anpassa formulering…** | Låter dig bläddra bland alla bestämmelser och ändra ordalydelsen. Du får en varning om att texten då avviker från katalogen. |
| **Kvalitet…** | Bestämmelsens kvalitetsbeskrivning och användbarhet. Krävs vid laga kraft, men är redan ifyllt med vanliga värden. |
| **Reglerar annan plan…** | Bara för egenskapsbestämmelser. Anger att bestämmelsen hör ihop med en annan detaljplan, till exempel vid samordning med en grannplan. Valfritt. |

> **Motiven skrivs inte här.** De skrivs på fliken *Motiv till planbestämmelser* i
> [Planens uppgifter](planens-uppgifter.md#motiv-till-planbestämmelser).

## Planbestämmelsekatalogen

Pluginet har en inbyggd kopia av Boverkets katalog med 908 pågående bestämmelser, så det fungerar även utan internet.

Välj **Rita Detaljplan → Uppdatera planbestämmelsekatalogen…** för att hämta den senaste versionen från Boverket.
Upphörda bestämmelser kommer också med. Hämtningen görs i bakgrunden och går via QGIS egna nätverksinställningar
(proxy med mera).

Katalogen kommer från [Boverkets öppna data](https://www.boverket.se/sv/om-boverket/oppna-data/planbestammelser/).

## Nästa steg

Fortsätt med [Planens uppgifter](planens-uppgifter.md).
