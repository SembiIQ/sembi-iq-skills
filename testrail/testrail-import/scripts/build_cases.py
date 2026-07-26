"""Assemble an add_cases request from a parsed source and a spec.

    python3 build_cases.py --parsed <parsed.json> --spec <spec.json> [--out <path.json>]

Reads the parse_workbook.py JSON dump and a mapping spec, and writes the
request body for the add_cases tool. Source cell text is copied into the
request unchanged. The destination section is not part of the request body,
since add_cases takes section_id as its own call parameter.

The spec is a JSON object keyed by:
    sheet            sheet index, or {"name": "..."}; default 0
    header_row       0-based index of the column-label row; default 0
    select_rows      "all", or a list of 1-based case numbers; default "all"
    template_id      template id applied to every case (optional)
    title_column     column supplying the required case title
    group_column     column whose key folds consecutive rows into one case, a
                     blank or repeated key continuing the case above (optional)
    text_fields      custom_ key -> [{"column", "label"}]; parts join with a
                     blank line, a label sits above its text, empty parts
                     drop, repeated values within a column collapse to one
    id_fields        first-class id key (priority_id or type_id) ->
                     {"column", "value_map"}; cell text maps to an option id,
                     an unmapped non-empty value is an error
    refs_columns     [{"column", "split"}]; values fold into the refs string,
                     joined with ", ", split on the separator when one is
                     given, kept verbatim, duplicates dropped
    labels_columns   [{"column", "split"}]; values fold into the labels array
                     as title strings, split on the separator when one is
                     given, kept verbatim, duplicates dropped
    steps_separated  {"key", "columns": [{"column", "sub", "split"}]} for the
                     structured separated-steps field, where key is the
                     custom_ steps key and each case row becomes one step
                     object. A row copies its mapped cells into the named
                     sub-columns (content, expected, additional_info, refs),
                     and array position sets the step order with no order
                     field. Rows empty across all mapped columns are skipped.
                     A column marked "split": true holds several steps in one
                     cell, one per line, and expands into one step object per
                     line with any leading enumerator stripped
    case_expected    {"column"} for one expected result that applies to the
                     whole case rather than to a single step. The assembler
                     builds the steps, then sets the last step's expected
                     sub-column to this column's value. Requires steps_separated,
                     and is rejected alongside an expected sub-column in its
                     columns list
"""

import argparse
import json
import os
import re
import sys
import tempfile


STEP_SUBS = ("content", "expected", "additional_info", "refs")


def fail(message):
    """Print an error to stderr and exit with a non-zero status."""
    print(message, file=sys.stderr)
    sys.exit(1)


def pick_sheet(parsed, spec):
    """Return the sheet record named or indexed by the spec."""
    sheets = parsed.get("sheets", [])
    if not sheets:
        fail("Parsed file holds no sheets.")
    selector = spec.get("sheet", 0)
    if isinstance(selector, dict):
        wanted_name = selector.get("name")
        for sheet in sheets:
            if sheet["name"] == wanted_name:
                return sheet
        fail("No sheet named '{}'.".format(wanted_name))
    if not isinstance(selector, int) or selector < 0 or selector >= len(sheets):
        fail("Sheet index {} is out of range (have {}).".format(selector, len(sheets)))
    return sheets[selector]


def build_column_index(header, spec_columns):
    """Map each spec column name to its position in the header row."""
    column_index = {}
    for position, label in enumerate(header):
        if label not in column_index:
            column_index[label] = position
    for column_name in spec_columns:
        if column_name not in column_index:
            fail("Column '{}' is not in the header row {}.".format(column_name, header))
    return column_index


def collect_spec_columns(spec):
    """Return every column name the spec references, for up-front validation."""
    column_names = set()
    if spec.get("title_column"):
        column_names.add(spec["title_column"])
    for parts in spec.get("text_fields", {}).values():
        for part in parts:
            column_names.add(part["column"])
    for field in spec.get("id_fields", {}).values():
        column_names.add(field["column"])
    for entry in spec.get("refs_columns", []):
        column_names.add(entry["column"])
    for entry in spec.get("labels_columns", []):
        column_names.add(entry["column"])
    steps_separated = spec.get("steps_separated")
    if steps_separated:
        for entry in steps_separated["columns"]:
            column_names.add(entry["column"])
    case_expected = spec.get("case_expected")
    if case_expected:
        column_names.add(case_expected["column"])
    if spec.get("group_column"):
        column_names.add(spec["group_column"])
    return column_names


