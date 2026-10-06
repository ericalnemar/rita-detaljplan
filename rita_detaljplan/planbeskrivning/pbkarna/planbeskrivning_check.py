"""Kontroll av en planbeskrivning mot Boverkets föreskrifter BFS 2020:8, innan den taggas: vad som blir otaggat, vilka
bestämmelser som saknar motiv och vilket obligatoriskt innehåll som inte hittas.

Kontrollen bygger på samma analys som taggningen (``planbeskrivning_docx.Analys``), så den visar det som faktiskt händer
när en taggad kopia skapas. Det är ingen bedömning av om innehållet är bra eller tillräckligt: bara om det som föreskriften
kräver går att hitta, och om det blir taggat. Villkorliga krav (t.ex. huvudmannaskap, om det finns allmän plats) kontrolleras
inte. Ren Python, ingen QGIS behövs."""
from __future__ import annotations

from dataclasses import dataclass

from . import planbeskrivning as pb
from . import planbeskrivning_docx as dx

FEL, VARNING, INFO = "fel", "varning", "info"
ORDNING = {FEL: 0, VARNING: 1, INFO: 2}
SYMBOL = {FEL: "✘", VARNING: "▲", INFO: "ℹ"}

# BFS 2020:8 2 kap.: (tema, grupp eller None = vilken grupp som helst, text, krav, allvarlighet)
KRAV = (
    ("Detaljplanens syfte", "Syfte", "Detaljplanens syfte saknas.", "2 kap. 1 §", FEL),
    ("Beskrivning av detaljplanen", "Hela detaljplan", "Detaljplanens omfattning och lokalisering saknas.",
     "2 kap. 2 § p. 2", FEL),
    ("Beskrivning av detaljplanen", "Genomförandetid", "Genomförandetiden saknas.", "2 kap. 2 § p. 3", FEL),
    ("Planeringsunderlag", None, "Sammanställningen av planeringsunderlag saknas.", "2 kap. 13 §", FEL),
    ("Beskrivning av detaljplanen", "Ärendeinformation",
     "Ärendeinformationen saknas (information enligt 2 kap. 3 § första stycket BFS 2020:5).", "2 kap. 14 §", VARNING),
    ("Genomförandefrågor", None, "Genomförandefrågor saknas. Ekonomisk bedömning och ansvar för utbyggnad och drift av "
     "allmän plats ska alltid redovisas.", "2 kap. 8–9 §§", VARNING),
    ("Genomförandefrågor", "Ekonomiska frågor", "Den ekonomiska bedömningen av genomförandet saknas.", "2 kap. 9 §",
     VARNING),
)


@dataclass(frozen=True)
class Fynd:
    """Ett resultat av kontrollen."""
    allvarlighet: str
    text: str
    var: str = ""  # rubrik eller bestämmelse som det gäller
    krav: str = ""  # vilken bestämmelse i BFS 2020:8 det rör

    @property
    def symbol(self) -> str:
        return SYMBOL[self.allvarlighet]


def _name(provision: dx.Provision) -> str:
    return f"{provision.label} {provision.text}".strip()


def check(analysis: dx.Analys) -> list[Fynd]:
    """Alla fynd, med de allvarligaste först."""
    found: list[Fynd] = []
    sections = analysis.sections
    tagged = [s for s in sections if s.taggas]
    if not sections:
        return [Fynd(FEL, "Dokumentet har inga rubriker (Rubrik 1, 2, 3): ingenting kan taggas.", "", "3 kap. 2 §")]

    # 1. text som inte blir taggad
    for section in sections:
        if not section.has_content or section.indelning.tema == pb.MOTIV_TEMA or section.taggas:
            continue
        where = " › ".join(section.path)
        if section.indelning.tema is None:
            found.append(Fynd(FEL, f"Texten taggas inte: rubriken \"{section.path[0]}\" känns inte igen som ett tema i "
                                   "BFS 2020:8. Välj tema i listan.", where, "3 kap. 2 §"))
        else:
            found.append(Fynd(FEL, "Texten taggas inte: den ligger direkt under temarubriken och saknar grupp. Välj "
                                   "grupp för den i listan, eller lägg den under en underrubrik i dokumentet.", where,
                              "3 kap. 2 §"))
    if analysis.front:
        found.append(Fynd(INFO, f"Text före första rubriken ({analysis.front} avsnitt, t.ex. försättsblad) taggas inte.",
                          "", "3 kap. 2 §"))

    # 2. motiv till reglering
    motive_keys = {m.key for m in analysis.motives if m.key is not None}
    needed = [p for p in analysis.provisions if p.refs and not p.technical]
    if needed:
        if not motive_keys:
            found.append(Fynd(FEL, f"Inga motiv hittades i dokumentet, men planen har {len(needed)} bestämmelser. Motiv "
                                   "till de enskilda regleringarna ska redovisas och kopplas till bestämmelsen.", "",
                              "2 kap. 3 §, 3 kap. 4 §"))
        else:
            for provision in needed:
                if provision.key not in motive_keys:
                    found.append(Fynd(FEL, "Bestämmelsen saknar motiv i planbeskrivningen.", _name(provision),
                                      "2 kap. 3 §, 3 kap. 4 §"))
    for motive in analysis.motives:
        name = motive.label or motive.title[:60]
        if motive.key is None:
            found.append(Fynd(VARNING, "Motivraden hittar ingen bestämmelse i planen (finns bestämmelsen kvar? stavning?).",
                              f"{name} ({' › '.join(motive.path[-1:])})", "3 kap. 4 §"))
        elif not motive.motiv.strip():
            found.append(Fynd(VARNING, "Motivet saknar text: bara bestämmelsen står där.", name, "2 kap. 3 §"))
    for section in analysis.uncovered:
        found.append(Fynd(VARNING, "Avsnittet handlar om motiv, men ingen bestämmelse kunde kopplas till texten: den "
                                   "taggas inte.", " › ".join(section.path), "3 kap. 4 §"))

    # 3. obligatoriskt innehåll
    present = {(s.indelning.tema, s.indelning.grupp) for s in tagged}
    themes = {tema for tema, _ in present}
    for tema, grupp, text, krav, severity in KRAV:
        if (grupp is None and tema not in themes) or (grupp is not None and (tema, grupp) not in present):
            if tema == "Genomförandefrågor" and grupp == "Ekonomiska frågor" and tema not in themes:
                continue  # redan sagt via temat
            found.append(Fynd(severity, text, tema + (f" › {grupp}" if grupp else ""), f"BFS 2020:8 {krav}"))
    if not themes & {"Planeringsförutsättningar", "Konsekvenser"}:
        found.append(Fynd(VARNING, "Hur kommunen hanterat och avvägt olika intressen enligt 2 kap. PBL ska redovisas, men "
                                   "varken Planeringsförutsättningar eller Konsekvenser hittades.", "",
                          "BFS 2020:8 2 kap. 2 § p. 4"))

    total = sum(1 for s in sections if s.has_content and s.indelning.tema != pb.MOTIV_TEMA)
    found.append(Fynd(INFO, f"{len(tagged)} av {total} avsnitt med text under tema utanför motiven blir taggade; "
                            f"{len(analysis.motives)} motiv hittades.", "", ""))
    found.sort(key=lambda f: ORDNING[f.allvarlighet])
    return found


def counts(found: list[Fynd]) -> tuple[int, int]:
    """(antal fel, antal varningar)."""
    return (sum(1 for f in found if f.allvarlighet == FEL), sum(1 for f in found if f.allvarlighet == VARNING))
