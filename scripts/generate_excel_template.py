from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName


OUT_PATH = Path(__file__).resolve().parents[1] / "assets" / "excel" / "analyst-template.xlsx"


def _add_named_range(wb: Workbook, name: str, ref: str) -> None:
    wb.defined_names.add(DefinedName(name, attr_text=ref))


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()

    dashboard = wb.active
    dashboard.title = "Dashboard"
    dashboard["A1"] = "Analyst Workbook Template"
    dashboard["A1"].font = Font(size=16, bold=True)
    dashboard["A2"] = "This workbook is hydrated by src.excel_export in template mode."
    dashboard.freeze_panes = "A3"

    for title in [
        "Portfolio Explorer",
        "By Lens",
        "By Collection",
        "Trend Summary",
        "Scenario Planner",
        "Executive Summary",
        "Print Pack",
    ]:
        ws = wb.create_sheet(title)
        ws["A1"] = title
        ws["A1"].font = Font(size=16, bold=True)
        ws.sheet_view.showGridLines = False

    info = wb.create_sheet("TemplateInfo")
    info.sheet_state = "hidden"
    info["A1"] = "Template Version"
    info["B1"] = "1"
    info["A2"] = "Workbook Mode"
    info["B2"] = "template"
    info["A3"] = "Generated At"
    info["B3"] = ""
    info["A4"] = "Portfolio Profile"
    info["B4"] = "default"
    info["A5"] = "Collection"
    info["B5"] = "all"
    fill = PatternFill("solid", fgColor="E2E8F0")
    for cell in ("A1", "A2", "A3", "A4", "A5"):
        info[cell].fill = fill
        info[cell].font = Font(bold=True)

    _add_named_range(wb, "tplTemplateVersion", "'TemplateInfo'!$B$1")
    _add_named_range(wb, "tplWorkbookMode", "'TemplateInfo'!$B$2")
    _add_named_range(wb, "tplGeneratedAt", "'TemplateInfo'!$B$3")
    _add_named_range(wb, "tplPortfolioProfile", "'TemplateInfo'!$B$4")
    _add_named_range(wb, "tplCollectionFilter", "'TemplateInfo'!$B$5")

    wb.save(OUT_PATH)
    print(OUT_PATH)


if __name__ == "__main__":
    main()
