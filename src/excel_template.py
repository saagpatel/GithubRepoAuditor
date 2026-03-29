from __future__ import annotations

import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
X14_NS = "http://schemas.microsoft.com/office/spreadsheetml/2009/9/main"
XM_NS = "http://schemas.microsoft.com/office/excel/2006/main"
SPARKLINE_URI = "{05C60535-1F16-4fd2-B633-F4F36F0B64E0}"
TREND_HISTORY_WINDOW = 12
DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "assets" / "excel" / "analyst-template.xlsx"
TEMPLATE_INFO_SHEET = "TemplateInfo"
TEMPLATE_SHEETS = [
    "Index",
    "Dashboard",
    "Portfolio Explorer",
    "By Lens",
    "By Collection",
    "Trend Summary",
    "Scenario Planner",
    "Review Queue",
    "Review History",
    "Campaigns",
    "Writeback Audit",
    "Governance Controls",
    "Governance Audit",
    "Executive Summary",
    "Print Pack",
    TEMPLATE_INFO_SHEET,
]

ET.register_namespace("", MAIN_NS)
ET.register_namespace("r", REL_NS)
ET.register_namespace("x14", X14_NS)
ET.register_namespace("xm", XM_NS)


@dataclass(frozen=True)
class SparklineSpec:
    sheet_name: str
    location: str
    data_range: str


def resolve_template_path(template_path: Path | None = None) -> Path:
    path = template_path or DEFAULT_TEMPLATE_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Excel template not found: {path}")
    return path


def copy_template_to_output(output_path: Path, template_path: Path | None = None) -> Path:
    source = resolve_template_path(template_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output_path)
    return output_path


def inject_native_sparklines(workbook_path: Path, specs: list[SparklineSpec]) -> None:
    if not specs:
        return

    specs_by_sheet: dict[str, list[SparklineSpec]] = {}
    for spec in specs:
        specs_by_sheet.setdefault(spec.sheet_name, []).append(spec)

    with zipfile.ZipFile(workbook_path) as source_zip:
        sheet_map = _map_sheet_paths(source_zip)
        updated_files: dict[str, bytes] = {}
        for sheet_name, sheet_specs in specs_by_sheet.items():
            sheet_path = sheet_map.get(sheet_name)
            if not sheet_path:
                continue
            updated_files[sheet_path] = _inject_sparklines_into_sheet_xml(
                source_zip.read(sheet_path),
                sheet_specs,
            )

        if not updated_files:
            return

        with NamedTemporaryFile(delete=False, suffix=".xlsx") as handle:
            temp_path = Path(handle.name)

        with zipfile.ZipFile(workbook_path) as source_zip, zipfile.ZipFile(temp_path, "w") as target_zip:
            for item in source_zip.infolist():
                data = updated_files.get(item.filename, source_zip.read(item.filename))
                target_zip.writestr(item, data)

    temp_path.replace(workbook_path)


def _map_sheet_paths(source_zip: zipfile.ZipFile) -> dict[str, str]:
    workbook_root = ET.fromstring(source_zip.read("xl/workbook.xml"))
    rel_root = ET.fromstring(source_zip.read("xl/_rels/workbook.xml.rels"))

    rel_map = {
        rel.attrib["Id"]: rel.attrib["Target"].lstrip("/")
        for rel in rel_root.findall(f"{{{PKG_REL_NS}}}Relationship")
    }

    sheet_map: dict[str, str] = {}
    sheets = workbook_root.find(f"{{{MAIN_NS}}}sheets")
    if sheets is None:
        return sheet_map

    for sheet in sheets.findall(f"{{{MAIN_NS}}}sheet"):
        name = sheet.attrib.get("name", "")
        rel_id = sheet.attrib.get(f"{{{REL_NS}}}id")
        target = rel_map.get(rel_id or "", "")
        if name and target:
            sheet_map[name] = f"xl/{target}" if not target.startswith("xl/") else target
    return sheet_map


def _inject_sparklines_into_sheet_xml(xml_bytes: bytes, specs: list[SparklineSpec]) -> bytes:
    root = ET.fromstring(xml_bytes)
    ext_lst = root.find(f"{{{MAIN_NS}}}extLst")
    if ext_lst is None:
        ext_lst = ET.SubElement(root, f"{{{MAIN_NS}}}extLst")

    for ext in list(ext_lst.findall(f"{{{MAIN_NS}}}ext")):
        if ext.attrib.get("uri") == SPARKLINE_URI:
            ext_lst.remove(ext)

    ext = ET.SubElement(ext_lst, f"{{{MAIN_NS}}}ext", {"uri": SPARKLINE_URI})
    spark_groups = ET.SubElement(ext, f"{{{X14_NS}}}sparklineGroups")
    spark_group = ET.SubElement(spark_groups, f"{{{X14_NS}}}sparklineGroup", {"displayEmptyCellsAs": "gap"})
    ET.SubElement(spark_group, f"{{{X14_NS}}}colorSeries", {"theme": "4", "tint": "-0.499984740745262"})
    ET.SubElement(spark_group, f"{{{X14_NS}}}colorNegative", {"theme": "5"})
    ET.SubElement(spark_group, f"{{{X14_NS}}}colorAxis", {"rgb": "FF000000"})
    ET.SubElement(spark_group, f"{{{X14_NS}}}colorMarkers", {"theme": "4", "tint": "-0.499984740745262"})
    ET.SubElement(spark_group, f"{{{X14_NS}}}colorFirst", {"theme": "4", "tint": "0.39997558519241921"})
    ET.SubElement(spark_group, f"{{{X14_NS}}}colorLast", {"theme": "4", "tint": "0.39997558519241921"})
    ET.SubElement(spark_group, f"{{{X14_NS}}}colorHigh", {"theme": "4"})
    ET.SubElement(spark_group, f"{{{X14_NS}}}colorLow", {"theme": "4"})

    sparklines = ET.SubElement(spark_group, f"{{{X14_NS}}}sparklines")
    for spec in specs:
        sparkline = ET.SubElement(sparklines, f"{{{X14_NS}}}sparkline")
        formula = ET.SubElement(sparkline, f"{{{XM_NS}}}f")
        formula.text = spec.data_range
        sqref = ET.SubElement(sparkline, f"{{{XM_NS}}}sqref")
        sqref.text = spec.location

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