def group_data_rows(data_rows, key_position):
    """Fold consecutive data rows into cases by their key column. A non-empty key different from the current case starts a new case, a non-empty key equal to it continues the case, and a blank key continues the case above."""
    cases = []
    current = None
    current_key = None
    for row in data_rows:
        key = cell(row, key_position)
        if key and key != current_key:
            current = [row]
            cases.append(current)
            current_key = key
        elif current is None:
            fail("Data begins with a blank key column, so the first rows belong "
                 "to no case. Check the group_column or header_row.")
        else:
            current.append(row)
    return cases


def selected_cases(sheet, spec, column_index):
    """Return the chosen cases as (one_based_number, rows) pairs. A case is one row without a group_column, or the consecutive rows sharing a key with one. select_rows indexes these cases."""
    header_row = spec.get("header_row", 0)
    data_rows = sheet["rows"][header_row + 1:]
    group_column = spec.get("group_column")
    if group_column:
        cases = group_data_rows(data_rows, column_index[group_column])
    else:
        cases = [[row] for row in data_rows]
    numbered = list(enumerate(cases, start=1))
    selection = spec.get("select_rows", "all")
    if selection == "all":
        return numbered
    chosen = []
    for number in selection:
        if not isinstance(number, int) or number < 1 or number > len(numbered):
            fail("Selected case {} is out of range (have {} cases)."
                 .format(number, len(numbered)))
        chosen.append(numbered[number - 1])
    return chosen


def cell(row, position):
    """Return the trimmed string at a column position, or empty if past the row."""
    if position >= len(row):
        return ""
    return row[position].strip()


def build_text_field(parts, rows, column_index):
    """Join the configured column parts into one custom field value, gathering each column down the rows of the case and dropping duplicate values."""
    chunks = []
    for part in parts:
        position = column_index[part["column"]]
        values = []
        for row in rows:
            value = cell(row, position)
            if value and value not in values:
                values.append(value)
        if not values:
            continue
        body = "\n\n".join(values)
        label = part.get("label")
        chunks.append(label + "\n\n" + body if label else body)
    return "\n\n".join(chunks)


# Matches a leading step number such as "1." or "2)" with its surrounding space.
ENUMERATOR = re.compile(r"^\s*\d+[.)]\s*")


def split_into_steps(value):
    """Return a cell's non-empty lines as step actions, with any leading enumerator stripped."""
    actions = []
    for line in value.splitlines():
        action = ENUMERATOR.sub("", line.strip())
        if action:
            actions.append(action)
    return actions


def build_steps_separated(steps_separated, rows, column_index):
    """Return the ordered step array for the separated-steps field, the array position setting each step's order. A column marked "split" expands its cell into one step per line. With no such column, every case row maps to a single step."""
    for entry in steps_separated["columns"]:
        if entry["sub"] not in STEP_SUBS:
            fail("Step sub-column '{}' is not one of {}.".format(entry["sub"], list(STEP_SUBS)))
    split_entry = next((entry for entry in steps_separated["columns"] if entry.get("split")), None)
    if split_entry:
        position = column_index[split_entry["column"]]
        steps = []
        for row in rows:
            for action in split_into_steps(cell(row, position)):
                steps.append({split_entry["sub"]: action})
        return steps
    steps = []
    for row in rows:
        step = {}
        for entry in steps_separated["columns"]:
            value = cell(row, column_index[entry["column"]])
            if value:
                step[entry["sub"]] = value
        if step:
            steps.append(step)
    return steps


def gather_values(entry, rows, column_index):
    """Return the column's values across the rows of the case, split on the separator when one is given, kept verbatim, duplicates dropped."""
    position = column_index[entry["column"]]
    separator = entry.get("split")
    values = []
    for row in rows:
        value = cell(row, position)
        if not value:
            continue
        pieces = value.split(separator) if separator else [value]
        for piece in pieces:
            piece = piece.strip()
            if piece and piece not in values:
                values.append(piece)
    return values


def build_refs(refs_columns, rows, column_index):
    """Fold the configured columns into the refs string, joined with ", "."""
    refs = []
    for entry in refs_columns:
        for value in gather_values(entry, rows, column_index):
            if value not in refs:
                refs.append(value)
    return ", ".join(refs)


def build_labels(labels_columns, rows, column_index):
    """Fold the configured columns into an ordered list of label title strings."""
    labels = []
    for entry in labels_columns:
        for value in gather_values(entry, rows, column_index):
            if value not in labels:
                labels.append(value)
    return labels


