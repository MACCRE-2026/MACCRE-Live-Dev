# ┌─────────────────────────────────────────────────────────────────────────────┐
# │  MACCREv2 ENGINEERING DOCTRINE                             Law Rev: 19.0   │
# ├─────────────────────────────────────────────────────────────────────────────┤
# │  I.   TYPING      All signatures: explicit Python 3.11+ type hints.        │
# │  II.  LINTING     Zero unused imports. No wildcards. 120-char line max.    │
# │  III. PATHS       Never hardcode absolute paths. Use get_maccre_root().     │
# │                   Default params: def f(p:str='') -> None: p=p or root/x   │
# │  IV.  DATACENTER  5-Tier: 01_Raw_Source · 02_Dynamic_Context               │
# │                           03_Agent_Ledgers · 04_Code_Artifacts             │
# │                           05_Rendered_Media                                 │
# │  V.   DIAMOND     Gen: temp=1.0  ·  Critic: temp=0.1 + dataclass schema   │
# │  VI.  ABSTRACTION All I/O behind abc.ABC before any concrete driver.       │
# │  VII. TEARDOWN    try/finally on all handles (omni clean compliance).      │
# │  VIII.TELEMETRY   No bare print(). logger only. JSON → 03_Agent_Ledgers.  │
# └─────────────────────────────────────────────────────────────────────────────┘
"""
maccre_core/_net/ooxml.py
==========================
Sovereign OOXML Workbook Writer — zero external dependencies.

Replicates the openpyxl write-path API surface used across all MACCREv2 scripts:
  - Workbook, Worksheet
  - Cell (value, font, fill, alignment, border)
  - Font, PatternFill, Alignment, Border, Side
  - merge_cells, column_dimensions, row_dimensions
  - get_column_letter

Architecture:
  xlsx is a ZIP archive containing XML files (OOXML spec / ECMA-376).
  This writer uses only stdlib: zipfile + xml.etree.ElementTree + io.

Status:   WRITE-ONLY (Phase 1D target).
Roadmap:  Read path stays on vendored openpyxl until a native reader is built.
"""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ── Column Letter Helper ────────────────────────────────────────────────────────

def get_column_letter(col_idx: int) -> str:
    """Convert 1-based column index to Excel letter(s). e.g., 1→'A', 27→'AA'."""
    if col_idx < 1:
        msg = f"Column index must be >= 1, got {col_idx}"
        raise ValueError(msg)
    result = ""
    while col_idx:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _col_letter_to_idx(col: str) -> int:
    """Convert Excel column letters to 1-based index. e.g., 'A'→1, 'AA'→27."""
    result = 0
    for ch in col.upper():
        result = result * 26 + (ord(ch) - 64)
    return result


def _cell_ref(row: int, col: int) -> str:
    return f"{get_column_letter(col)}{row}"


# ── Style Primitives ────────────────────────────────────────────────────────────

@dataclass
class Font:
    name: str = "Calibri"
    bold: bool = False
    italic: bool = False
    size: int | float = 11
    color: str = "000000"

    def xml_key(self) -> tuple[Any, ...]:
        return (self.name, self.bold, self.italic, self.size, self.color)


@dataclass
class PatternFill:
    patternType: str = "solid"  # noqa: N815 — openpyxl API compat
    fgColor: str = "FFFFFF"     # noqa: N815 — openpyxl API compat

    def xml_key(self) -> tuple[Any, ...]:
        return (self.patternType, self.fgColor)


@dataclass
class Alignment:
    horizontal: str = "general"
    vertical: str = "bottom"
    wrap_text: bool = False

    def xml_key(self) -> tuple[Any, ...]:
        return (self.horizontal, self.vertical, self.wrap_text)


@dataclass
class Side:
    style: str = "thin"
    color: str = "000000"

    def xml_key(self) -> tuple[Any, ...]:
        return (self.style, self.color)


@dataclass
class Border:
    left: Side | None = None
    right: Side | None = None
    top: Side | None = None
    bottom: Side | None = None

    def xml_key(self) -> tuple[Any, ...]:
        def _sk(s: Side | None) -> tuple[Any, ...]:
            return s.xml_key() if s else ()
        return (_sk(self.left), _sk(self.right), _sk(self.top), _sk(self.bottom))


