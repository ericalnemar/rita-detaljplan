"""Ett litet syntetiskt Word-dokument (.docx) för testerna: rubriker, en motivtabell, Words egna namnrymder och en
befintlig anpassad XML-del (bibliografi), så att taggningen provas mot det som riktiga dokument innehåller."""
import zipfile
from pathlib import Path

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
BODY = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W}" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" \
xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:Ignorable="w14"><w:body>
<w:p><w:pPr><w:pStyle w:val="Innehllsfrteckningsrubrik"/></w:pPr><w:r><w:t>Innehåll</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Rubrik1"/></w:pPr><w:bookmarkStart w:id="0" w:name="_Toc100"/><w:r><w:t>DETALJPLANENS SYFTE</w:t></w:r><w:bookmarkEnd w:id="0"/></w:p>
<w:p><w:pPr><w:pStyle w:val="Rubrik2"/></w:pPr><w:bookmarkStart w:id="1" w:name="_Toc101"/><w:r><w:t>Syfte</w:t></w:r><w:bookmarkEnd w:id="1"/></w:p>
<w:p><w:r><w:t>Detaljplanen syftar till att möjliggöra en badanläggning.</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Rubrik1"/></w:pPr><w:r><w:t>BESKRIVNING AV DETALJPLANEN</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Rubrik2"/></w:pPr><w:r><w:t>Hela detaljplanen</w:t></w:r></w:p>
<w:p><w:r><w:t>Planen omfattar </w:t></w:r><w:r><w:t>5 &amp; 6 hektar.</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Rubrik2"/></w:pPr><w:r><w:t>Allmän plats</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Rubrik3"/></w:pPr><w:r><w:t>Gator</w:t></w:r></w:p>
<w:p><w:r><w:t>Gatan är befintlig.</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Rubrik2"/></w:pPr><w:r><w:t>Genomförandetid</w:t></w:r></w:p>
<w:p><w:r><w:t>Genomförandetiden är tio år.</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Rubrik1"/></w:pPr><w:r><w:t>MOTIV TILL DETALJPLANENS REGLERINGAR</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Rubrik2"/></w:pPr><w:r><w:t>Motiv till regleringar</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Rubrik3"/></w:pPr><w:r><w:t>Användning av kvartersmark</w:t></w:r></w:p>
<w:tbl><w:tblPr/><w:tblGrid><w:gridCol/><w:gridCol/></w:tblGrid>
<w:tr><w:tc><w:p><w:r><w:t>R1</w:t></w:r><w:r><w:t>R1</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Badanläggning</w:t></w:r></w:p><w:p><w:r><w:t>Syftet är att möjliggöra bad.</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p/></w:tc><w:tc><w:p><w:r><w:t>Marken får inte förses med byggnad</w:t></w:r></w:p><w:p><w:r><w:t>Syftet är att behålla gatan fri.</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>z9</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Okänd bestämmelse</w:t></w:r></w:p><w:p><w:r><w:t>Motiv.</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p/></w:tc><w:tc><w:p/></w:tc></w:tr>
</w:tbl>
<w:p><w:pPr><w:pStyle w:val="Rubrik1"/></w:pPr><w:r><w:t>HEMLIG RUBRIK</w:t></w:r></w:p>
<w:p><w:r><w:t>Text under en rubrik som inte finns i BFS.</w:t></w:r></w:p>
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>
</w:body></w:document>"""

def para(text: str, style: str = "") -> str:
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{props}<w:r><w:t>{text}</w:t></w:r></w:p>"


def run(text: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r>'


def label_box(text: str) -> str:
    """En symbol med bestämmelsens beteckning, som Word skriver en textruta: en riktig ruta (``mc:Choice``) och en reservversion
    med samma text (``mc:Fallback``)."""
    inner = f"<w:txbxContent><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:txbxContent>"
    return ("<w:r><mc:AlternateContent><mc:Choice Requires=\"wps\"><w:drawing><wp:inline><wps:wsp><wps:txbx>"
            f"{inner}</wps:txbx></wps:wsp></wp:inline></w:drawing></mc:Choice><mc:Fallback><w:pict><v:shape><v:textbox>"
            f"{inner}</v:textbox></v:shape></w:pict></mc:Fallback></mc:AlternateContent></w:r>")


def raw_para(runs: str) -> str:
    return f"<w:p>{runs}</w:p>"


def wrap(content: str) -> str:
    """Ett dokument med bara ``content`` i brödtexten (samma namnrymder som ``BODY``)."""
    return (f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{W}" xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" \
xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" \
xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" \
xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" xmlns:v="urn:schemas-microsoft-com:vml" \
mc:Ignorable="w14"><w:body>{content}\
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>''')


STYLES = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="{W}">
<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Rubrik1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Rubrik2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:outlineLvl w:val="1"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Rubrik3"><w:name w:val="Rubrik 3"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Innehllsfrteckningsrubrik"><w:name w:val="TOC Heading"/><w:basedOn w:val="Rubrik1"/><w:pPr><w:outlineLvl w:val="9"/></w:pPr></w:style>
</w:styles>"""

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/customXml/itemProps1.xml" ContentType="application/vnd.openxmlformats-officedocument.customXmlProperties+xml"/></Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml" Target="../customXml/item1.xml"/><Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>"""

BIBLIOGRAPHY = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?><b:Sources xmlns:b="http://schemas.openxmlformats.org/'
                'officeDocument/2006/bibliography" SelectedStyle="\\APA.xsl" StyleName="APA" Version="6"></b:Sources>')
ITEM_PROPS = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n<ds:datastoreItem ds:itemID="{5C242326-5DF8-46C6-B49F-'
              'A8E510FC9052}" xmlns:ds="http://schemas.openxmlformats.org/officeDocument/2006/customXml"><ds:schemaRefs>'
              '<ds:schemaRef ds:uri="http://schemas.openxmlformats.org/officeDocument/2006/bibliography"/></ds:schemaRefs>'
              '</ds:datastoreItem>')
ITEM_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/'
             'package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
             'relationships/customXmlProps" Target="itemProps1.xml"/></Relationships>')


def make_docx(path: Path, body: str = BODY, extra: dict | None = None) -> Path:
    """``extra`` = ytterligare delar i paketet, {namn: text}."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in (extra or {}).items():
            z.writestr(name, data)
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("word/document.xml", body)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("customXml/item1.xml", BIBLIOGRAPHY)
        z.writestr("customXml/itemProps1.xml", ITEM_PROPS)
        z.writestr("customXml/_rels/item1.xml.rels", ITEM_RELS)
    return path


def running_text_body() -> str:
    """Motiv i löpande text, i tre former: rubrik som pekar ut bestämmelsen, ett kort stycke, och beteckning med motivet i samma stycke."""
    return wrap(
        para("MOTIV TILL DETALJPLANENS REGLERINGAR", "Rubrik1") + para("Motiv till regleringar", "Rubrik2")
        + para("Här motiveras bestämmelserna.")
        + para("R1 Badanläggning", "Rubrik3") + para("Syftet är att möjliggöra bad.")
        + para("Marken får inte förses med byggnad") + para("Syftet är att behålla gatan fri.") + para("Och dessutom.")
        + para("m1 Byggnaden ska utformas så att vatten kan passera. Bestämmelsen syftar till att skydda mot översvämning.")
        + para("Annat", "Rubrik3") + para("Text som inte hör till någon bestämmelse."))
