"""En liten syntetisk plan som Rita Detaljplan sparar den (bara tabellerna som läses, utan geometri), ett QGIS-projekt
som pekar på den, och en planbeskrivning som hör till planen. Används av testerna och av ``tools/skapa_exempel.py``."""
import json
import sqlite3
import uuid
import zipfile
from pathlib import Path

from docx_case import make_docx, para, wrap
from rita_detaljplan.planbeskrivning.pbkarna.geometri import gpkg_blob

PLAN_ID = "7f3c2b10-5d4e-4a8b-9c21-0e6f3d2ba91e"


def _uuid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "kv-larkan/" + seed))


def _value(name: str, value: str) -> str:
    return json.dumps([{"beskrivning": name, "variabelvarde": value}], ensure_ascii=False)


# (tabell, beteckning, formulering, värden (JSON) eller None, ytor)
BESTAMMELSER = [
    ("anvandning_yta", "B", "Bostäder", None, ["q1", "q2", "q3"]),
    ("anvandning_yta", "GATA", "Gata", None, ["gata"]),
    ("anvandning_yta", "PARK", "Park", None, ["park"]),
    ("egenskap_yta", "e1", "Största byggnadsarea är [procent:decimaltal] % av fastighetsarean",
     _value("procent", "30"), ["q1", "q2", "q3"]),
    ("egenskap_yta", "h1", "Högsta nockhöjd är [höjd:decimaltal] meter", _value("höjd", "14,0"), ["q1", "q3"]),
    ("egenskap_yta", "p1", "Huvudbyggnad ska placeras minst [avstånd:decimaltal] meter från fastighetsgräns",
     _value("avstånd", "4,0"), ["q1", "q2", "q3"]),
    ("egenskap_yta", "f1", "Endast radhus", None, ["q3"]),
    ("egenskap_yta", "b1", "Källare får inte finnas", None, ["q1", "q2", "q3"]),
    ("egenskap_yta", "n1", "Högst [procent:decimaltal] % av fastighetsarean får hårdgöras", _value("procent", "50"),
     ["q1", "q2", "q3"]),
    ("egenskap_yta", "k1", "Fasader ska behålla puts och fönstersättning", None, ["q2"]),
    ("egenskap_yta", "r1", "Byggnaden får inte rivas", None, ["q2"]),
    ("egenskap_yta", "u1", "Markreservat för allmännyttiga underjordiska ledningar", None, ["u"]),
]


# Ytorna i kartan (x0, y0, x1, y1 i meter, y nedåt som i skissen): (namn, lager, beteckning)
YTOR = [
    ("q1", "anvandning_yta", "B", (10, 10, 140, 115)),
    ("q2", "anvandning_yta", "B", (146, 10, 214, 115)),
    ("q3", "anvandning_yta", "B", (10, 145, 214, 190)),
    ("gata", "anvandning_yta", "GATA", (10, 121, 214, 139)),
    ("park", "anvandning_yta", "PARK", (220, 10, 290, 190)),
    ("u", "egenskap_yta", "u1", (10, 100, 140, 115)),
]
PLANGRANS = (6, 6, 294, 194)


def _ring(box):
    x0, y0, x1, y1 = box
    e, n = 150000, 6500200  # SWEREF 99 TM-liknande, y vänds så att norr är uppåt
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    return [(e + x, n - y) for x, y in pts]


