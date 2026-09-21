"""Pluginets inställningar (sparas i QGIS användarprofil)."""
from __future__ import annotations

import re
from typing import Optional

from qgis.core import QgsApplication, QgsSettings

# Obs: nycklarna nedan behåller det gamla prefixet ``detaljplan_ngp`` (pluginet hette förr Detaljplan NGP) så att redan
# skapade projekt och sparade inställningar fortsätter fungera efter namnbytet.
KEY_REFERENCE_SCALE = "detaljplan_ngp/reference_scale"
DEFAULT_REFERENCE_SCALE = 1000
SCALES = (200, 500, 1000, 2000, 4000, 5000, 10000)  # förslag i inställningsdialogen
MIN_SCALE, MAX_SCALE = 100, 50000


KEY_NGP = "detaljplan_ngp/ngp/"


def ngp_config():
    """Inställningarna för leverans till NGP (miljö, adresser, autentiseringskonfiguration)."""
    from . import ngp_client as ngp
    store = QgsSettings()
    environment = str(store.value(KEY_NGP + "environment", "ver"))
    defaults = ngp.ENVIRONMENTS.get(environment)
    if defaults is None:
        environment = "egen"
    base = str(store.value(KEY_NGP + "base_url", defaults.base_url if defaults else "") or "")
    token = str(store.value(KEY_NGP + "token_url", defaults.token_url if defaults else "") or "")
    return ngp.NgpConfig(environment=environment, base_url=base, token_url=token,
                         authcfg=str(store.value(KEY_NGP + "authcfg", "") or ""))


def set_ngp_config(config) -> None:
    store = QgsSettings()
    store.setValue(KEY_NGP + "environment", config.environment)
    store.setValue(KEY_NGP + "base_url", config.base_url.strip())
    store.setValue(KEY_NGP + "token_url", config.token_url.strip())
    store.setValue(KEY_NGP + "authcfg", config.authcfg)


def auth_configs() -> list[tuple[str, str]]:
    """QGIS autentiseringskonfigurationer som (id, namn). Tom lista om autentiseringsdatabasen inte kan läsas."""
    try:
        configs = QgsApplication.authManager().availableAuthMethodConfigs()
        return sorted(((cid, cfg.name()) for cid, cfg in configs.items()), key=lambda item: item[1].lower())
    except Exception:  # noqa: BLE001 - t.ex. låst databas eller saknad huvudlösenordsfråga
        return []


def scale_text(scale: int) -> str:
    return f"1:{scale}"


def parse_scale(text: str) -> Optional[int]:
    """Läser "1:1000" eller "1000" som 1000. None om texten inte är en skala."""
    match = re.fullmatch(r"\s*(?:1\s*:\s*)?(\d{2,6})\s*", text or "")
    return int(match.group(1)) if match else None


def clamp_scale(value) -> int:
    try:
        scale = int(round(float(value)))
    except (TypeError, ValueError):
        return DEFAULT_REFERENCE_SCALE
    return max(MIN_SCALE, min(MAX_SCALE, scale))


def reference_scale() -> int:
    """Referensskalan (nämnaren, 1000 = 1:1000) som linjer och texter dimensioneras för."""
    return clamp_scale(QgsSettings().value(KEY_REFERENCE_SCALE, DEFAULT_REFERENCE_SCALE))


def set_reference_scale(value) -> int:
    scale = clamp_scale(value)
    QgsSettings().setValue(KEY_REFERENCE_SCALE, scale)
    return scale
