# Revision av arkivpaketet och användningen av PREMIS

Datum: 2026-10-26. Gäller arkivpaketet i Rita Detaljplan 0.1.55–0.1.59 (`rita_detaljplan/core/archive.py`).

> **Status:** fynd 1–9 och 11–12 och 16 är rättade i **0.1.60** (planens uppgifter enligt alternativ A, i `significantProperties`).
> Kvar: fynd 10 (kontrollsumma för metadatafilen), 13 (formatregister), 14 (okänt skapande program), 15 (datumformatet är
> redan det utökade, med verklig tidszon) samt valfri E-ARK SIP. Texten nedan beskriver läget **före** 0.1.60.

Revisionen kontrollerar paketet mot **Library of Congress officiella XML-schema för PREMIS 3.0**, mot LoC:s kontrollerade
värdelistor, mot **Boverkets dataelementkatalog (maj 2026)** med deras två XML-mallar och manual, och mot hur
**Riksarkivet** vill ha PREMIS i ett paket (E-ARK CSIP/SIP).

## Kort slutsats

1. **Paketets två XML-filer går inte igenom schemavalidering.** Det gäller både `detaljplan.xml` och `metadata/PREMIS.xml`.
2. **Orsaken är att Boverkets mallar inte följer schemat, och att pluginet följde mallarna.** Båda mallarna är ogiltiga mot
   schemat på samma sätt (se avsnitt 2). Det stämmer med det experten sagt om att Boverkets exempel är felaktigt.
3. **Värdena är rätt.** Alla värden pluginet och Boverket använder (till exempel `has Part`, `information package creation`,
   `SHA-256`, `Uniform Resource Identifier`) finns i LoC:s värdelistor. Felen ligger i XML-strukturen, inte i innehållet.
4. **Allt går att rätta och ändå följa Boverkets katalog**, utom på en punkt: katalogen vill ha `objectCharacteristics`
   på själva planen (*representation*), och det tillåter PREMIS inte (avsnitt 2, punkt 5).
5. En rättad prototyp (en enda självbärande PREMIS-fil) är **giltig mot schemat** och alla länkar går åt båda håll.

## 1. Så kontrollerades det

| Kontroll | Hur |
|---|---|
| Schemavalidering | `lxml` mot LoC:s `premis.xsd` (version 3.0, 18 januari 2016) |
| Värdelistor | LoC:s listor på id.loc.gov (relationshipSubType, eventType, objectCategory, hash, m.fl.) jämfördes med våra värden |
| Länkar | Eget skript: alla UUID går att slå upp, och varje länk finns åt båda håll (Boverkets krav i manualen) |
| Boverkets material | Dataelementkatalogen (maj 2026), manualen och de två XML-mallarna, hämtade från Boverkets sida |

Schemavalidering ger bara besked om strukturen. Den säger ingenting om huruvida innehållet är *meningsfullt* för ett
e-arkiv, och inget som gjorts här ersätter experten.

## 2. Fynd i XML-strukturen (blockerande: schemat godkänner inte filerna)

Felen ligger bakom varandra: schemat slutar läsa vid första felet i varje objekt. Därför rättades de ett i taget i en
kopia för att hitta alla. `PREMIS.xml` blev giltig först efter att fynd 1–4 och 6 rättats. Fynd 5 gäller planens egen
post (representationen), som ligger i `detaljplan.xml`.

| # | Fel | Vad schemat kräver | Var det kommer från |
|---|---|---|---|
| 1 | `<object>` saknar `xsi:type` | `object` är en abstrakt typ. Varje objekt måste ha `xsi:type="premis:file"` eller `"premis:representation"` | Boverkets mallar |
| 2 | Elementet `objectCategory` finns | **Elementet finns inte i XML-schemat.** Kategorin uttrycks bara med `xsi:type`. Schemat säger det själv i en kommentar (`premis.xsd` rad 119–123) | Boverkets mallar och katalog (som följer *dataordlistan*, inte XML-schemat) |
| 3 | `originalName` och `storage` står före `objectCharacteristics` | Ordningen är: `objectIdentifier`, `significantProperties`, `objectCharacteristics`, `originalName`, `storage`, `relationship`, `linkingEventIdentifier` | Boverkets mallar |
| 4 | `linkingAgentIdentifier` direkt på ett `object` | Ett objekt har ingen agentlänk. Agenter länkas bara via händelser | Boverkets mallar |
| 5 | `objectCharacteristics`/`objectCharacteristicsExtension` på en *representation* | `representation` har inte `objectCharacteristics` alls. Det finns bara på `file` och `bitstream` | Boverkets katalog (kardinalitet `[1..*]` på alla objekt) |
| 6 | I en `event` står `linkingObjectIdentifier` före `linkingAgentIdentifier` | Ordningen är agent först, sedan objekt | Boverkets mallar |
| 7 | `schemaLocation` pekar på `premis-3-0-draft.xsd` | Adressen finns, men är **utkastet för offentlig granskning** (60 kB, "DRAFT For Public Review"). Slutversionen är `premis-v3-0.xsd` (52 kB) | Boverkets mallar |