def make_geopackage(path: Path, plan_id: str = PLAN_ID, bestammelser=None, motiv: dict | None = None,
                    geometry: bool = True) -> Path:
    """Tabellerna ``detaljplan`` och ``bestammelse`` med de kolumner som läses, och (med ``geometry``) ytorna i
    ``anvandning_yta`` och ``egenskap_yta``. ``motiv``: {beteckning: text}."""
    path = Path(path)
    path.unlink(missing_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE detaljplan (fid INTEGER PRIMARY KEY, geom BLOB, objektidentitet TEXT, namn TEXT, "
                "beteckning TEXT, syfte TEXT, kommun TEXT)")
    con.execute("INSERT INTO detaljplan (objektidentitet, namn, beteckning, syfte, kommun, geom) VALUES (?,?,?,?,?,?)",
                (plan_id, "Detaljplan för kv. Lärkan", "1485-P2026/3", "", "1485",
                 gpkg_blob([_ring(PLANGRANS)]) if geometry else None))
    if geometry:
        con.execute("CREATE TABLE gpkg_geometry_columns (table_name TEXT, column_name TEXT)")
        con.execute("INSERT INTO gpkg_geometry_columns VALUES ('detaljplan', 'geom')")
        for table in ("anvandning_yta", "egenskap_yta"):
            con.execute(f"CREATE TABLE {table} (fid INTEGER PRIMARY KEY, geom BLOB, objektidentitet TEXT, "
                        "detaljplan TEXT, beteckning TEXT)")
            con.execute("INSERT INTO gpkg_geometry_columns VALUES (?, 'geom')", (table,))
        for name, table, label, box in YTOR:
            con.execute(f"INSERT INTO {table} (geom, objektidentitet, detaljplan, beteckning) VALUES (?,?,?,?)",
                        (gpkg_blob([_ring(box)]), _uuid("yta/" + name), plan_id, label))
    con.execute("CREATE TABLE bestammelse (fid INTEGER PRIMARY KEY, objektidentitet TEXT, detaljplan TEXT, tabell TEXT, "
                "yta TEXT, beteckning TEXT, ordning INTEGER, planbestammelsekatalogreferens TEXT, "
                "bestammelseformulering TEXT, bestammelsevarde TEXT, motiv TEXT)")
    for n, (table, label, text, values, areas) in enumerate(bestammelser or BESTAMMELSER):
        for area in areas:
            con.execute("INSERT INTO bestammelse (objektidentitet, detaljplan, tabell, yta, beteckning, ordning, "
                        "planbestammelsekatalogreferens, bestammelseformulering, bestammelsevarde, motiv) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (_uuid(f"{label}/{area}"), plan_id, table, _uuid("yta/" + area), label, n,
                         _uuid("katalog/" + text), text, values, (motiv or {}).get(label)))
    con.commit()
    con.close()
    return path


def make_project(path: Path, gpkg_name: str, provider: str = "ogr") -> Path:
    """Ett QGIS-projekt (.qgz eller .qgs) med planens lager, som pekar på GeoPackage-filen med en relativ sökväg."""
    path = Path(path)
    layers = "".join(
        f"<maplayer type=\"vector\"><id>{name}_1</id><datasource>./{gpkg_name}|layername={name}</datasource>"
        f"<layername>{name}</layername><provider encoding=\"UTF-8\">{provider}</provider></maplayer>"
        for name in ("detaljplan", "anvandning_yta", "egenskap_yta", "bestammelse"))
    if provider == "postgres":
        layers = layers.replace(f"./{gpkg_name}|layername=bestammelse",
                                "dbname='plan' host=localhost table=\"plan\".\"bestammelse\"")
    xml = f'<!DOCTYPE qgis><qgis projectname="kv Lärkan" version="3.40.0"><projectlayers>{layers}</projectlayers></qgis>'
    if path.suffix.lower() == ".qgz":
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(path.with_suffix(".qgs").name, xml)
    else:
        path.write_text(xml, encoding="utf-8")
    return path


def _table(rows: list[tuple[str, str, str]]) -> str:
    cells = "".join(
        f"<w:tr><w:tc>{para(label)}</w:tc><w:tc>{para(title)}{para(text)}</w:tc></w:tr>" for label, title, text in rows)
    return f"<w:tbl><w:tblPr/><w:tblGrid><w:gridCol/><w:gridCol/></w:tblGrid>{cells}</w:tbl>"


