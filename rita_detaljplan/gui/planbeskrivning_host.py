"""Knappen Tagga planbeskrivning: öppnar programmet Tagga planbeskrivning (kopian i ``rita_detaljplan/planbeskrivning``)
med den aktiva planen förvald. Programmet läser planens bestämmelser och ytor direkt härifrån (även sådant som inte sparats
än) och kan lägga syftet och motiven ur planbeskrivningen på planen, i redigeringsbufferten, som när man skriver dem i
Planens uppgifter. Planen sparas sedan som vanligt."""
from __future__ import annotations

from ..controller import PLAN_LAYER, PlanController
from ..core import assignments, model, rows
from ..core import catalog as cat
from ..planbeskrivning.pbapp import session as ss
from ..planbeskrivning.pbkarna import geometri as geo
from ..planbeskrivning.pbkarna import plankarta as pk
from ..planbeskrivning.pbkarna.planbeskrivning_docx import Provision

AREA_TABLES = (cat.USE_LAYER, "egenskap_yta", "egenskap_linje")
_KIND_ORDER = {cat.USE_LAYER: 0, "egenskap_yta": 1, "egenskap_linje": 2}
SYFTE_MAX = next(f.length for f in model.layer_by_name(PLAN_LAYER).fields if f.name == "syfte")


def _wkb(feature) -> bytes:
    return bytes(feature.geometry().asWkb()) if feature.hasGeometry() else b""


class QgisHost(ss.Host):
    name = "QGIS"

    def __init__(self, controller: PlanController):
        self.controller = controller

    def load_plan(self):
        c = self.controller
        identity = c.plan_identity()
        if not identity:
            raise ss.SessionError("Planen har inget planområde än. Rita planområdet först.")
        values = c.plan_values()
        plan = pk.Plan(identity, values.get("namn") or "", values.get("beteckning") or "", None,
                       syfte=values.get("syfte") or "")
        details = {p["key"]: p for p in c.provisions()}
        for target in c.provision_targets():
            key = target["key"]
            plan.provisions.append(Provision(key, target["label"], target["text"], tuple(target["refs"]), target["technical"]))
            plan.kinds[key] = details.get(key, {}).get("kind") or ""
            if details.get(key, {}).get("motiv"):
                plan.motiv[key] = details[key]["motiv"]
        plan.provisions.sort(key=lambda p: (_KIND_ORDER.get(plan.kinds.get(p.key), 9), p.label.lower(), p.text.lower()))
        karta = geo.Karta()
        labels: dict = {}
        for row in assignments.read_rows(c.project):
            if row.get("yta") and row.get("objektidentitet"):
                plan.areas.setdefault(rows.identity(row), []).append(row["yta"])
                if row.get("tabell") == cat.USE_LAYER and row.get("beteckning"):
                    labels.setdefault(row["yta"], []).append(row["beteckning"])
        for table in AREA_TABLES:
            layer = c.layer(table)
            if layer is None:
                continue
            for feature in layer.getFeatures():
                ident = feature["objektidentitet"]
                shape = geo.parse_wkb(_wkb(feature))
                if shape is None or not ident:
                    continue
                karta.areas[ident] = shape
                karta.layer_of[ident] = table
                if ident in labels:
                    karta.labels[ident] = " ".join(labels[ident])
        feature = c.plan_feature()
        if feature is not None:
            karta.border = geo.parse_wkb(_wkb(feature))
        return plan, karta

    def write_back(self, purpose: str, motives: dict) -> str:
        c = self.controller
        current = {p["key"]: (p["motiv"] or "").strip() for p in c.provisions() if not p["technical"]}
        wanted = {key: text.strip() for key, text in motives.items() if key in current and text.strip()}
        changed = [key for key, text in wanted.items() if current[key] != text]
        purpose = " ".join((purpose or "").split())
        parts = []
        try:
            if purpose:
                kept = purpose[:SYFTE_MAX]
                if (c.plan_values().get("syfte") or "").strip() != kept:
                    c.set_plan_values({"syfte": kept})
                    parts.append("syftet")
            if changed:
                c.set_motives({key: wanted[key] for key in changed})
                parts.append(f"{len(changed)} motiv")
        except (RuntimeError, KeyError) as exc:
            raise ss.SessionError(f"Planen kunde inte ändras: {exc}") from exc
        if not parts:
            message = "Planen hade redan samma syfte och motiv som planbeskrivningen."
        else:
            message = " och ".join(parts).capitalize() + " lades på planen. Spara planen som vanligt."
        if len(purpose) > SYFTE_MAX:
            message += f" Syftet är {len(purpose)} tecken, mer än de {SYFTE_MAX} som specifikationen tillåter: det kortades."
        missing = [key for key in current if not (wanted.get(key) or current[key])]
        if missing:
            message += f" {len(missing)} bestämmelser saknar fortfarande motiv."
        return message


def open_window(controller: PlanController, parent=None):
    """Öppnar programmet (ett eget fönster, inte modalt) med den aktiva planen."""
    from ..planbeskrivning.pbapp.main import open_in_host
    return open_in_host(QgisHost(controller), parent)
