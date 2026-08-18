"""Parse a spreadsheet or CSV into a structured JSON dump for the xray-import skill.

Reads an .xlsx, .xls, or .csv source, bounds each sheet by its real content
rather than its declared dimensions, and writes the sheets as JSON so the skill
can read back a faithful grid of every cell. Run it as:

    python3 parse_workbook.py <source> [--out <path.json>]

.xlsx and .csv are read with the Python standard library alone, so they need no
installed packages. Legacy .xls is the one exception: that old binary format is
read with xlrd, an optional package installed only when an .xls actually turns
up. The JSON holds one entry per sheet, each with its name and its rows as lists
of cell strings. A CSV becomes a single sheet named after the file. A short
summary is printed to stdout, including the output path.
"""

import argparse
import csv
import datetime
import io
import json
import os
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

# Some workbooks declare more rows than they hold, so stop after a run of blank rows.
MAX_EMPTY_STREAK = 200


def fail(message):
    """Print an error to stderr and exit with a non-zero status."""
    print(message, file=sys.stderr)
    sys.exit(1)


def stringify_value(value):
    """Return one native cell value as a plain string."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


def stringify_xls(cell, datemode):
    """Return one xlrd cell as a plain string, resolving its type."""
    import xlrd

    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return ""
    if cell.ctype == xlrd.XL_CELL_TEXT:
        return cell.value
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        number = cell.value
        return str(int(number)) if float(number).is_integer() else repr(number)
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(cell.value, datemode).isoformat()
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return "TRUE" if cell.value else "FALSE"
    if cell.ctype == xlrd.XL_CELL_ERROR:
        return "#ERROR"
    return str(cell.value)


def trim_grid(rows):
    """Drop trailing empty rows and trailing empty columns, keeping a rectangle."""
    while rows and all(cell == "" for cell in rows[-1]):
        rows.pop()
    if not rows:
        return []
    last_content_col = 0
    for row in rows:
        for index in range(len(row) - 1, -1, -1):
            if row[index] != "":
                last_content_col = max(last_content_col, index)
                break
    width = last_content_col + 1
    return [list(row[:width]) + [""] * (width - len(row)) for row in rows]


def build_sheet(name, index, rows):
    """Assemble one sheet record from its raw rows."""
    trimmed = trim_grid(rows)
    col_count = len(trimmed[0]) if trimmed else 0
    return {
        "name": name,
        "index": index,
        "row_count": len(trimmed),
        "col_count": col_count,
        "rows": trimmed,
    }


# An .xlsx file is a zip of XML parts, so the reader below leans on zipfile and
# ElementTree to pull the same cell values openpyxl would, without the package.

def local(tag):
    """Return an XML tag with its namespace stripped."""
    return tag.rsplit("}", 1)[-1]


def rich_text(element):
    """Concatenate the text of a shared or inline string, following its runs and
    ignoring phonetic (rPh) guides, the way Excel renders the cell."""
    parts = []
    for child in element:
        tag = local(child.tag)
        if tag == "t":
            parts.append(child.text or "")
        elif tag == "r":
            for run_child in child:
                if local(run_child.tag) == "t":
                    parts.append(run_child.text or "")
    return "".join(parts)


# Builtin number-format ids Excel treats as dates or times, plus a token test
# for custom format codes, together decide whether a numeric cell is a date.
BUILTIN_DATE_IDS = set(range(14, 23)) | {45, 46, 47}
DATE_TOKEN = re.compile(r"[dmyhs]", re.IGNORECASE)


def is_date_format(code):
    """Return whether a custom number-format code renders a date or time."""
    if not code:
        return False
    section = code.split(";")[0]
    section = re.sub(r'"[^"]*"', "", section)      # quoted literals
    section = re.sub(r"\\.", "", section)          # escaped characters
    section = re.sub(r"\[[^\]]*\]", "", section)   # [color], [condition], [h]
    section = section.replace("AM/PM", "").replace("am/pm", "")
    return bool(DATE_TOKEN.search(section))


WINDOWS_EPOCH = datetime.datetime(1899, 12, 30)
MAC_EPOCH = datetime.datetime(1904, 1, 1)
SECONDS_PER_DAY = 86400


def excel_serial_to_datetime(serial, epoch):
    """Convert an Excel date serial to a datetime or a time, matching openpyxl.
    A serial below 1 is a time of day. A serial below 60 on the 1900 epoch
    predates Excel's fictitious 29 Feb 1900, so it shifts back a day to stay
    correct."""
    whole_days, fraction = divmod(serial, 1)
    seconds = round(fraction * SECONDS_PER_DAY)
    if 0 <= serial < 1:
        return (WINDOWS_EPOCH + datetime.timedelta(seconds=seconds)).time()
    if epoch == WINDOWS_EPOCH and serial < 60:
        base = datetime.datetime(1899, 12, 31)
        return base + datetime.timedelta(days=int(whole_days) - 1, seconds=seconds)
    return epoch + datetime.timedelta(days=int(whole_days), seconds=seconds)


def cast_number(text):
    """Return a numeric cell as an int, or a float when it carries a point or exponent."""
    if "." in text or "E" in text or "e" in text:
        return float(text)
    return int(text)


def read_shared_strings(archive):
    """Return the shared-string table as a list of plain strings."""
    try:
        data = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    return [rich_text(si) for si in ET.fromstring(data)]


def read_styles(archive):
    """Return the cell-xf number-format ids and the custom format-code map."""
    try:
        data = archive.read("xl/styles.xml")
    except KeyError:
        return [], {}
    root = ET.fromstring(data)
    custom = {}
    cell_xfs = []
    for node in root:
        tag = local(node.tag)
        if tag == "numFmts":
            for fmt in node:
                custom[int(fmt.get("numFmtId"))] = fmt.get("formatCode", "")
        elif tag == "cellXfs":
            for xf in node:
                cell_xfs.append(int(xf.get("numFmtId", "0")))
    return cell_xfs, custom


def style_is_date(style_index, cell_xfs, custom):
    """Return whether the cell format at a style index renders a date or time."""
    if style_index is None or style_index >= len(cell_xfs):
        return False
    fmt_id = cell_xfs[style_index]
    if fmt_id in BUILTIN_DATE_IDS:
        return True
    if fmt_id in custom:
        return is_date_format(custom[fmt_id])
    return False


COLUMN_LETTERS = re.compile(r"[A-Za-z]+")


def column_index(ref):
    """Return the 0-based column index from a cell ref such as 'AB12'."""
    letters = COLUMN_LETTERS.match(ref).group().upper()
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def cell_value(cell, shared, cell_xfs, custom, epoch):
    """Resolve one <c> element to a native value matching openpyxl's read."""
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        for child in cell:
            if local(child.tag) == "is":
                return rich_text(child)
        return None

    value_node = None
    for child in cell:
        if local(child.tag) == "v":
            value_node = child
            break
    if value_node is None or value_node.text is None:
        return None
    raw = value_node.text

    if cell_type == "s":
        return shared[int(raw)]
    if cell_type in ("str", "e"):
        return raw
    if cell_type == "b":
        return raw not in ("0", "false", "FALSE", "")
    number = cast_number(raw)
    style_index = cell.get("s")
    style_index = int(style_index) if style_index is not None else None
    if style_is_date(style_index, cell_xfs, custom):
        return excel_serial_to_datetime(float(number), epoch)
    return number


REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def worksheet_targets(archive):
    """Return worksheet XML paths in workbook (sheet) order, each with its name."""
    rels = {}
    for rel in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels")):
        rels[rel.get("Id")] = rel.get("Target")
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    sheets = []
    for node in workbook.iter():
        if local(node.tag) != "sheet":
            continue
        target = rels.get(node.get(REL_ID) or node.get("id"), "")
        target = target.lstrip("/") if target.startswith("/") else "xl/" + target.lstrip("/")
        sheets.append((node.get("name"), target))
    return sheets


def workbook_epoch(archive):
    """Return the workbook's date epoch, honoring the rare 1904 date mode."""
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    for node in workbook.iter():
        if local(node.tag) == "workbookPr" and node.get("date1904") in ("1", "true"):
            return MAC_EPOCH
    return WINDOWS_EPOCH


def read_xlsx(workbook_path):
    """Read an .xlsx workbook into a list of sheet records using only the stdlib."""
    with zipfile.ZipFile(workbook_path) as archive:
        shared = read_shared_strings(archive)
        cell_xfs, custom = read_styles(archive)
        epoch = workbook_epoch(archive)
        sheets = []
        for index, (name, target) in enumerate(worksheet_targets(archive)):
            root = ET.fromstring(archive.read(target))
            cells_by_row = {}
            max_row = 0
            max_col = 0
            for node in root.iter():
                if local(node.tag) != "row":
                    continue
                row_num = int(node.get("r"))
                max_row = max(max_row, row_num)
                row_cells = {}
                running_col = 0
                for cell in node:
                    if local(cell.tag) != "c":
                        continue
                    ref = cell.get("r")
                    col = column_index(ref) if ref else running_col
                    running_col = col + 1
                    max_col = max(max_col, col)
                    row_cells[col] = cell_value(cell, shared, cell_xfs, custom, epoch)
                cells_by_row[row_num] = row_cells

            rows = []
            empty_streak = 0
            width = max_col + 1
            for row_num in range(1, max_row + 1):
                row_cells = cells_by_row.get(row_num, {})
                row = [stringify_value(row_cells.get(col)) for col in range(width)]
                if all(cell == "" for cell in row):
                    empty_streak += 1
                    if empty_streak >= MAX_EMPTY_STREAK:
                        break
                else:
                    empty_streak = 0
                rows.append(row)
            sheets.append(build_sheet(name, index, rows))
    return sheets