Fynd 2 är sannolikt det som är mest förvirrande: i PREMIS **dataordlista** finns `objectCategory` (värden: `file`,
`representation`, `bitstream`, `intellectual entity`), men i **XML-bindningen** har det ersatts av `xsi:type`.
Boverkets katalog och mallar blandar ihop de två.

## 3. Fynd som inte är schemafel, men som bryter mot Boverkets egna regler eller god praxis

| # | Fynd | Kommentar |
|---|---|---|
| 8 | **Länkarna går inte åt båda håll.** Agenterna saknar länk tillbaka till händelserna, och filerna saknar `is Part Of` mot planen | Manualen: "Alla relationer ska vara dubbelriktade". Kontrollerat med skript. Gäller dagens paket |
| 9 | **Planen (*representation*) ligger i en annan fil än resten.** `PREMIS.xml` hänvisar till ett UUID som bara finns i `detaljplan.xml` | Varje fil för sig har hängande hänvisningar. Manualen beskriver *en* PREMIS-fil med objekt, händelser och agenter |
| 10 | **Metadatafilerna har ingen kontrollsumma.** Filerna i `content/` skyddas, men `PREMIS.xml` och `detaljplan.xml` kan ändras utan att "Kontrollera paket" märker det | Löses med en manifestfil eller en kontrollsumma för hela paketet |
| 11 | Programmets version ligger i `agentName` ("Rita Detaljplan 0.1.59") | Det finns ett eget element, `agentVersion` |
| 12 | Händelserna saknar `eventOutcomeInformation` | Valfritt, men normalt (`eventOutcome`: success/failure) |
| 13 | Formatnamnen är egna ("DOCX", "GeoPackage", "PDF/A" + version "2B") och saknar registernyckel | PREMIS rekommenderar `formatRegistry` (till exempel PRONOM: PDF/A-1b är `fmt/354`, formatnamn "Acrobat PDF/A - Portable Document Format", version "1b"). Boverkets katalog gör det valfritt |
| 14 | Okänt skapande program skrivs som "Okänt program" | Ett påhittat värde. Bättre att utelämna `creatingApplication` (valfritt i schemat) eller skriva "unknown" |
| 15 | Datum: katalogen säger `ÅÅÅÅMMDDTHHMMSS+0100`, manualen och mallen `ÅÅÅÅ-MM-DDThh:mm:ss+01:00` | Pluginet skriver det utökade formatet med **verklig** tidszon (+02:00 på sommaren), vilket är rätt enligt EDTF. Fast `+01:00` är fel under sommartid |
| 16 | `objectCharacteristicsExtension`-innehållet (planens uppgifter) ligger utan eget namnrymd | Schemat tillåter det, men ett eget namnrymd gör att tolkande system kan känna igen elementen |

## 4. Fel och oklarheter i Boverkets eget material

- **Manualen, exempel 2.1:** `</premis:objectCategory` saknar `>`.
- **Mallen "flera filer":** datumen är `ÅÅÅÅ:MM:DDTTT:MM:SS+01:00` (kolon i datumet och ett T för mycket). Mallen "en fil" har
  `ÅÅÅÅ-MM-DDThh:mm:ss+01:00`.
- **Katalogen, `contentLocationType`:** exemplet är `URI`, men värdelistan (och LoC) har `Uniform Resource Identifier`.
- **Katalogen, `agentType`:** förklaringslänken pekar på `eventRelatedObjectRole.html` (ska vara `agentType`).
- **Katalogen:** `creatingApplication` är `[1..*]` på ett ställe och `[0..*]` på ett annat; `dateCreatedByApplication` är `[1]` i
  katalogen men kan utelämnas i schemat så länge programmets namn finns.
- **Katalogen, avsnitt 1.7:** "det finns inga dataelement som beskriver den intellektuella entiteten särskilt", men
  katalogen vill ändå lägga planens uppgifter på representationen (se fynd 5).
- Mallarna använder platshållare ("TEXT", "HELTAL") som inte är giltiga värden, till exempel `compositionLevel`.
- Katalogen är markerad som **förslag** och säger själv att den avviker från PREMIS "i val av värden och värdelistor".

