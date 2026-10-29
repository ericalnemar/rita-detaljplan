# Tagga planbeskrivning

Programmet **Tagga planbeskrivning** taggar planbeskrivningen (Word, `.docx`) enligt Boverkets föreskrifter BFS 2020:8
och Lantmäteriets Planbeskrivning 2.0. Varje avsnitt får tema, grupp och undergrupp, och motiven kopplas till planens
bestämmelser.

**Originaldokumentet ändras aldrig.**

<!-- FILM: tagga-planbeskrivning | Tagga en planbeskrivning i fyra steg, ca 4 min -->

## Öppna programmet

Klicka på **Tagga planbeskrivning** (dokumentet med en etikett) i verktygsfältet. Programmet öppnas i ett eget fönster
med den aktiva planen vald. Knappen är grå tills planområdet är ritat.

Programmet går också att köra fristående, utan QGIS.

## De fyra stegen

1. **Välj planbeskrivningen** – Word-filen (`.docx`).
2. **Granska taggarna** – pluginet föreslår tema, grupp och undergrupp för varje avsnitt. Ändra där förslaget inte
   stämmer.
3. **Koppla motiven** – koppla motiven i texten till planens bestämmelser. Kartan visar var en bestämmelse gäller.
4. **Kontrollera och spara** – pluginet kontrollerar det obligatoriska innehållet och sparar två kopior.

<!-- BILD: tagga-steg-2.png | Steg 2 i Tagga planbeskrivning: rubrikerna med föreslagna teman -->

## Det här sparas

| Fil | Innehåll |
|---|---|
| **Leveranskopia** | Dokumentet med bokmärken och en XML-del med taggarna. |
| **Granskningskopia** | Dokumentet med taggarna som kommentarer i Word, så att du lätt kan granska dem. |

## Hämta syfte och motiv till planen

Klicka på **Importera till planen** i sista steget. Syftet och motiven från planbeskrivningen läggs då på planen och
dess bestämmelser och ersätter det som stod där. Ändringarna hamnar i redigeringsbufferten, så spara planen som vanligt
efteråt.

Har du ändrat i planen medan fönstret är öppet hämtar **Läs om från QGIS** bestämmelserna igen.

## Så känns rubrikerna igen

Rubrikerna i Word känns igen som tema, grupp och undergrupp när de stämmer med bilagan till föreskrifterna.

- Skiftläge, numrering och skiljetecken spelar ingen roll.
- En liten felstavning går bra. Raden markeras då som *nära*.

### Motiven

Motiv söks **bara** under en rubrik med temat *Motiv till detaljplanens regleringar*. Rubriken känns också igen när
den skrivs på andra vanliga sätt, till exempel *Motiv*, *Motiveringar*, *Motiv till planens bestämmelser* eller *Skäl
till bestämmelserna*.

Hittas inga motiv:

1. Kontrollen säger vilken rubrik som inte känns igen.
2. Välj temat *Motiv till detaljplanens regleringar* för rubriken i listan.
3. Motiven hittas. Valet sparas till nästa dokument med samma rubrik.

> Motiv som står utspridda under andra rubriker, till exempel under varje användning, hittas inte automatiskt.
