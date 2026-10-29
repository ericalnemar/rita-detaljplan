# Kontrollera planen

Pluginet har två kontroller:

- **Kontrollera planen** granskar hela planen mot Lantmäteriets regler inför leverans.
- **Topologikontroll** hittar små glapp och brytpunkter som nästan, men inte exakt, sammanfaller, och rättar dem.

<!-- FILM: kontrollera | Kontrollera planen och rätta avvikelser, ca 3 min -->

## Kontrollera planen

1. Klicka på **Leverans och export** (brickan med en pil uppåt).
2. Klicka på **Kontrollera planen…** i den blå rutan överst.
3. Gå igenom listan. Avvikelserna är uppdelade i tre slag:
   - **Fel** – stoppar leveransen och måste rättas.
   - **Varningar** – bör ses över, men stoppar inte.
   - **Att fylla i** – uppgifter som saknas.
4. **Dubbelklicka** på en rad för att markera ytan och zooma till den.

Kontrollen körs också automatiskt när du avslutar redigeringen. Resultatet visas då i meddelandefältet.

<!-- BILD: kontrollera-planen.png | Dialogen Kontrollera planen med fel, varningar och att fylla i -->

### Vad som kontrolleras

Bland annat:

- att hela planområdet har en användning (DP-0002/0003),
- överlapp, glapp och smala ytor (DP-Krav-0011–0014),
- självkorsande gränser (DP-Krav-0018),
- att egenskaper ligger inom användningen och har rätt användningsform,
- att varje bestämmelse har rätt värden, värdetyp och enhet (DP-0022/0009),
- tekniska anläggningar (DP-0019/0020),
- att osäkert läge inte anges (DP-0010),
- kraven vid laga kraft: beslutsinformation, handlingar och kvalitetsbeskrivning.

Alla regler finns i [Regler från Lantmäteriets vägledning](../ngp-regler.md).

## Topologikontroll

> Topologikontrollen är i **beta** och har ännu inte full funktionalitet.

Två gränser som nästan, men inte exakt, ligger på varandra ritas båda. Då kan en gräns se olika tjock ut på olika
ställen. Topologikontrollen hittar sådant och föreslår rättningar.

Kontrollen görs på den **sparade** planen. Knappen är grå medan du redigerar: avsluta och spara först.

1. Klicka på **Topologikontroll** (brytpunkter med en cirkel).
2. Välj **tolerans**.
3. Gå igenom förslagen. Markera ett förslag och klicka på **Visa i kartan** för att se var det gäller.
4. Kryssa ur de förslag du inte vill genomföra.
5. Genomför ändringarna.
6. Spara genom att avsluta redigeringen.

<!-- BILD: topologikontroll.png | Dialogen Topologikontroll med förslag och Visa i kartan -->

### Förslagen

- **Flytta brytpunkter:** en brytpunkt i en användnings- eller egenskapsyta som ligger nära en annan ytas brytpunkt
  eller gräns flyttas dit.
- **Lägg till brytpunkter:** planområdets brytpunkter läggs till i användningen där de saknas.
- **Stäng glapp:** glapp mellan ytor i samma lager stängs. Den yta som ritades senast anpassas till den tidigare.

Planområdet ändras aldrig. Ändringarna görs i redigeringsbufferten med ett ångra-steg per lager.

### Avvikelser som också visas

- **Planområdet saknar användning** (fel). Knappen fyller det som saknas, på samma sätt som *Fyll användning*.
  *Visa i kartan* markerar exakt den del som saknar användning.
- **En yta saknar bestämmelse** (fel).
- **Kvartersmark saknar egenskapsområden** (varning). Det behöver inte vara fel.

## Nästa steg

Fortsätt med [Leverera planen](leverera.md).