## 5. Hur PREMIS ska användas för en detaljplan

PREMIS beskriver **bevarandet**, inte planen. Planens innehåll (namn, status, laga kraft) hör hemma i beskrivande metadata.

- **Representation** (`xsi:type="premis:representation"`) = planen som helhet, som den lämnas till arkivet. Ett paket har en.
- **File** = varje bifogad fil. Egenskaper: kontrollsumma, storlek, format, skapande program, namn, plats i paketet.
- **Event** = vad som hänt med objekten: *information package creation*, *message digest calculation*, *exporting*, och senare
  *fixity check* (varje gång paketet kontrolleras), *ingestion* (när e-arkivet tar emot det) och *migration*/*normalization*
  (om en fil konverteras).
- **Agent** = programmet och personen som utförde händelserna. Rollen anges på händelsen (`executing program`, `implementer`).
- **Relationer** går åt båda håll: planen `has Part` filerna, och varje fil `is Part Of` planen. Det gäller också event ↔ objekt och
  event ↔ agent.
- **Rättigheter** (`rights`) utelämnas, som Boverket gör.

Planens uppgifter kan läggas på tre giltiga sätt (välj ett, se rekommendationen sist):

| Alternativ | Giltigt enligt schemat | Kommentar |
|---|---|---|
| A. `significantProperties` → `significantPropertiesExtension` på representationen | Ja | Finns alltid. Prototypen använder detta |
| B. `objectCharacteristicsExtension` på leveransfilen (JSON) | Ja | Det som katalogen beskriver, men bara om leveransfilen är med |
| C. Egen beskrivande fil (`detaljplan.xml`, inte PREMIS) | Ja (ingen PREMIS-validering) | Så E-ARK gör: beskrivande och bevarandemetadata hålls isär |

## 6. Är paketet ett arkivpaket som e-arkiv tar emot?

Nej, inte direkt, och det är inte heller Boverkets avsikt: katalogen "ersätter inte … paketeringsspecifikationer". Riksarkivets
tillämpning av **E-ARK CSIP/SIP** (och FGS Paketstruktur) kräver:

- en rotmapp som börjar med `IP_`,
- `METS.xml` i roten,
- mapparna `metadata/descriptive`, `metadata/preservation` (här ligger PREMIS-dokumenten), `metadata/other`,
- `representations/rep_1/data` (själva filerna), `schemas/` och `documentation/`.

Pluginets mappar (`detaljplan.xml`, `metadata/PREMIS.xml`, `content/`) liknar det, men är ingen SIP. En kommun med e-arkiv får
alltså lägga PREMIS-filen i sitt eget paketeringsflöde (det är så Boverkets manual är tänkt). Att skapa en riktig E-ARK-SIP
(med METS) vore ett eget, större arbete.

## 7. Rekommenderade åtgärder

| Prio | Åtgärd |
|---|---|
| 1 | Rätta fynd 1–7: `xsi:type`, ingen `objectCategory`, rätt elementordning, inga agentlänkar på objekt, ordning i `event`, slutversionens schemaadress |
| 1 | Fynd 8: skriv alla länkar åt båda håll (`is Part Of`, agent → händelse) |
| 1 | Lägg ett automatiskt test som validerar mot LoC:s schema och kontrollerar länkarna (så att felen inte kommer tillbaka) |
| 2 | Fynd 9: en enda självbärande `PREMIS.xml` med representation, filer, händelser och agenter |
| 2 | Fynd 5: flytta planens uppgifter från representationens `objectCharacteristics` till ett giltigt ställe (alternativ A, B eller C) |
| 2 | Fynd 10: en manifestfil med kontrollsummor, så att också metadatafilerna kan kontrolleras |
| 3 | Fynd 11–14, 16: `agentVersion`, `eventOutcome`, formatregister (PRONOM), eget namnrymd för planens uppgifter |
| 3 | "Kontrollera paket" skriver en händelse `fixity check` (eller en separat kontrollrapport) |
| 4 | Valfritt senare: export som E-ARK SIP (METS) |

## 8. Det som inte kontrollerats

- Vad experten faktiskt menade. Punkterna ovan är det som går att *bevisa* mot schemat; det kan finnas fler, till exempel
  synpunkter om vilka händelser som ska finnas eller om representation kontra intellectual entity.
- Om svenska e-arkivsystem (Visuell Arkivering, Comprima, Preservica m.fl.) accepterar filen. Det kräver deras egna validatorer.
- PRONOM-nycklar för alla format pluginet kan lägga i ett paket (bara PDF/A-1b är bekräftad).
- Boverkets mallar har bara kontrollerats i sin ursprungliga form (med platshållarna).
