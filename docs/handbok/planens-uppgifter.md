# Planens uppgifter

Dialogen **Planens uppgifter** (ikonen med kryssrutan) samlar allt om planen som inte är geometri: namn, syfte,
status, genomförandetid, kvalitet, motiv, beslut och handlingar. Här finns också en checklista över vad som återstår
före leverans.

<!-- FILM: planens-uppgifter | Fyll i planens uppgifter, motiv och handlingar, ca 3 min -->

Du kan spara när som helst och fylla i resten senare. Saknade uppgifter stoppar aldrig sparandet.

- **Gula rutor** med en röd asterisk är obligatoriska och ännu tomma. De blir vita när du fyllt i dem.
- **Röda rutor** innehåller ett felskrivet datum. Det stoppar sparandet tills du rättat det.
- Alla datumrutor har en **kalenderknapp** till höger.

Dialogen har flera flikar.

<!-- BILD: planens-uppgifter.png | Dialogen Planens uppgifter, fliken Plan, med checklistan -->

## Fliken Plan

| Fält | Kommentar |
|---|---|
| **Kommun** * | |
| **Namn** * | |
| **Syfte** * | |
| **Status** * | |
| **Plantyp** * | |
| **Beteckning** | |
| **Genomförandetid** * | Se nedan. |
| **Referensskala** | Under *Visning i kartan*. Se nedan. |
| **Läge** | Digitaliseringsläge för äldre planer. Se [Kom igång](kom-igang.md#digitalisera-en-äldre-plan). |

### Genomförandetid

Varje detaljplan måste ha en genomförandetid. Ange den i år eller månader, mellan 5 och 15 år enligt PBL 4 kap. 21 §.

- Den ingår i checklistan.
- Saknas den ger kontrollen ett fel som stoppar leveransen.
- Den skrivs ut längst ned i teckenförklaringen.

### Referensskala

Linjer och texter ritas för en fast skala, så att de inte blir för tjocka eller tunna när du zoomar. Standard är
**1:1000**. Ändra den till den skala plankartan ska skrivas ut i.

Användningens text är alltid tydligt större än egenskapernas, som placeras under den.

### Checklistan

Checklistan visar vad som krävs före leverans:

- kommun, namn, syfte, status och plantyp,
- att planområdet är ritat,
- att användningsytorna täcker hela planområdet,
- att alla ytor har bestämmelse,
- genomförandetid och, vid laga kraft, kvalitet, motiv och handlingar.

Checklistan visas också när du avslutar redigeringen.

## Fliken Kvalitet

Planens kvalitetsbeskrivning och användbarhet enligt Nationell informationsspecifikation Detaljplan 4.1:

- **Digitaliseringsnivå** * – redan ifylld med *komplett*.
- **Användbarhet** * – redan ifylld med *god*.
- Beskrivning av nivå, korrigerade gränser och kontrollerat planeringsunderlag – valfria.

Digitaliseringsnivå och användbarhet krävs vid laga kraft. De förifyllda värdena gäller när planen ritas direkt med
rätt lägesnoggrannhet. Ändra dem bara om det inte stämmer, till exempel om du digitaliserat från ett sämre underlag.

Varje bestämmelse har en egen kvalitetsbeskrivning, som du når med **Kvalitet…** när du tilldelar bestämmelser.

## Motiv till planbestämmelser

Fliken listar alla bestämmelser som används i planen, en rad per bestämmelse även om den ligger på flera ytor.

1. Markera en bestämmelse i listan.
2. Skriv motivet (planbestämmelsebeskrivningen).

Motivet gäller alla ytor som har bestämmelsen. Lägger du samma bestämmelse på en ny yta får den motivet direkt.

- Motiven **krävs först vid laga kraft**. När status är *laga kraft* blir tomma motiv gula och fliken får ett kryss.
- För *Tekniska anläggningar* är motivet fast.
- I digitaliseringsläget krävs inga motiv.

> Har du redan skrivit motiven i planbeskrivningen kan du hämta dem därifrån med
> [Tagga planbeskrivning](tagga-planbeskrivning.md).

## Fliken Beslut

Beslutsinformationen: instans, beslutstyp, diarienummer och datum för påbörjat, antagande och laga kraft.
Datum för påbörjat är obligatoriskt.

## Fliken Handlingar

Här anger du planbeskrivning, beslutshandlingar (plankarta, protokoll) och planeringsunderlag, med namn, datum,
händelse och länk (https). Referensidentiteten för en handling sätts när den laddats upp till NGP.

**Vid laga kraft krävs**

- en planbeskrivning (DP-0005),
- minst en beslutshandling som innehåller plankartan (DP-0014, DP-0017).

En beslutshandling kan innehålla flera saker: plankarta, beslutsprotokoll och övrigt (till exempel ett
laga kraft-bevis). Kryssa i det som stämmer. Ett protokoll som också innehåller plankartan räcker alltså.

Före laga kraft är handlingarna frivilliga, men saknas de får du en varning. Vid laga kraft stoppar de leveransen och
fliken får ett kryss tills kraven är uppfyllda.

## Nästa steg

Fortsätt med [Kontrollera planen](kontrollera.md).
