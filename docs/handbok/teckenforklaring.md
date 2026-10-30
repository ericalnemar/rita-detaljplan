# Teckenförklaring och plankarta

Pluginet skapar planens **teckenförklaring** i QGIS layoutläge. Vill du ha en färdig utgångspunkt för hela plankartan
finns också en **exempellayout** med karta, teckenförklaring, norrpil, skalstock och titelruta.

<!-- FILM: teckenforklaring | Skapa och anpassa teckenförklaringen i en layout, ca 2 min -->

## Exempellayout för plankartan

1. Välj **Rita Detaljplan → Skapa exempellayout för plankarta…**.
2. En ny layout skapas och öppnas: en A2-sida i liggande format med
   - **kartan** till vänster, i planens referensskala och med planområdet i mitten,
   - **teckenförklaringen** överst till höger,
   - **norrpil** och **skalstock** under den,
   - en **titelruta** längst ned till höger med kommun, planens namn, skede (till exempel *Samrådshandling*), skala,
     planbeteckning, diarienummer, datum och rader att fylla i.
3. Lägg till grundkartan i kartan och anpassa resten, till exempel kommunens logotyp, färger och typsnitt.
4. Spara layouten som mall med **Layout → Spara som mall…**, så kan du använda den för nästa plan.

<!-- BILD: exempellayout.png | Exempellayouten: karta, teckenförklaring, norrpil, skalstock och titelruta på A2 -->

Exempellayouten är en **utgångspunkt**, inte en mall som bestämmer hur kommunens plankartor ska se ut. Uppgifterna i
titelrutan hämtas från *Planens uppgifter* när layouten skapas. Ändrar du dem senare skapar du en ny exempellayout eller
skriver om texten i layouten.

> Ryms inte planen i kartan i referensskalan på A2 får du en varning. Ändra då skalan i kartans egenskaper eller byt
> till en större sida.

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