# ── Cell ────────────────────────────────────────────────────────────────────────

@dataclass
class Cell:
    row: int = 0
    col: int = 0
    value: Any = None
    font: Font | None = None
    fill: PatternFill | None = None
    alignment: Alignment | None = None
    border: Border | None = None
    _number_format: str = "General"

    # Pyright compatibility: openpyxl exposes these as settable attrs
    @property
    def number_format(self) -> str:
        return self._number_format

    @number_format.setter
    def number_format(self, fmt: str) -> None:
        self._number_format = fmt


# ── Dimension Helpers (mimic openpyxl attribute objects) ───────────────────────

@dataclass
class ColumnDimension:
    width: float = 8.0
    hidden: bool = False


@dataclass
class RowDimension:
    height: float | None = None
    hidden: bool = False


# ── Data Validation (Dropdowns) ────────────────────────────────────────────────

@dataclass
class DataValidation:
    """Represents an Excel dropdown or list validation on a cell range.

    Two formula1 modes:
      Inline list  — '"Option A,Option B,Option C"'  (255 char max)
      Range ref    — "'SheetName'!$A$2:$A$60"         (for long dynamic lists)
    """
    sqref: str                    # target: "B3" or "B3:B200"
    formula1: str                 # inline or range-reference formula
    show_dropdown: bool = True
    show_error: bool    = True
    error_title: str    = "Invalid Selection"
    error_msg: str      = "Choose a value from the dropdown list."


# ── Style Registry (deduplication for the styles.xml file) ─────────────────────

# Alias types
XfKey = tuple[int, int, int, str, str, bool]


class StyleRegistry:
    """Collects unique fonts, fills, borders and assigns integer IDs for styles.xml."""

    def __init__(self) -> None:
        self.fonts: list[Font] = [Font()]              # index 0 = default
        self.fills: list[PatternFill] = [              # 0,1 required by OOXML spec
            PatternFill("none", "FFFFFF"),
            PatternFill("gray125", "FFFFFF"),
        ]
        self.borders: list[Border] = [Border()]        # index 0 = no border
        self._font_idx: dict[tuple[Any, ...], int] = {}
        self._fill_idx: dict[tuple[Any, ...], int] = {}
        self._border_idx: dict[tuple[Any, ...], int] = {}

    def get_font_id(self, font: Font | None) -> int:
        if font is None:
            return 0
        key = font.xml_key()
        if key not in self._font_idx:
            idx = len(self.fonts)
            self.fonts.append(font)
            self._font_idx[key] = idx
        return self._font_idx[key]

    def get_fill_id(self, fill: PatternFill | None) -> int:
        if fill is None:
            return 0
        key = fill.xml_key()
        if key not in self._fill_idx:
            idx = len(self.fills)
            self.fills.append(fill)
            self._fill_idx[key] = idx
        return self._fill_idx[key]

    def get_border_id(self, border: Border | None) -> int:
        if border is None:
            return 0
        key = border.xml_key()
        if key not in self._border_idx:
            idx = len(self.borders)
            self.borders.append(border)
            self._border_idx[key] = idx
        return self._border_idx[key]


# ── Worksheet ───────────────────────────────────────────────────────────────────

