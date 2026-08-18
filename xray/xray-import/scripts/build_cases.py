"""Assemble create_test call arguments from a parsed source and a spec.

    python3 build_cases.py --parsed <parsed.json> --spec <spec.json> [--out <path.json>]

Reads the parse_workbook.py JSON dump and a mapping spec, and writes the
arguments for the create_test tool. Source cell text is copied into the
arguments unchanged. Xray creates one Test per call, so the output holds a
"tests" array with one complete argument set per call rather than a single
bulk request body, and the skill sends each entry as it stands.

The spec is a JSON object keyed by:
    sheet            sheet index, or {"name": "..."}; default 0
    header_row       0-based index of the column-label row; default 0
    select_rows      "all", or a list of 1-based case numbers; default "all"
    project          {"key"} or {"id"} for the Jira project every Test is
                     created in, sent as the Jira project field
    summary_column   column supplying the required Jira issue summary
    test_type        {"name"} or {"id"} for the Test Type applied to every
                     Test, such as {"name": "Manual"} (optional)
    folder_path      Test Repository folder path applied to every Test, such
                     as "/Login" (optional)
    group_column     column whose key groups consecutive rows into one case, a
                     blank or repeated key continuing the case above (optional)
    description_fields  [{"column", "label"}] combined into the Jira
                     description, the one free-text field a Test carries.
                     Parts join with a blank line, a label sits above its text,
                     empty parts drop, repeated values within a column collapse
                     to one
    priority         {"column", "value_map"}; cell text maps to a Jira priority
                     name, an unmapped non-empty value is an error
    labels_columns   [{"column", "split"}]; values go into the Jira labels
                     array, split on the separator when one is given, and each
                     label is normalized to the space-free form Jira requires,
                     with duplicates dropped
    steps            {"columns": [{"column", "sub", "split"}]} for a Manual
                     Test's steps, where each case row becomes one step object.
                     A row copies its mapped cells into the named sub-columns
                     (action, data, result), and array position sets the step
                     order with no order field. Rows empty across all mapped
                     columns are skipped. A column marked "split": true holds
                     several steps in one cell, one per line, and expands into
                     one step object per line with any leading enumerator
                     stripped
    case_result      {"column"} for one expected result that applies to the
                     whole case rather than to a single step. The assembler
                     builds the steps, then sets the last step's result
                     sub-column to this column's value. Requires steps, and is
                     rejected alongside a result sub-column in its columns list
    gherkin_column   {"column"} holding a Cucumber Test's scenario, for a
                     Gherkin kind Test Type
    unstructured_column  {"column"} holding a Generic Test's definition, for an
                     Unstructured kind Test Type

A Test carries one body, so steps, gherkin_column, and unstructured_column are
mutually exclusive.
"""

import argparse
import json
import os
import re
import sys
import tempfile


STEP_SUBS = ("action", "data", "result")

BODY_KEYS = ("steps", "gherkin_column", "unstructured_column")


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
    if spec.get("summary_column"):
        column_names.add(spec["summary_column"])
    for part in spec.get("description_fields", []):
        column_names.add(part["column"])
    if spec.get("priority"):
        column_names.add(spec["priority"]["column"])
    for entry in spec.get("labels_columns", []):
        column_names.add(entry["column"])
    steps = spec.get("steps")
    if steps:
        for entry in steps["columns"]:
            column_names.add(entry["column"])
    for key in ("case_result", "gherkin_column", "unstructured_column"):
        if spec.get(key):
            column_names.add(spec[key]["column"])
    if spec.get("group_column"):
        column_names.add(spec["group_column"])
    return column_names


def group_data_rows(data_rows, key_position):
    """Group consecutive data rows into cases by their key column. A non-empty key different from the current case starts a new case, a non-empty key equal to it continues the case, and a blank key continues the case above."""
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
    """Join the configured column parts into one text value, gathering each column down the rows of the case and dropping duplicate values."""
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


def build_steps(steps_spec, rows, column_index):
    """Return the ordered step array for a Manual Test, the array position setting each step's order. A column marked "split" expands its cell into one step per line. With no such column, every case row maps to a single step."""
    for entry in steps_spec["columns"]:
        if entry["sub"] not in STEP_SUBS:
            fail("Step sub-column '{}' is not one of {}.".format(entry["sub"], list(STEP_SUBS)))
    split_entry = next((entry for entry in steps_spec["columns"] if entry.get("split")), None)
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
        for entry in steps_spec["columns"]:
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


LABEL_WHITESPACE = re.compile(r"\s+")


def normalize_label(value):
    """Return a Jira-safe label, since Jira rejects a label holding whitespace."""
    return LABEL_WHITESPACE.sub("-", value.strip())


def build_labels(labels_columns, rows, column_index):
    """Collect the configured columns into an ordered list of Jira-safe labels."""
    labels = []
    for entry in labels_columns:
        for value in gather_values(entry, rows, column_index):
            label = normalize_label(value)
            if label and label not in labels:
                labels.append(label)
    return labels


def first_cell(rows, position):
    """Return the first non-empty cell at a column position across the rows, or empty if none hold a value."""
    for row in rows:
        value = cell(row, position)
        if value:
            return value
    return ""