def larkan_body() -> str:
    """Planbeskrivningen för kv. Lärkan: BFS-rubriker, några rubriker som bara liknar BFS, en motivtabell, motiv i löpande
    text och en rubrik som inte finns i BFS."""
    h1, h2, h3 = (lambda t: para(t, "Rubrik1")), (lambda t: para(t, "Rubrik2")), (lambda t: para(t, "Rubrik3"))
    return wrap(
        h1("DETALJPLANENS SYFTE") + h2("Syfte")
        + para("Syftet med detaljplanen är att möjliggöra cirka 40 nya bostäder i form av radhus och flerbostadshus, och "
               "att säkerställa att den befintliga parken mot Bäckdalen bevaras som allmän plats.")
        + h1("BESKRIVNING AV DETALJPLANEN") + h2("Hela detaljplanen")
        + para("Planområdet ligger cirka 1,5 km norr om Exempelstads centrum och omfattar drygt 2,4 hektar.")
        + h2("Kvartersmark")
        + para("Radhus i två våningar placeras mot villabebyggelsen i söder, och flerbostadshus i högst fyra våningar "
               "mot Västra vägen.")
        + h2("Allmän plats") + h3("Huvudmannaskap")
        + para("Kommunen är huvudman för allmän plats. Lärkvägen förlängs och parken ansluts med en gång- och cykelväg.")
        + h2("Genomförandetid") + para("Genomförandetiden är fem år från den dag planen vinner laga kraft.")
        + h1("MOTIV TILL DETALJPLANENS REGLERINGAR") + h2("Motiv till reglering")
        + para("Här redovisas skälen till planens bestämmelser.")
        + h3("Användning av mark")
        + _table([
            ("B", "Bostäder", "Användningen följer översiktsplanens inriktning och svarar mot behovet av bostäder."),
            ("GATA", "Gata", "Lärkvägen förlängs som allmän plats så att kommunen ansvarar för drift och underhåll."),
            ("PARK", "Park", "Parken säkerställs för att bevara grönstrukturen mot Bäckdalen och ge plats för lek."),
        ])
        + h3("Egenskaper")
        + _table([
            ("e1", "Största byggnadsarea är 30 % av fastighetsarean",
             "Byggnadsarean begränsas så att det blir tillräckligt med friyta för uteplatser och dagvatten."),
            ("h1", "Högsta nockhöjd är 14,0 meter",
             "Nockhöjden anpassas till villabebyggelsen i söder och tillåter fyra våningar mot Västra vägen."),
            ("", "Huvudbyggnad ska placeras minst 4,0 meter från fastighetsgräns",
             "Avståndet ger utrymme för underhåll av fasader och minskar risken för brandspridning."),
            ("b1", "Källare får inte finnas", "Grundvattnet ligger högt och marken består av lera."),
            ("k", "Varsamhet", "Villan på Lärkan 3 från 1912 är en del av riksintresset för kulturmiljövården."),
        ])
        + para("n1 Högst 50 % av fastighetsarean får hårdgöras. Bestämmelsen gör att dagvatten kan infiltreras inom "
               "kvartersmark.")
        + para("r1 Byggnaden får inte rivas.") + para("Villan är kulturhistoriskt värdefull och ska bevaras.")
        + h1("PLANERINGSFÖRUTSÄTTNINGAR") + h2("Kommunala") + h3("Översiktsplan")
        + para("I översiktsplanen (antagen 2022) är området utpekat för ny bebyggelse med inriktning på bostäder.")
        + h3("Detaljplan") + para("För området gäller detaljplan 1485-P78/12 som anger allmänt ändamål.")
        + h2("Riksintressen") + h3("Kulturmiljövård")
        + para("Området ligger inom riksintresse för kulturmiljövården enligt 3 kap. 6 § miljöbalken.")
        + h2("Hälsa och säkerhet") + h3("Buller")
        + para("Trafikbullret från Västra vägen ger högst 58 dBA ekvivalent ljudnivå vid fasad.")
        + h2("Geotekniska förhållanden")
        + para("Marken består av lera på friktionsjord. Grundläggning kan ske utan pålning.")
        + h2("Dagvattenhantering")
        + para("Dagvattnet ska fördröjas inom kvartersmark innan det leds till det kommunala nätet.")
        + h1("KONSEKVENSER") + h2("Sociala") + h3("Barn")
        + para("Parken bevaras och får en ny lekplats. Gång- och cykelvägen ger en trafiksäker väg till Lärkskolan.")
        + h2("Miljökvalitetsnormer") + h3("Vatten")
        + para("Planen bedöms inte försämra möjligheten att uppnå miljökvalitetsnormerna för Bäckdalsån.")
        + h1("GENOMFÖRANDEFRÅGOR") + h2("Fastighetsrättsliga frågor") + h3("Förändrad fastighetsindelning")
        + para("Lärkan 3 behöver regleras mot kommunens fastighet Exempelstad 4:12.")
        + h2("Ekonomiska frågor") + h3("Planavgift")
        + para("Planavgift tas inte ut vid bygglov, eftersom planarbetet bekostas genom ett planavtal.")
        + h1("MEDVERKANDE")
        + para("Planbeskrivningen har tagits fram av planenheten på samhällsbyggnadsförvaltningen."))


def make_larkan(folder: Path) -> dict:
    """Skriver hela exemplet i ``folder``: planbeskrivning, GeoPackage och QGIS-projekt. Returnerar sökvägarna."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    return {
        "docx": make_docx(folder / "Planbeskrivning_kv_Larkan.docx", larkan_body()),
        "gpkg": make_geopackage(folder / "kv_Larkan.gpkg"),
        "qgz": make_project(folder / "Detaljplan_kv_Larkan.qgz", "kv_Larkan.gpkg"),
    }
