# Teckenförklaring och plankarta

Pluginet skapar planens **teckenförklaring** i QGIS layoutläge. Vill du ha en färdig utgångspunkt för hela plankartan
finns också **exempellayouter** i A1–A4, liggande och stående, med karta, teckenförklaring, norrpil, skalstock och
titelruta.

<!-- FILM: teckenforklaring | Skapa och anpassa teckenförklaringen i en layout, ca 2 min -->

## Exempellayout för plankartan

1. Välj **Rita Detaljplan → Skapa exempellayout för plankarta…**.
2. Välj **pappersformat**: A1, A2, A3 eller A4, liggande eller stående. A2 liggande är förvalt om planen ryms där i
   referensskalan, annars A1 liggande.
3. En ny layout skapas och öppnas med
   - **kartan** i planens referensskala och med planområdet i mitten, med koordinatkryss i kanten,
   - **teckenförklaringen** till höger om kartan (liggande) eller under den (stående),
   - **norrpil**, **skala** (till exempel *1:1 000 (A2)*) och **skalstock**,
   - **grundkartans beteckningar** och **upplysningar** (plan- och bygglagen, koordinat- och höjdsystem),
   - en **titelruta** med skede (till exempel *SAMRÅDSHANDLING*), planens namn, kommun, ritad av, datum och rader för
     antagande och laga kraft.
4. Lägg till grundkartan i kartan och anpassa resten, till exempel kommunens logotyp, färger, typsnitt och vem som ritat
   planen.
5. Spara layouten som mall med **Layout → Spara som mall…**, så kan du använda den för nästa plan.

<!-- BILD: exempellayout.png | Exempellayouten: karta, teckenförklaring, norrpil, skalstock och titelruta på A2 -->

Exempellayouterna är en **utgångspunkt**, inte mallar som bestämmer hur kommunens plankartor ska se ut. Alla åtta är samma
plankarta: de liggande är samma sida i olika storlek, och de stående har kartan överst. Skedet, planens namn, kommunen och
datumen för antagande och laga kraft hämtas från *Planens uppgifter* när layouten skapas; det som saknas står som
*202x-xx-xx*. Ändrar du uppgifterna senare skapar du en ny exempellayout eller skriver om texten i layouten.

Mallarna finns också som vanliga QGIS-mallar (`.qpt`) i pluginets mapp `data/layouts/`, så att du kan öppna dem i
layoutläget och göra en egen mall av dem. Den streckade rutan *Plats för teckenförklaring* visar var teckenförklaringen
ska ligga och skrivs inte ut.

> Ryms inte planen i kartan i referensskalan i det format du valt får du en varning. Ändra då skalan i kartans
> egenskaper eller välj ett större format.

## Skapa teckenförklaringen

1. Öppna eller skapa en **layout** i QGIS.
2. Vill du bestämma var teckenförklaringen ska ligga: rita ett objekt, till exempel en rektangel, och markera det.
   Teckenförklaringen fyller då den ytan. Annars läggs den längst till höger på sidan.
3. Klicka på **Teckenförklaring** i verktygsfältet *Rita Detaljplan* i layoutfönstret.

<!-- BILD: teckenforklaring-layout.png | En layout med en färdig teckenförklaring till höger om kartan -->

Teckenförklaringen blir en grupp som du kan flytta. Klickar du på knappen igen ersätts den på samma plats, till exempel
när du ändrat i planen.

Är den för lång för ytan görs den mindre eller delas i två kolumner, och du får en varning.

> Syns inte verktygsfältet? Det kan döljas under menyn *Visa* eller med högerklick på verktygsfälten i layoutfönstret.

## Vad som kommer med

- Rubrikerna **PLANBESTÄMMELSER**, **GRÄNSLINJER**, **ANVÄNDNING AV …** och **EGENSKAPSBESTÄMMELSER FÖR …**, med
  kategorier.
- Längst ned **GENOMFÖRANDETID**.
- Färgrutor och mönster med samma symboler som i kartan.
- Beteckningar med nedsänkta siffror.

## Anpassa utseendet

Klicka på **Inställningar för teckenförklaring** bredvid knappen. Där ställer du in

- teckensnitt,
- storlek på rubriker och texter,
- storlek på rutor och linjer,
- avstånd mellan ruta och text, rader, underrubriker, rubriker och kolumner,
- om den inledande texten ska vara med,
- om allt ska skalas efter sidans bredd. Måtten gäller A1.

Inställningarna sparas i din QGIS-profil. En teckenförklaring som redan finns görs om på samma plats.

> Standardteckensnittet är **Arial**. Finns det inte på datorn väljer QGIS ett annat. Byt i så fall teckensnitt i
> inställningarna.

## Utskrift och symbologi

Symbologin följer Boverkets föreskrifter och kommer från stilbiblioteket
[Detaljplaner (Bfs 2020:6)](https://hub.qgis.org/styles/238/).

Användningens färg ritas med blandningsläget *Multiplicera*, så att grundkartans byggnader och gränser syns genom
färgen. En PDF med vektorutskrift har inget blandningsläge. Där täcker användningens färg grundkartan, men
egenskapernas mönster syns.