def first_cell(rows, position):
    """Return the first non-empty cell at a column position across the rows, or empty if none hold a value."""
    for row in rows:
        value = cell(row, position)
        if value:
            return value
    return ""


def build_case(number, rows, spec, column_index):
    """Assemble one case object from the one or more rows that form it. Single-value fields take the first row that carries them, and text, refs, and label fields gather down every row."""
    title = first_cell(rows, column_index[spec["title_column"]])
    if not title:
        fail("Case {} has no value in title column '{}'."
             .format(number, spec["title_column"]))

    case = {"title": title}
    if spec.get("template_id") is not None:
        case["template_id"] = spec["template_id"]

    for field_key, parts in spec.get("text_fields", {}).items():
        value = build_text_field(parts, rows, column_index)
        if value:
            case[field_key] = value

    steps_separated = spec.get("steps_separated")
    steps = build_steps_separated(steps_separated, rows, column_index) if steps_separated else []

    case_expected = spec.get("case_expected")
    if case_expected:
        if not steps_separated:
            fail("Spec sets case_expected but has no steps_separated.")
        if any(entry["sub"] == "expected" for entry in steps_separated["columns"]):
            fail("Spec sets both a per-step expected sub-column and case_expected.")
        value = first_cell(rows, column_index[case_expected["column"]])
        if value:
            if not steps:
                fail("Case {} has a case_expected value but no steps to place it on."
                     .format(number))
            steps[-1]["expected"] = value

    if steps:
        case[steps_separated["key"]] = steps

    for field_key, field in spec.get("id_fields", {}).items():
        value = first_cell(rows, column_index[field["column"]])
        if not value:
            continue
        value_map = field["value_map"]
        if value not in value_map:
            fail("Case {} has '{}' in column '{}', which is not in the "
                 "value_map for {}.".format(number, value, field["column"], field_key))
        case[field_key] = value_map[value]

    refs = build_refs(spec.get("refs_columns", []), rows, column_index)
    if refs:
        case["refs"] = refs

    labels = build_labels(spec.get("labels_columns", []), rows, column_index)
    if labels:
        case["labels"] = labels
    return case


def default_output_path(parsed_path):
    """Return the default request path in a temp folder, named after the source."""
    stem = os.path.splitext(os.path.basename(parsed_path))[0]
    folder = os.path.join(tempfile.gettempdir(), "testrail-import")
    return os.path.join(folder, stem + ".cases.json")


def print_summary(cases, output_path):
    """Print a short overview of the assembled cases."""
    print("Assembled {} case(s)".format(len(cases)))
    for case in cases:
        custom_keys = [field_key for field_key in case if field_key.startswith("custom_")]
        print("  - {} | priority_id={} | type_id={} | labels={} | fields={}".format(
            case["title"][:55],
            case.get("priority_id", "-"),
            case.get("type_id", "-"),
            case.get("labels", []),
            custom_keys))
    print("Request written to {}".format(output_path))


def main():
    parser = argparse.ArgumentParser(
        description="Assemble an add_cases request from a parsed source.")
    parser.add_argument("--parsed", required=True, help="Path to the parse_workbook.py JSON dump")
    parser.add_argument("--spec", required=True, help="Path to the mapping spec JSON")
    parser.add_argument("--out", help="Path for the request JSON (defaults to a temp file)")
    args = parser.parse_args()

    for path in (args.parsed, args.spec):
        if not os.path.isfile(path):
            fail("File not found: {}".format(path))

    with open(args.parsed, encoding="utf-8") as handle:
        parsed = json.load(handle)
    with open(args.spec, encoding="utf-8") as handle:
        spec = json.load(handle)

    if not spec.get("title_column"):
        fail("Spec must set 'title_column'.")

    sheet = pick_sheet(parsed, spec)
    header_row = spec.get("header_row", 0)
    if header_row >= len(sheet["rows"]):
        fail("header_row {} is past the end of sheet '{}'.".format(header_row, sheet["name"]))
    header = sheet["rows"][header_row]
    column_index = build_column_index(header, collect_spec_columns(spec))

    cases = [build_case(number, rows, spec, column_index)
             for number, rows in selected_cases(sheet, spec, column_index)]
    if not cases:
        fail("No rows selected, nothing to assemble.")

    request = {"cases": cases}
    output_path = args.out or default_output_path(args.parsed)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(request, output_file, ensure_ascii=False)

    print_summary(cases, output_path)


if __name__ == "__main__":
    main()
