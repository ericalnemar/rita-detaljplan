"""Kodlistor (värdemängder) för Nationell informationsspecifikation Detaljplan 4.1.

AUTOGENERERAD av tools/generate_codelists.py från spec/*.json. Redigera inte för hand.
"""

PLANSTATUS = (
    "påbörjad",
    "samråd",
    "granskning",
    "antagen",
    "överklagad",
    "tillsyn",
    "laga kraft",
    "upphävd",
    "avslutad",
)

PLANTYP = (
    "avstyckningsplan",
    "byggnadsplan",
    "detaljplan",
    "stadsplan",
)

DIGITALISERINGSNIVA = (
    "komplett",
    "ej komplett",
)

TILLFORLITLIGHET = (
    "god",
    "medel",
    "låg",
)

AVGRANSNING = (
    "uppåt",
    "nedåt",
)

KOMMUNINSTANS = (
    "byggnadsnämnd enligt PBL",
    "kommunstyrelse",
    "kommunfullmäktige",
)

BESLUTSTYP = (
    "antagande av ny detaljplan",
    "antagande om ändring",
    "antagande om upphävande",
    "beslut om avslut",
)

INNEHALL = (
    "plankarta",
    "beslutsprotokoll",
    "övrigt",
)

RESURSHANDELSE = (
    "skapad",
    "publicerad",
    "reviderad",
)

HUVUDOMRADE = (
    "kommunala",
    "utredningar",
    "regionala",
    "annat",
)

UNDERLAGSTYP = (
    "barnkonsekvensanalys",
    "bullerutredning",
    "dagsljus och skugga",
    "dagvattenutredning",
    "detaljplan",
    "förprojektering",
    "geoteknisk utredning",
    "grundkarta",
    "handelsutredning",
    "kulturmiljöutredning",
    "markmiljöutredning",
    "miljökonsekvensbeskrivning",
    "naturinventering",
    "planprogram",
    "regionplan",
    "riskutredning",
    "särskilt beslut om betydande miljöpåverkan",
    "trafikutredning",
    "undersökning enligt 6 kap. 6 § plan- och bygglagen (2010:900)",
    "översiktsplan",
    "annat",
)

VARIABELTYP = (
    "text",
    "decimaltal",
)

VARDETYP = (
    "min",
    "max",
    "exakt",
)

ENHET = (
    "meter",
    "kvadratmeter",
    "kubikmeter",
    "procent",
    "grader",
    "antal",
    "år",
    "dB(A)",
)

KOORDINATSYSTEM_PLAN = (
    "EPSG:3006",
    "EPSG:3007",
    "EPSG:3008",
    "EPSG:3009",
    "EPSG:3010",
    "EPSG:3011",
    "EPSG:3012",
    "EPSG:3013",
    "EPSG:3014",
    "EPSG:3015",
    "EPSG:3016",
    "EPSG:3017",
    "EPSG:3018",
)

HOJDSYSTEM = (
    "EPSG:5613",
)

OSAKERT_LAGE = (
    "skymt läge vid inmätning",
    "lägesplacering i ungefärligt läge",
    "lägesplacering i illustrativt läge",
)

# Lägesbestämningsmetod -> tillåtna varianter (tom lista = ingen variant).
LAGESMETODER = {
    "geodetisk detaljmätning": (
        "avvägning",
        "barometerhöjdmätning",
        "DGNSS",
        "GNSS, absolut",
        "GNSS, enkelstations-RTK",
        "GNSS, nätverks-RTK",
        "GNSS, precise point positioning (PPP)",
        "GNSS, statistik",
        "inbindning och liknande planbestämningsmetoder",
        "okänd",
        "polär inmätning, totalstation, fri station GNSS",
        "polär inmätning, totalstation i stomnät",
        "polär inmätning, äldre utrustning",
        "trigonometrisk höjdmätning",
        "tröghetsteknik",
),
    "lägesplacering": (
        "3D-modell",
        "analog karta",
        "befintligt objekt i 3D-modell",
        "befintligt objekt i digital karta",
        "digital karta",
        "kartografiskt läge",
        "okänd",
        "ortofoto",
),
    "fotogrammetrisk detaljmätning": (
        "digital stereomodell, digitala bilder från drönare",
        "analogt ortofoto, analoga flygbilder",
        "digital stereomodell, digitala flygbilder",
        "digital stereomodell, skannade analoga flygbilder",
        "digitalt ortofoto, digitala bilder från drönare",
        "digitalt ortofoto, digitala flygbilder",
        "digitalt ortofoto, skannade analoga flygbilder",
        "digitalt sant ortofoto, digitala bilder från drönare",
        "digitalt sant ortofoto, digitala flygbilder",
        "okänd",
        "punktmoln, digitala bilder från drönare",
        "punktmoln, digitala flygbilder",
        "punktmoln, skannade analoga flygbilder",
        "skannat analogt ortofoto, analoga bilder",
        "stereomodell, analoga flygbilder",
),
    "vektorisering av analogt material": (
        "analog karta, bordsdigitalisering",
        "okänd",
        "skannad analog karta, automatisk tolkning",
        "skannad analog karta, skärmdigitalisering",
        "skannad ritning, automatisk tolkning",
        "skannad ritning, skärmdigitalisering",
),
    "detaljmätning i laserdata": (
        "drönarlaserskanning",
        "flygburen laserskanning",
        "fordonsburen laserskanning",
        "okänd",
        "terrester laserskanning",
),
    "konvertering": (
        "BIM-data till geodata, geodetiskt referenssystem",
        "BIM-data till geodata, kartesiskt koordinatsystem",
        "byggdata till geodata, okänd",
        "CAD-data till geodata, geodetiskt referenssystem",
        "CAD-data till geodata, kartesiskt koordinatsystem",
),
    "interpolering": (
        "höjder i höjdmodell, okänd",
        "höjder i markhöjdmodell, fotogrammetrisk detaljmätning",
        "höjder i markhöjdmodell, laserdata",
        "höjder i markhöjdmodell, laserdata och fotogrammetriskt punktmoln",
        "höjder i ythöjdmodell, fotogrammetriskt punktmoln",
        "höjder i ythöjdmodell, laserdata",
),
    "fjärranalys": (

),
    "batymetri": (

),
    "okänd": (
        "okänd",
),
}