class Worksheet:
    def __init__(self, title: str) -> None:
        self.title: str = title
        self.cells: dict[tuple[int, int], Cell] = {}
        self.merges: list[str] = []            # e.g. "A1:D1"
        # Auto-create entries on first access — mirrors openpyxl API exactly.
        self.column_dimensions: defaultdict[str, ColumnDimension] = defaultdict(ColumnDimension)
        self.row_dimensions: defaultdict[int, RowDimension] = defaultdict(RowDimension)
        self.data_validations: list[DataValidation] = []

    def add_validation(self, sqref: str, formula1: str, **kwargs: bool | str) -> DataValidation:
        """Add a dropdown/list validation to a cell or range and return it."""
        dv = DataValidation(sqref=sqref, formula1=formula1, **kwargs)  # type: ignore[arg-type]
        self.data_validations.append(dv)
        return dv

    # ── Cell access ─────────────────────────────────────────────────────────

    def cell(self, row: int, column: int, value: Any = None) -> Cell:
        key = (row, column)
        if key not in self.cells:
            self.cells[key] = Cell(row=row, col=column)
        c = self.cells[key]
        if value is not None:
            c.value = value
        return c

    def __getitem__(self, ref: str) -> Cell:
        """Support ws['A1'] style access."""
        m = re.match(r"([A-Za-z]+)(\d+)$", ref)
        if not m:
            msg = f"Invalid cell reference: {ref}"
            raise ValueError(msg)
        col = _col_letter_to_idx(m.group(1))
        row = int(m.group(2))
        return self.cell(row=row, column=col)

    # ── Merging ─────────────────────────────────────────────────────────────

    def merge_cells(self, range_str: str) -> None:
        self.merges.append(range_str)

    # ── XML serialization ───────────────────────────────────────────────────

    def to_xml(self, registry: StyleRegistry) -> str:
        """Render this worksheet to its sheet XML string.

        OOXML CT_Worksheet strict element order:
          cols → sheetData → mergeCells → dataValidations
        """
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        ET.register_namespace("", ns)
        root = ET.Element(f"{{{ns}}}worksheet")

        # Determine sheet bounds
        if self.cells:
            max_row = max(r for r, _ in self.cells)
            max_col = max(c for _, c in self.cells)
        else:
            max_row, max_col = 1, 1

        # ── 1. cols (MUST come before sheetData per OOXML spec) ──────────────
        col_dims = {k: v for k, v in self.column_dimensions.items()}
        if col_dims:
            cols_el = ET.SubElement(root, f"{{{ns}}}cols")
            for col_letter, cd in sorted(col_dims.items(),
                                         key=lambda kv: _col_letter_to_idx(kv[0])):
                c_idx = _col_letter_to_idx(col_letter)
                col_el = ET.SubElement(cols_el, f"{{{ns}}}col")
                col_el.set("min", str(c_idx))
                col_el.set("max", str(c_idx))
                col_el.set("width", str(cd.width))
                col_el.set("customWidth", "1")

        # ── 2. sheetData ─────────────────────────────────────────────────────
        sheet_data = ET.SubElement(root, f"{{{ns}}}sheetData")
        for row_idx in range(1, max_row + 1):
            row_el = ET.SubElement(sheet_data, f"{{{ns}}}row")
            row_el.set("r", str(row_idx))
            # Row dimension (height)
            rd = self.row_dimensions.get(row_idx)
            if rd is not None and rd.height is not None:
                row_el.set("ht", str(rd.height))
                row_el.set("customHeight", "1")

            for col_idx in range(1, max_col + 1):
                key = (row_idx, col_idx)
                if key not in self.cells:
                    continue
                c = self.cells[key]
                if c.value is None:
                    continue

                font_id   = registry.get_font_id(c.font)
                fill_id   = registry.get_fill_id(c.fill)
                border_id = registry.get_border_id(c.border)

                c_el = ET.SubElement(row_el, f"{{{ns}}}c")
                c_el.set("r", _cell_ref(row_idx, col_idx))

                val_str = str(c.value) if c.value is not None else ""
                if isinstance(c.value, bool):
                    c_el.set("t", "b")
                    ET.SubElement(c_el, f"{{{ns}}}v").text = "1" if c.value else "0"
                elif isinstance(c.value, (int, float)):
                    ET.SubElement(c_el, f"{{{ns}}}v").text = val_str
                else:
                    # Inline string — avoids shared strings table complexity
                    c_el.set("t", "inlineStr")
                    is_el = ET.SubElement(c_el, f"{{{ns}}}is")
                    ET.SubElement(is_el, f"{{{ns}}}t").text = val_str

                # Tag with style markers — resolved to xf index in _write_sheet
                c_el.set("_font", str(font_id))
                c_el.set("_fill", str(fill_id))
                c_el.set("_border", str(border_id))
                if c.alignment:
                    c_el.set("_halign", c.alignment.horizontal)
                    c_el.set("_valign", c.alignment.vertical)
                    c_el.set("_wrap", "1" if c.alignment.wrap_text else "0")

        # ── 3. mergeCells ────────────────────────────────────────────────────
        if self.merges:
            merge_cells_el = ET.SubElement(root, f"{{{ns}}}mergeCells")
            for m in self.merges:
                mc = ET.SubElement(merge_cells_el, f"{{{ns}}}mergeCell")
                mc.set("ref", m)

        # ── 4. dataValidations (dropdowns) ───────────────────────────────────
        if self.data_validations:
            dvs_el = ET.SubElement(root, f"{{{ns}}}dataValidations")
            dvs_el.set("count", str(len(self.data_validations)))
            for dv in self.data_validations:
                dv_el = ET.SubElement(dvs_el, f"{{{ns}}}dataValidation")
                dv_el.set("type", "list")
                dv_el.set("sqref", dv.sqref)
                dv_el.set("showDropDown", "0" if dv.show_dropdown else "1")
                if dv.show_error:
                    dv_el.set("showErrorMessage", "1")
                    dv_el.set("errorTitle", dv.error_title)
                    dv_el.set("error", dv.error_msg)
                ET.SubElement(dv_el, f"{{{ns}}}formula1").text = dv.formula1

        return ET.tostring(root, encoding="unicode", xml_declaration=False)