def read_xls(workbook_path):
    """Read a legacy .xls workbook into a list of sheet records."""
    try:
        import xlrd
    except ImportError:
        fail("xlrd is required to read legacy .xls files, and it is not installed.\n"
             "Install it for this interpreter with:\n"
             "  {} -m pip install --user xlrd\n"
             "xlrd is pure Python, so it needs no build tools. If the install reports "
             "an externally managed environment (PEP 668), retry with "
             "--break-system-packages appended.".format(sys.executable))
    book = xlrd.open_workbook(workbook_path)
    sheets = []
    for index in range(book.nsheets):
        sheet = book.sheet_by_index(index)
        rows = [
            [stringify_xls(sheet.cell(row_index, col_index), book.datemode)
             for col_index in range(sheet.ncols)]
            for row_index in range(sheet.nrows)
        ]
        sheets.append(build_sheet(sheet.name, index, rows))
    return sheets


def decode_csv_text(source_file):
    """Decode a CSV file to text. Supported sources include UTF-8, ISO-8859-1, ISO-8859-15, or Windows-1252. This function tries utf-8-sig, then cp1252, then latin-1, which maps every byte and so never raises."""
    with open(source_file, "rb") as handle:
        raw = handle.read()
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def read_csv(source_file):
    """Read a .csv file into a single sheet record named after the file."""
    text = decode_csv_text(source_file)
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;:|\t")
    except csv.Error:
        dialect = csv.excel
    rows = [list(row) for row in csv.reader(io.StringIO(text, newline=""), dialect)]
    return [build_sheet(os.path.basename(source_file), 0, rows)]


def default_output_path(workbook_path):
    """Return the default JSON path in a temp folder, named after the workbook."""
    stem = os.path.splitext(os.path.basename(workbook_path))[0]
    folder = os.path.join(tempfile.gettempdir(), "xray-import")
    return os.path.join(folder, stem + ".parsed.json")


def print_summary(result, output_path):
    """Print a short human-readable overview of the parsed workbook."""
    print("Parsed {} ({} format)".format(result["source_file"], result["format"]))
    print("Sheet count {}".format(result["sheet_count"]))
    for sheet in result["sheets"]:
        print("  [{}] {} -> {} rows by {} cols".format(
            sheet["index"], sheet["name"], sheet["row_count"], sheet["col_count"]))
    print("JSON written to {}".format(output_path))


def main():
    parser = argparse.ArgumentParser(
        description="Parse a spreadsheet or CSV into a JSON dump of its sheets.")
    parser.add_argument("source", help="Path to the .xlsx, .xls, or .csv file")
    parser.add_argument("--out", help="Path for the JSON dump (defaults to a temp file)")
    args = parser.parse_args()

    source_file = args.source
    if not os.path.isfile(source_file):
        fail("File not found: {}".format(source_file))

    extension = os.path.splitext(source_file)[1].lower()
    if extension == ".xlsx":
        source_format = "xlsx"
        sheets = read_xlsx(source_file)
    elif extension == ".xls":
        source_format = "xls"
        sheets = read_xls(source_file)
    elif extension == ".csv":
        source_format = "csv"
        sheets = read_csv(source_file)
    else:
        fail("Unsupported file type '{}'. This parser handles .xlsx, .xls, and .csv."
             .format(extension))

    result = {
        "source_file": os.path.abspath(source_file),
        "format": source_format,
        "sheet_count": len(sheets),
        "sheets": sheets,
    }

    output_path = args.out or default_output_path(source_file)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(result, output_file, indent=2, ensure_ascii=False)

    print_summary(result, output_path)


if __name__ == "__main__":
    main()