def build_body(number, spec, rows, column_index):
    """Return the Test's body as a single key and value pair, one of steps, gherkin, or unstructured, or an empty dict when the source carries no body."""
    gherkin_column = spec.get("gherkin_column")
    if gherkin_column:
        value = build_text_field([gherkin_column], rows, column_index)
        return {"gherkin": value} if value else {}

    unstructured_column = spec.get("unstructured_column")
    if unstructured_column:
        value = build_text_field([unstructured_column], rows, column_index)
        return {"unstructured": value} if value else {}

    steps_spec = spec.get("steps")
    if not steps_spec:
        return {}

    steps = build_steps(steps_spec, rows, column_index)
    case_result = spec.get("case_result")
    if case_result:
        value = first_cell(rows, column_index[case_result["column"]])
        if value:
            if not steps:
                fail("Case {} has a case_result value but no steps to place it on."
                     .format(number))
            steps[-1]["result"] = value
    return {"steps": steps} if steps else {}


def assemble_call(spec, jira_fields, body):
    """Return one complete create_test argument set. This is the only place that knows the tool's argument shape, so a change to that shape stays here."""
    call = {"jira": {"fields": jira_fields}}
    if spec.get("test_type"):
        call["test_type"] = spec["test_type"]
    if spec.get("folder_path"):
        call["folder_path"] = spec["folder_path"]
    call.update(body)
    return call


def build_test(number, rows, spec, column_index):
    """Assemble one create_test argument set from the one or more rows that form the case. Single-value fields take the first row that carries them, and the description and label fields gather down every row."""
    summary = first_cell(rows, column_index[spec["summary_column"]])
    if not summary:
        fail("Case {} has no value in summary column '{}'."
             .format(number, spec["summary_column"]))

    jira_fields = {"summary": summary, "project": spec["project"]}

    description = build_text_field(spec.get("description_fields", []), rows, column_index)
    if description:
        jira_fields["description"] = description

    priority = spec.get("priority")
    if priority:
        value = first_cell(rows, column_index[priority["column"]])
        if value:
            value_map = priority["value_map"]
            if value not in value_map:
                fail("Case {} has '{}' in column '{}', which is not in the "
                     "priority value_map.".format(number, value, priority["column"]))
            jira_fields["priority"] = {"name": value_map[value]}

    labels = build_labels(spec.get("labels_columns", []), rows, column_index)
    if labels:
        jira_fields["labels"] = labels

    body = build_body(number, spec, rows, column_index)
    return assemble_call(spec, jira_fields, body)


def default_output_path(parsed_path):
    """Return the default output path in a temp folder, named after the source."""
    stem = os.path.splitext(os.path.basename(parsed_path))[0]
    folder = os.path.join(tempfile.gettempdir(), "xray-import")
    return os.path.join(folder, stem + ".tests.json")


def print_summary(tests, output_path):
    """Print a short overview of the assembled Tests."""
    print("Assembled {} test(s)".format(len(tests)))
    for test in tests:
        jira_fields = test["jira"]["fields"]
        priority = jira_fields.get("priority", {}).get("name", "-")
        body = next((key for key in ("steps", "gherkin", "unstructured") if key in test), "none")
        size = len(test["steps"]) if body == "steps" else "-"
        print("  - {} | priority={} | labels={} | body={} | steps={}".format(
            jira_fields["summary"][:55],
            priority,
            jira_fields.get("labels", []),
            body,
            size))
    print("Call arguments written to {}".format(output_path))


def validate_spec(spec):
    """Reject a spec that cannot assemble a Test, before any row is read."""
    if not spec.get("summary_column"):
        fail("Spec must set 'summary_column'.")
    project = spec.get("project")
    if not isinstance(project, dict) or not (project.get("key") or project.get("id")):
        fail("Spec must set 'project' to an object holding a 'key' or an 'id'.")

    bodies = [key for key in BODY_KEYS if spec.get(key)]
    if len(bodies) > 1:
        fail("Spec sets {}, but a Test carries one body.".format(" and ".join(bodies)))

    case_result = spec.get("case_result")
    if case_result:
        steps_spec = spec.get("steps")
        if not steps_spec:
            fail("Spec sets case_result but has no steps.")
        if any(entry["sub"] == "result" for entry in steps_spec["columns"]):
            fail("Spec sets both a per-step result sub-column and case_result.")


def main():
    parser = argparse.ArgumentParser(
        description="Assemble create_test call arguments from a parsed source.")
    parser.add_argument("--parsed", required=True, help="Path to the parse_workbook.py JSON dump")
    parser.add_argument("--spec", required=True, help="Path to the mapping spec JSON")
    parser.add_argument("--out", help="Path for the call arguments JSON (defaults to a temp file)")
    args = parser.parse_args()

    for path in (args.parsed, args.spec):
        if not os.path.isfile(path):
            fail("File not found: {}".format(path))

    with open(args.parsed, encoding="utf-8") as handle:
        parsed = json.load(handle)
    with open(args.spec, encoding="utf-8") as handle:
        spec = json.load(handle)

    validate_spec(spec)

    sheet = pick_sheet(parsed, spec)
    header_row = spec.get("header_row", 0)
    if header_row >= len(sheet["rows"]):
        fail("header_row {} is past the end of sheet '{}'.".format(header_row, sheet["name"]))
    header = sheet["rows"][header_row]
    column_index = build_column_index(header, collect_spec_columns(spec))

    tests = [build_test(number, rows, spec, column_index)
             for number, rows in selected_cases(sheet, spec, column_index)]
    if not tests:
        fail("No rows selected, nothing to assemble.")

    output_path = args.out or default_output_path(args.parsed)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump({"tests": tests}, output_file, ensure_ascii=False)

    print_summary(tests, output_path)


if __name__ == "__main__":
    main()
