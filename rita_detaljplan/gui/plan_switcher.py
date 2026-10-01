"""En rad som visar och låter en byta aktiv plan (se ``core.project.plan_groups``/``activate_plan_group``), för
dialoger som annars inte visar vilken av flera laddade planer de gäller. Syns bara om fler än en plan är laddad –
annars är det underförstått vilken det gäller."""
from __future__ import annotations

from typing import Callable, Optional

from qgis.PyQt.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from ..controller import PlanController
from ..core.project import activate_plan_group, find_plan_group, plan_groups


def build_plan_switcher(controller: PlanController, on_switch: Callable[[], None], parent=None) -> Optional[QWidget]:
    """Bygger raden ("Aktiv plan: [lista]"), eller returnerar None om det bara finns en (eller ingen) laddad plan.
    Väljer man en annan plan görs den aktiv (``activate_plan_group`` + ``controller.attach()``) och ``on_switch``
    anropas – det är upp till den som bygger dialogen att läsa om innehållet (eller stänga och öppna den igen) för
    den nya planen, se t.ex. ``TopologyDialog.reload``/``ValidationDialog.reload`` eller ``PlanInfoDialog``."""
    groups = plan_groups(controller.project)
    if len(groups) <= 1:
        return None
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 10)
    layout.addWidget(QLabel("Aktiv plan:"))
    combo = QComboBox()
    for group in groups:
        combo.addItem(group.name(), group)
    combo.setCurrentIndex(combo.findData(find_plan_group(controller.project)))

    def _changed(index: int) -> None:
        group = combo.itemData(index)
        if group is find_plan_group(controller.project):  # läses om varje gång: kan ha ändrats sedan raden byggdes
            return
        activate_plan_group(controller.project, group)
        controller.attach()
        on_switch()

    combo.currentIndexChanged.connect(_changed)
    layout.addWidget(combo)
    layout.addStretch(1)
    return row
