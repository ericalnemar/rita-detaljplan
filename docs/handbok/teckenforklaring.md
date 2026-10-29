# Teckenförklaring

Pluginet skapar planens **teckenförklaring** i QGIS layoutläge. Kartan, titelblocket och resten av plankartan gör du
själv i layouten.

<!-- FILM: teckenforklaring | Skapa och anpassa teckenförklaringen i en layout, ca 2 min -->

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
