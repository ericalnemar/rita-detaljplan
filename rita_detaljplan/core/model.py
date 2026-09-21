"""Datamodell (GeoPackage-schema) för detaljplaner enligt Nationell informationsspecifikation Detaljplan 4.1.

Kolumnnamn är identiska med fältnamnen i Lantmäteriets JSON-schema (detaljplan-4.1.json), så att
exporten till NGP blir en direkt avbildning. Modellen är ren Python och kräver inte QGIS.

Avvikelser från JSON-strukturen (löses i exporten):
  * geometri och geometrimetadata ligger som kolumner (``lagesmetodTyp`` m.fl.) i stället för
    som nästlade objekt;
  * listor (t.ex. ``datumLagakraft``) lagras som semikolonseparerad text eller som flera rader;
  * ytor (användning, egenskap) är geometrilager och bestämmelserna ligger i tabellen ``bestammelse`` med en rad
    per bestämmelse: en yta kan ha flera bestämmelser, och vid leverans blir varje rad ett planbestämmelseobjekt
    med ytans geometri.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import codelists as cl

SPEC_VERSION = "4.1"
MEDIATYP = "application/vnd.lm.detaljplan.v4+json"
SCHEMA_VERSION = 6  # schemaversion (3: ytor + bestämmelsetabell; 4: + hjälplinjer; 5: + textens läge; 6: + ordning)

# Fälttyper
TEXT, INT, REAL, DATE, DATETIME, BOOL = "text", "int", "real", "date", "datetime", "bool"

# Uttryck som QGIS använder för standardvärden.
UUID_EXPR = "lower(uuid('WithoutBraces'))"
NOW_EXPR = "now()"


@dataclass(frozen=True)
class FieldDef:
    name: str
    type: str
    alias: str
    required: bool = False  # obligatoriskt enligt specifikationen (mjuk begränsning i QGIS)
    codelist: Optional[tuple[str, ...]] = None
    default: Optional[str] = None  # QGIS-uttryck
    length: int = 0
    multiline: bool = False
    comment: str = ""


@dataclass(frozen=True)
class LayerDef:
    name: str  # tabellnamn i GeoPackage
    alias: str
    geometry: Optional[str]  # "MultiPolygon" | "MultiLineString" | "MultiPoint" | None (attributtabell)
    fields: tuple[FieldDef, ...]
    description: str = ""


# --------------------------------------------------------------------------------------
# Återanvändbara fältgrupper
# --------------------------------------------------------------------------------------

def _identitet() -> tuple[FieldDef, ...]:
    return (
        FieldDef("objektidentitet", TEXT, "Objektidentitet", True, default=UUID_EXPR, length=36,
                 comment="Global unik identitet (UUID), skapas automatiskt."),
        FieldDef("objektversion", INT, "Objektversion", default="1"),
        FieldDef("versionGiltigFran", DATETIME, "Version giltig från", True, default=NOW_EXPR),
    )


def _geometrimetadata() -> tuple[FieldDef, ...]:
    return (
        FieldDef("lagesmetodTyp", TEXT, "Lägesbestämningsmetod i plan", False,
                 codelist=tuple(cl.LAGESMETODER), default="'lägesplacering'",
                 comment="Obligatorisk för planer påbörjade efter 2021-12-31."),
        FieldDef("lagesmetodVariant", TEXT, "Variant av lägesbestämningsmetod", False,
                 codelist=_alla_varianter(), default="'digital karta'"),
        FieldDef("tidpunktForLagesbestamning", DATETIME, "Tidpunkt för lägesbestämning i plan", False,
                 default=NOW_EXPR, comment="Obligatorisk för planer påbörjade efter 2021-12-31."),
        FieldDef("absolutLagesosakerhetPlan", REAL, "Absolut lägesosäkerhet i plan (m)"),
        FieldDef("presentationsskala", INT, "Presentationsskala"),
        FieldDef("tidpunktForKontrollAvGeometri", DATETIME, "Tidpunkt för kontroll av geometri"),
    )


def _alla_varianter() -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for variants in cl.LAGESMETODER.values():
        for v in variants:
            seen.setdefault(v)
    return tuple(seen)


def _kvalitet(required: bool) -> tuple[FieldDef, ...]:
    return (
        FieldDef("digitaliseringsniva", TEXT, "Digitaliseringsnivå", False, codelist=cl.DIGITALISERINGSNIVA),
        FieldDef("beskrivningNiva", TEXT, "Beskrivning av nivå"),
        FieldDef("korrigeradeGranser", BOOL, "Korrigerade gränser", required, default="false" if required else None),
        FieldDef("kontrolleratPlaneringsunderlag", BOOL, "Kontrollerat planeringsunderlag", required,
                 default="false" if required else None),
        FieldDef("anvandbarhet", TEXT, "Användbarhet", False, codelist=cl.TILLFORLITLIGHET),
        FieldDef("beskrivningAnvandbarhet", TEXT, "Beskrivning av användbarhet"),
    )


# --------------------------------------------------------------------------------------
# Lager och tabeller
# --------------------------------------------------------------------------------------

DETALJPLAN = LayerDef(
    name="detaljplan",
    alias="Detaljplan (planområde)",
    geometry="MultiPolygon",
    description="Detaljplanens utbredning (plangeometri) med planens egenskaper.",
    fields=(
        *_identitet(),
        FieldDef("kommun", TEXT, "Kommun", True),
        FieldDef("beteckning", TEXT, "Beteckning"),
        FieldDef("namn", TEXT, "Namn", True),
        FieldDef("syfte", TEXT, "Syfte", True, length=4000, multiline=True),
        FieldDef("status", TEXT, "Status", True, codelist=cl.PLANSTATUS, default="'påbörjad'"),
        FieldDef("datumStatusforandring", DATE, "Datum för statusförändring"),
        FieldDef("typ", TEXT, "Plantyp", True, codelist=cl.PLANTYP, default="'detaljplan'"),
        *_kvalitet(required=True),
        FieldDef("vertikalAvgransning", TEXT, "Vertikal avgränsning", codelist=cl.AVGRANSNING),
        *_geometrimetadata(),
    ),
)

BESLUTSINFORMATION = LayerDef(
    name="beslutsinformation",
    alias="Beslutsinformation",
    geometry=None,
    description="Beslut om detaljplanen. En rad per beslut; minst en rad krävs.",
    fields=(
        FieldDef("detaljplan", TEXT, "Detaljplan (objektidentitet)", True, length=36),
        FieldDef("instansInomKommunen", TEXT, "Instans inom kommunen", codelist=cl.KOMMUNINSTANS),
        FieldDef("diarienummerKommun", TEXT, "Diarienummer kommun"),
        FieldDef("diarienummerFullmaktige", TEXT, "Diarienummer fullmäktige"),
        FieldDef("beslutstyp", TEXT, "Beslutstyp", codelist=cl.BESLUTSTYP),
        FieldDef("datumPaborjat", DATE, "Datum påbörjat"),
        FieldDef("datumAntagande", DATE, "Datum antagande"),
        FieldDef("datumLagakraft", TEXT, "Datum laga kraft",
                 comment="Ett eller flera datum (ÅÅÅÅ-MM-DD), separerade med semikolon."),
        FieldDef("genomforandetid", INT, "Genomförandetid (månader)"),
        FieldDef("genomforandetidStartar", DATE, "Genomförandetid startar"),
        FieldDef("arkividentitetKommun", TEXT, "Arkividentitet kommun"),
        FieldDef("foregaendePlansBeteckning", TEXT, "Föregående plans beteckning",
                 comment="Flera värden separeras med semikolon."),
        FieldDef("berordDomsMalnummer", TEXT, "Berörd doms målnummer", comment="Flera värden separeras med semikolon."),
    ),
)

# Kolumner som bara pluginet använder (ingår inte i leveransen till NGP).
PLUGIN_ONLY_FIELDS = ("tabell", "yta", "beteckning", "beteckningsindex", "bestammelsekod", "anvandningsform", "farg",
                      "symbol", "avviker", "bestammelser", "label_x", "label_y", "ordning")


# Textens läge på plankartan när användaren flyttat den (tomt = automatisk placering). Bara för pluginet.
LABEL_FIELDS = (
    FieldDef("label_x", REAL, "Textens läge (x)", comment="Sätts när texten flyttas med textverktyget."),
    FieldDef("label_y", REAL, "Textens läge (y)", comment="Sätts när texten flyttas med textverktyget."),
)


def _area_fields() -> tuple[FieldDef, ...]:
    """Fält för ett ytlager (användning, egenskap): geometrin med de uppgifter som behövs för att rita den.
    Själva bestämmelserna ligger i tabellen ``bestammelse`` (en rad per bestämmelse, flera per yta)."""
    return (
        *_identitet(),
        FieldDef("detaljplan", TEXT, "Detaljplan (objektidentitet)", True, length=36),
        FieldDef("beteckning", TEXT, "Beteckning på plankartan",
                 comment="Sammansatt av ytans bestämmelser (t.ex. BC eller e1 a2). Sätts av pluginet."),
        FieldDef("farg", TEXT, "Färg", comment="Färgnamn från Boverkets katalog (användning)."),
        FieldDef("symbol", TEXT, "Symbol", comment="Symbol från Boverkets katalog (t.ex. prickmark)."),
        FieldDef("anvandningsform", TEXT, "Användningsform", comment="Allmän plats, kvartersmark eller vattenområde."),
        FieldDef("bestammelser", INT, "Antal bestämmelser", default="0"),
        *LABEL_FIELDS,
        *_geometrimetadata(),
    )


ANVANDNING_YTA = LayerDef("anvandning_yta", "Användning (yta)", "MultiPolygon", _area_fields(),
                          "Användningsytor: vad marken får användas till. Bestämmelserna ligger i tabellen bestammelse.")
EGENSKAP_YTA = LayerDef("egenskap_yta", "Egenskap (yta)", "MultiPolygon", _area_fields(),
                        "Egenskapsytor. Ska ligga inom användningsytor; en yta kan ha flera egenskapsbestämmelser.")
EGENSKAP_LINJE = LayerDef("egenskap_linje", "Egenskap (linje)", "MultiLineString", _area_fields(),
                          "Egenskapslinjer: endast utfartsförbud och stängsel. Ska ligga på en användningsyta.")

# Bestämmelsernas inbördes ordning på en yta (styr ordningen i beteckningen). Bara för pluginet.
ORDNING = FieldDef("ordning", INT, "Ordning", comment="Ordning bland ytans bestämmelser. Sätts av pluginet.")

BESTAMMELSE = LayerDef(
    name="bestammelse",
    alias="Planbestämmelser",
    geometry=None,
    description=("Tilldelade planbestämmelser: en rad per bestämmelse och yta. Vid leverans blir varje rad ett "
                 "planbestämmelseobjekt med ytans geometri."),
    fields=(
        *_identitet(),
        FieldDef("detaljplan", TEXT, "Detaljplan (objektidentitet)", True, length=36),
        FieldDef("tabell", TEXT, "Ytlager", True, comment="Vilket ytlager bestämmelsen hör till."),
        FieldDef("yta", TEXT, "Yta (objektidentitet)", True, length=36),
        FieldDef("beteckning", TEXT, "Beteckning på plankartan"),
        FieldDef("beteckningsindex", INT, "Index i beteckningen"),
        ORDNING,
        FieldDef("planbestammelsekatalogreferens", TEXT, "Planbestämmelsekatalogens UUID", True, length=36,
                 comment="UUID för bestämmelsen i Boverkets planbestämmelsekatalog (sätts av pluginet)."),
        FieldDef("bestammelsekod", TEXT, "Bestämmelsekod", comment="Boverkets bestämmelsekod (inte del av leveransen)."),
        FieldDef("anvandningsform", TEXT, "Användningsform"),
        FieldDef("farg", TEXT, "Färg"),
        FieldDef("symbol", TEXT, "Symbol"),
        FieldDef("bestammelseformulering", TEXT, "Bestämmelseformulering", True, multiline=True),
        FieldDef("avviker", BOOL, "Avviker från katalogen", default="false"),
        FieldDef("ursprungligBestammelseformulering", TEXT, "Ursprunglig bestämmelseformulering", multiline=True),
        FieldDef("bestammelsevarde", TEXT, "Bestämmelsevärden (JSON)", multiline=True,
                 comment="Lista med variabelvärden som JSON, se schemat 'variabelvarde'."),
        FieldDef("motiv", TEXT, "Motiv (planbestämmelsebeskrivning)", multiline=True),
        *_kvalitet(required=False),
        FieldDef("vertikalAvgransning", TEXT, "Vertikal avgränsning", codelist=cl.AVGRANSNING),
        FieldDef("giltighetstid", INT, "Giltighetstid (månader)", comment="Endast användningsbestämmelser."),
        FieldDef("borjarGallaEfter", INT, "Börjar gälla efter (månader)", comment="Endast användningsbestämmelser."),
        FieldDef("sekundarEgenskapsgrans", BOOL, "Sekundär egenskapsgräns", comment="Endast egenskapsbestämmelser."),
        FieldDef("reglerarDetaljplan", TEXT, "Reglerar detaljplan (UUID)", length=36),
    ),
)

HJALPLINJE = LayerDef(
    name="hjalplinje",
    alias="Hjälplinjer",
    geometry="MultiLineString",
    description="Konstruktionslinjer som hjälp vid ritningen. Ingår aldrig i leveransen till NGP.",
    fields=(
        FieldDef("objektidentitet", TEXT, "Objektidentitet", True, default=UUID_EXPR, length=36),
        FieldDef("beskrivning", TEXT, "Beskrivning"),
    ),
)
# Tabeller som bara finns för användarens skull och som aldrig exporteras till NGP.
NOT_DELIVERED = ("hjalplinje", "dp_meta")

# Handlingsroller i tabellen ``dokument``
DOKUMENTROLLER = ("planbeskrivning", "beslutshandling", "planeringsunderlag")

DOKUMENT = LayerDef(
    name="dokument",
    alias="Dokument (handlingar och underlag)",
    geometry=None,
    description="Planbeskrivning, beslutshandlingar (plankarta, beslutsprotokoll) och planeringsunderlag.",
    fields=(
        FieldDef("detaljplan", TEXT, "Detaljplan (objektidentitet)", True, length=36),
        FieldDef("roll", TEXT, "Roll", True, codelist=DOKUMENTROLLER),
        FieldDef("innehall", TEXT, "Innehåll", codelist=cl.INNEHALL, comment="Endast beslutshandlingar."),
        FieldDef("huvudomrade", TEXT, "Huvudområde", codelist=cl.HUVUDOMRADE, comment="Endast planeringsunderlag."),
        FieldDef("underlagstyp", TEXT, "Underlagstyp", codelist=cl.UNDERLAGSTYP, comment="Endast planeringsunderlag."),
        FieldDef("namn", TEXT, "Namn", True),
        FieldDef("kortnamn", TEXT, "Kortnamn"),
        FieldDef("datum", DATE, "Datum"),
        FieldDef("handelse", TEXT, "Händelse", codelist=cl.RESURSHANDELSE),
        FieldDef("lank", TEXT, "Länk (https)"),
        FieldDef("referensIdentitet", TEXT, "Referensidentitet (UUID)", length=36,
                 comment="Sätts när dokumentet laddats upp till NGP."),
        FieldDef("specifikReferens", TEXT, "Specifik referens", comment="Flera värden separeras med semikolon."),
    ),
)

# Lagrens ordning = ordning i lagerträdet i QGIS (överst först). Ordningen avgör hierarkin i kartan: där
# kantlinjer sammanfaller täcker det översta lagret det undre (planområde > användning > egenskap).
LAYERS: tuple[LayerDef, ...] = (
    HJALPLINJE,
    EGENSKAP_LINJE,
    DETALJPLAN,
    ANVANDNING_YTA,
    EGENSKAP_YTA,
    BESTAMMELSE,
    BESLUTSINFORMATION,
    DOKUMENT,
)
AREA_LAYERS = (ANVANDNING_YTA, EGENSKAP_YTA, EGENSKAP_LINJE)

# Relationer: (namn, barnlager, barnfält, föräldrafält)
RELATIONS = (
    ("detaljplan_beslutsinformation", "beslutsinformation", "detaljplan", "objektidentitet"),
    ("detaljplan_dokument", "dokument", "detaljplan", "objektidentitet"),
    ("detaljplan_anvandning", "anvandning_yta", "detaljplan", "objektidentitet"),
    ("detaljplan_egenskap_yta", "egenskap_yta", "detaljplan", "objektidentitet"),
    ("detaljplan_egenskap_linje", "egenskap_linje", "detaljplan", "objektidentitet"),
    ("detaljplan_bestammelse", "bestammelse", "detaljplan", "objektidentitet"),
)

META_TABLE = "dp_meta"


def layer_by_name(name: str) -> LayerDef:
    for layer in LAYERS:
        if layer.name == name:
            return layer
    raise KeyError(name)