# ── Workbook ────────────────────────────────────────────────────────────────────

class Workbook:
    def __init__(self) -> None:
        self._sheets: list[Worksheet] = []
        self._registry = StyleRegistry()
        self._xf_map: dict[XfKey, int] = {}

    @property
    def sheetnames(self) -> list[str]:
        return [ws.title for ws in self._sheets]

    def create_sheet(self, title: str) -> Worksheet:
        ws = Worksheet(title)
        self._sheets.append(ws)
        return ws

    def __delitem__(self, title: str) -> None:
        self._sheets = [ws for ws in self._sheets if ws.title != title]

    def __contains__(self, title: str) -> bool:
        return any(ws.title == title for ws in self._sheets)

    # ── OOXML ZIP Assembly ──────────────────────────────────────────────────

    def save(self, filepath: str) -> None:
        """Write the workbook to filepath as a valid .xlsx ZIP archive."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            self._write_content_types(zf)
            self._write_rels(zf)
            self._write_workbook_xml(zf)
            self._write_workbook_rels(zf)
            self._write_styles(zf)
            self._write_shared_strings(zf)
            for idx, ws in enumerate(self._sheets, start=1):
                self._write_sheet(zf, ws, idx)
        buf.seek(0)
        Path(filepath).write_bytes(buf.read())

    # ── Internal XML writers ────────────────────────────────────────────────

    def _write_content_types(self, zf: zipfile.ZipFile) -> None:
        ns = "http://schemas.openxmlformats.org/package/2006/content-types"
        root = ET.Element(f"{{{ns}}}Types")
        ET.register_namespace("", ns)

        def _default(ext: str, ct: str) -> None:
            el = ET.SubElement(root, f"{{{ns}}}Default")
            el.set("Extension", ext)
            el.set("ContentType", ct)

        def _override(part: str, ct: str) -> None:
            el = ET.SubElement(root, f"{{{ns}}}Override")
            el.set("PartName", part)
            el.set("ContentType", ct)

        _default("rels", "application/vnd.openxmlformats-package.relationships+xml")
        _default("xml", "application/xml")
        _override("/xl/workbook.xml",
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml")
        _override("/xl/styles.xml",
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml")
        _override("/xl/sharedStrings.xml",
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml")
        for idx in range(1, len(self._sheets) + 1):
            _override(f"/xl/worksheets/sheet{idx}.xml",
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")

        zf.writestr("[Content_Types].xml", ET.tostring(root, encoding="unicode"))

    def _write_rels(self, zf: zipfile.ZipFile) -> None:
        ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        ET.register_namespace("", ns)
        root = ET.Element(f"{{{ns}}}Relationships")
        rel = ET.SubElement(root, f"{{{ns}}}Relationship")
        rel.set("Id", "rId1")
        rel.set("Type",
                "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument")
        rel.set("Target", "xl/workbook.xml")
        zf.writestr("_rels/.rels", ET.tostring(root, encoding="unicode"))

    def _write_workbook_xml(self, zf: zipfile.ZipFile) -> None:
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        ET.register_namespace("", ns)
        ET.register_namespace("r", rns)
        root = ET.Element(f"{{{ns}}}workbook")
        # NOTE: do NOT call root.set("xmlns:r", rns) — ET.register_namespace already
        # emits xmlns:r during serialization; a manual set would create a duplicate attribute.
        sheets_el = ET.SubElement(root, f"{{{ns}}}sheets")
        for idx, ws in enumerate(self._sheets, start=1):
            s = ET.SubElement(sheets_el, f"{{{ns}}}sheet")
            s.set("name", ws.title)
            s.set("sheetId", str(idx))
            s.set(f"{{{rns}}}id", f"rId{idx + 2}")
        zf.writestr("xl/workbook.xml", ET.tostring(root, encoding="unicode"))

    def _write_workbook_rels(self, zf: zipfile.ZipFile) -> None:
        ns = "http://schemas.openxmlformats.org/package/2006/relationships"
        ET.register_namespace("", ns)
        root = ET.Element(f"{{{ns}}}Relationships")
        base = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

        def _rel(rid: str, typ: str, target: str) -> None:
            el = ET.SubElement(root, f"{{{ns}}}Relationship")
            el.set("Id", rid)
            el.set("Type", typ)
            el.set("Target", target)

        _rel("rId1", f"{base}/styles", "styles.xml")
        _rel("rId2", f"{base}/sharedStrings", "sharedStrings.xml")
        for idx in range(1, len(self._sheets) + 1):
            _rel(f"rId{idx + 2}", f"{base}/worksheet", f"worksheets/sheet{idx}.xml")
        zf.writestr("xl/_rels/workbook.xml.rels", ET.tostring(root, encoding="unicode"))

    def _write_styles(self, zf: zipfile.ZipFile) -> None:
        """Build styles.xml from the collected style registry."""
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        ET.register_namespace("", ns)
        root = ET.Element(f"{{{ns}}}styleSheet")
        reg = self._registry

        # ── fonts ───────────────────────────────────────────────────────────
        fonts_el = ET.SubElement(root, f"{{{ns}}}fonts")
        fonts_el.set("count", str(len(reg.fonts)))
        for fnt in reg.fonts:
            f_el = ET.SubElement(fonts_el, f"{{{ns}}}font")
            ET.SubElement(f_el, f"{{{ns}}}sz").set("val", str(fnt.size))
            col_el = ET.SubElement(f_el, f"{{{ns}}}color")
            col_el.set("rgb", f"FF{fnt.color.upper().lstrip('#')}")
            ET.SubElement(f_el, f"{{{ns}}}name").set("val", fnt.name)
            if fnt.bold:
                ET.SubElement(f_el, f"{{{ns}}}b")
            if fnt.italic:
                ET.SubElement(f_el, f"{{{ns}}}i")

        # ── fills ───────────────────────────────────────────────────────────
        fills_el = ET.SubElement(root, f"{{{ns}}}fills")
        fills_el.set("count", str(len(reg.fills)))
        for fil in reg.fills:
            fill_el = ET.SubElement(fills_el, f"{{{ns}}}fill")
            pf_el = ET.SubElement(fill_el, f"{{{ns}}}patternFill")
            pf_el.set("patternType", fil.patternType)
            if fil.patternType == "solid":
                fg = ET.SubElement(pf_el, f"{{{ns}}}fgColor")
                fg.set("rgb", f"FF{fil.fgColor.upper().lstrip('#')}")

        # ── borders ─────────────────────────────────────────────────────────
        borders_el = ET.SubElement(root, f"{{{ns}}}borders")
        borders_el.set("count", str(len(reg.borders)))
        for brd in reg.borders:
            b_el = ET.SubElement(borders_el, f"{{{ns}}}border")
            for side_name, side_obj in [
                ("left", brd.left), ("right", brd.right),
                ("top", brd.top), ("bottom", brd.bottom),
            ]:
                s_el = ET.SubElement(b_el, f"{{{ns}}}{side_name}")
                if side_obj and side_obj.style:
                    s_el.set("style", side_obj.style)
                    clr = ET.SubElement(s_el, f"{{{ns}}}color")
                    clr.set("rgb", f"FF{side_obj.color.upper().lstrip('#')}")
            ET.SubElement(b_el, f"{{{ns}}}diagonal")

        # ── cellStyleXfs (required by spec — one default entry) ─────────────
        csxfs = ET.SubElement(root, f"{{{ns}}}cellStyleXfs")
        csxfs.set("count", "1")
        default_xf = ET.SubElement(csxfs, f"{{{ns}}}xf")
        default_xf.set("numFmtId", "0")
        default_xf.set("fontId", "0")
        default_xf.set("fillId", "0")
        default_xf.set("borderId", "0")

        # ── cellXfs — one entry per unique style combo seen across all cells ──
        xf_map: dict[XfKey, int] = {}
        xf_list: list[XfKey] = []

        def _register(f_id: int, fi_id: int, b_id: int,
                      ha: str, va: str, wr: bool) -> int:
            key: XfKey = (f_id, fi_id, b_id, ha, va, wr)
            if key not in xf_map:
                xf_map[key] = len(xf_list)
                xf_list.append(key)
            return xf_map[key]

        # Default xf (index 0)
        _register(0, 0, 0, "general", "bottom", False)

        # Walk all cells to pre-build the xf table before writing styles.xml
        for ws in self._sheets:
            for c in ws.cells.values():
                if c.value is None:
                    continue
                _register(
                    reg.get_font_id(c.font),
                    reg.get_fill_id(c.fill),
                    reg.get_border_id(c.border),
                    c.alignment.horizontal if c.alignment else "general",
                    c.alignment.vertical   if c.alignment else "bottom",
                    c.alignment.wrap_text  if c.alignment else False,
                )

        cxfs = ET.SubElement(root, f"{{{ns}}}cellXfs")
        cxfs.set("count", str(len(xf_list)))
        for (f_id, fi_id, b_id, ha, va, wr) in xf_list:
            xf = ET.SubElement(cxfs, f"{{{ns}}}xf")
            xf.set("numFmtId", "0")
            xf.set("fontId", str(f_id))
            xf.set("fillId", str(fi_id))
            xf.set("borderId", str(b_id))
            xf.set("xfId", "0")
            if f_id:
                xf.set("applyFont", "1")
            if fi_id:
                xf.set("applyFill", "1")
            if b_id:
                xf.set("applyBorder", "1")
            has_align = ha != "general" or va != "bottom" or wr
            if has_align:
                xf.set("applyAlignment", "1")
                align_el = ET.SubElement(xf, f"{{{ns}}}alignment")
                align_el.set("horizontal", ha)
                align_el.set("vertical", va)
                if wr:
                    align_el.set("wrapText", "1")

        self._xf_map = xf_map

        # ── cellStyles (required by openpyxl reader to avoid 'no default style' warning) ──
        cs_el = ET.SubElement(root, f"{{{ns}}}cellStyles")
        cs_el.set("count", "1")
        cs = ET.SubElement(cs_el, f"{{{ns}}}cellStyle")
        cs.set("name", "Normal")
        cs.set("xfId", "0")
        cs.set("builtinId", "0")

        zf.writestr("xl/styles.xml", ET.tostring(root, encoding="unicode"))

    def _write_shared_strings(self, zf: zipfile.ZipFile) -> None:
        """Write a minimal (empty) sharedStrings.xml — we use inline strings."""
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        ET.register_namespace("", ns)
        root = ET.Element(f"{{{ns}}}sst")
        root.set("count", "0")
        root.set("uniqueCount", "0")
        zf.writestr("xl/sharedStrings.xml", ET.tostring(root, encoding="unicode"))

    def _write_sheet(self, zf: zipfile.ZipFile, ws: Worksheet, idx: int) -> None:
        """Render and write a single Worksheet XML with correct xf style indices."""
        ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        ET.register_namespace("", ns)

        raw_xml = ws.to_xml(self._registry)
        root = ET.fromstring(raw_xml)

        for c_el in root.iter(f"{{{ns}}}c"):
            f_id   = int(c_el.attrib.pop("_font",   "0"))
            fi_id  = int(c_el.attrib.pop("_fill",   "0"))
            b_id   = int(c_el.attrib.pop("_border", "0"))
            ha     = c_el.attrib.pop("_halign", "general")
            va     = c_el.attrib.pop("_valign", "bottom")
            wr     = c_el.attrib.pop("_wrap",   "0") == "1"
            key: XfKey = (f_id, fi_id, b_id, ha, va, wr)
            xf_idx = self._xf_map.get(key, 0)
            if xf_idx:
                c_el.set("s", str(xf_idx))

        zf.writestr(f"xl/worksheets/sheet{idx}.xml",
                    ET.tostring(root, encoding="unicode"))
