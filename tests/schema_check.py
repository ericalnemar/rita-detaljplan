"""Minimal JSON Schema-kontroll (draft-04, det som Lantmäteriets scheman använder) mot de riktiga schemafilerna i
spec/. Används i testerna för att visa att exporten följer detaljplan-4.1.json. Externa scheman (geojson-1.1) ersätts av
en egen kort version efter Lantmäteriets beskrivning, eftersom de inte finns lokalt."""
from __future__ import annotations

import json
import re
from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / "spec"

GEOJSON = {"definitions": {
    "position": {"type": "array", "minItems": 2, "items": {"type": "number"}},
    "ring": {"type": "array", "minItems": 4, "items": {"$ref": "#/definitions/position"}},
    "point": {"type": "object", "required": ["type", "coordinates"],
              "properties": {"type": {"enum": ["Point"]}, "coordinates": {"$ref": "#/definitions/position"}}},
    "linestring": {"type": "object", "required": ["type", "coordinates"],
                   "properties": {"type": {"enum": ["LineString"]},
                                  "coordinates": {"type": "array", "minItems": 2,
                                                  "items": {"$ref": "#/definitions/position"}}}},
    "polygon": {"type": "object", "required": ["type", "coordinates"],
                "properties": {"type": {"enum": ["Polygon"]},
                               "coordinates": {"type": "array", "minItems": 1, "items": {"$ref": "#/definitions/ring"}}}},
    "multipoint": {"type": "object", "required": ["type", "coordinates"], "properties": {"type": {"enum": ["MultiPoint"]}}},
    "multilinestring": {"type": "object", "required": ["type", "coordinates"],
                        "properties": {"type": {"enum": ["MultiLineString"]}}},
    "multipolygon": {"type": "object", "required": ["type", "coordinates"],
                     "properties": {"type": {"enum": ["MultiPolygon"]}}},
    "geometrycollection": {"type": "object", "required": ["type", "geometries"],
                           "properties": {"type": {"enum": ["GeometryCollection"]}}},
    "feature": {"type": "object", "required": ["type", "properties", "geometry"],
                "properties": {"type": {"enum": ["Feature"]}}},
    "featurecollection": {"type": "object", "required": ["type", "features"],
                          "properties": {"type": {"enum": ["FeatureCollection"]}, "features": {"type": "array"}}},
}}

DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _load(name: str) -> dict:
    return json.loads((SPEC / name).read_text(encoding="utf-8"))


class Checker:
    def __init__(self):
        self.docs = {"detaljplan": _load("detaljplan-4.1.json"), "geometri": _load("geometri-2.0.json"),
                     "geometrimetadata": _load("geometrimetadata-2.0.1.json"), "geojson": GEOJSON}

    def problems(self, instance) -> list[str]:
        root = self.docs["detaljplan"]
        errors: list[str] = []
        self._check(instance, root, "detaljplan", "$", errors)
        return errors

    # -- uppslagning ---------------------------------------------------------------------
    def _resolve(self, ref: str, doc: str):
        if ref.startswith("#"):
            target, fragment = doc, ref[1:]
        else:
            url, _, fragment = ref.partition("#")
            name = url.rsplit("/", 1)[-1]
            target = next(key for key in sorted(self.docs, key=len, reverse=True) if name.startswith(key))
        node = self.docs[target]
        for part in [p for p in fragment.split("/") if p]:
            node = node[part]
        return node, target

    # -- kontroll --------------------------------------------------------------------------
    def _check(self, value, schema: dict, doc: str, path: str, errors: list[str]) -> None:
        if "$ref" in schema:
            node, target = self._resolve(schema["$ref"], doc)
            self._check(value, node, target, path, errors)
        for sub in schema.get("allOf", []):
            self._check(value, sub, doc, path, errors)
        if "oneOf" in schema:
            matches = 0
            for sub in schema["oneOf"]:
                trial: list[str] = []
                self._check(value, sub, doc, path, trial)
                matches += not trial
            if matches != 1:
                errors.append(f"{path}: matchar {matches} av {len(schema['oneOf'])} alternativ (ska vara exakt 1)")
                if matches == 0:  # visa varför det närmaste alternativet inte passar
                    trials = []
                    for sub in schema["oneOf"]:
                        trial: list[str] = []
                        self._check(value, sub, doc, path, trial)
                        trials.append(trial)
                    errors.extend("    " + e for e in min(trials, key=len)[:6])
        if "enum" in schema and value not in schema["enum"]:
            errors.append(f"{path}: {value!r} finns inte i {schema['enum']}")
        kind = schema.get("type")
        if kind is not None and not self._is(value, kind):
            errors.append(f"{path}: ska vara {kind}, är {type(value).__name__}")
            return
        if isinstance(value, str):
            if "pattern" in schema and not re.search(schema["pattern"], value):
                errors.append(f"{path}: {value!r} följer inte mönstret {schema['pattern']}")
            if schema.get("format") == "date" and not DATE.match(value):
                errors.append(f"{path}: {value!r} är inget datum")
            if schema.get("format") == "date-time" and not DATE_TIME.match(value):
                errors.append(f"{path}: {value!r} är ingen tidpunkt")
        if isinstance(value, dict):
            for name in schema.get("required", []):
                if name not in value:
                    errors.append(f"{path}: {name} saknas")
            properties = schema.get("properties", {})
            for name, item in value.items():
                if name in properties:
                    self._check(item, properties[name], doc, f"{path}.{name}", errors)
                elif schema.get("additionalProperties") is False:
                    errors.append(f"{path}: {name} är inte tillåtet här")
        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append(f"{path}: minst {schema['minItems']} poster krävs (finns {len(value)})")
            if "items" in schema:
                for index, item in enumerate(value):
                    self._check(item, schema["items"], doc, f"{path}[{index}]", errors)

    @staticmethod
    def _is(value, kind: str) -> bool:
        if kind == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if kind == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if kind == "boolean":
            return isinstance(value, bool)
        return isinstance(value, TYPES[kind])
