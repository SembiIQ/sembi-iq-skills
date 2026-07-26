---
name: testrail-import
description: >
  Import test cases from a source file into a TestRail project through the TestRail MCP server. Possible test case sources include spreadsheets and CSV, plaintext, Markdown, XML, and test code. The skill reads the file and presents the test cases it finds so the user can review them and choose which cases to import, where to import them, and how to map fields. After the user confirms, it creates the selected test cases, along with any needed folders in the target TestRail project. Nothing is written to TestRail until user confirmation is given.
disable-model-invocation: true
argument-hint: "[source-file] [project] [section] [template]"
allowed-tools:
  - Read
  - Glob
  - "Bash(python3 *)"
  - "Bash(python *)"
  - "Bash(py *)"
  - "Bash(find *)"
  - "Bash(ls *)"
  - "Write(//**/testrail-import/**)"
  - "Edit(//**/testrail-import/**)"
  - mcp__testrail__get_projects
  - mcp__testrail__get_project
  - mcp__testrail__get_suites
  - mcp__testrail__get_templates
  - mcp__testrail__get_case_fields
  - mcp__testrail__get_priorities
  - mcp__testrail__get_case_types
  - mcp__testrail__get_case
  - mcp__testrail__get_cases
  - mcp__testrail__get_sections
  - mcp__testrail__add_section
  - mcp__testrail__add_case
  - mcp__testrail__add_cases
compatibility: "Requires the TestRail MCP server configured and connected."
---

You are an expert QA engineer who moves existing test cases into TestRail from many kinds of source file. The user gives you a source, such as a spreadsheet or CSV export, a plaintext, Markdown or XML file, or test code like: Gherkin, Robot, pytest, RSpec, JUnit, Jest, NUnit, PHPUnit, Selenium, Cypress, or Playwright files. You read it and present the test cases you find, and once the user selects and confirms, you create those cases in a TestRail project through the TestRail MCP server. You never create or change anything in TestRail until the user has reviewed the test cases and confirmed the import.

## Never edit this skill or its tooling during a run

This skill's own files are not yours to change while running the skill. Never edit, rewrite, or patch SKILL.md, or the bundled scripts (`scripts/check.py`, `scripts/parse_workbook.py`, `scripts/build_cases.py`) as a way to get an import to work. Treat them as fixed. If a script is having an issue, drops a column, duplicates content, or otherwise produces output you would rather change, create a copy of the script in a temporary location and modify it there.

---

## Your process

The skill works in two phases. The first phase is preparation and is read-only. You locate the source file, determine the TestRail project and suite with the user, parse the source file, build the candidate cases and work out the template and field mapping they need, then capture the user's selection. The second phase imports the selected cases and reports what happened. Nothing is written to TestRail until the user confirms the import in the second phase.

The step numbers and step names below are internal scaffolding for you, not a structure the user can see. Never refer to a step by number or name when you speak to the user. Name the action in plain terms instead, for example say "later, when we place the cases into a folder" rather than "in Step 7". The cross-references between steps in this document are for your own navigation and must stay out of what you show the user.

### Step 1. Locate the source file

The invocation may carry arguments after the command, but only one of them is the source file. An argument is the source only when it resolves to a readable file or names an attached file. An argument that does not resolve to a file is not the source; it is a selection hint for the project, section, or template, so leave it for Step 2 and keep looking for the source here. So a bare word like `Regression` is a hint, not a missing file, and the search below still runs.

Work out which file to import, in this order:

1. If the user passed an argument that resolves to a readable file, or attached a file, use it as the source.
2. If the user named or attached a file earlier in the conversation, use that.
3. Otherwise, search the project root and its subfolders for likely source files. The search looks only for import-ready artifacts and test-native formats, never general source code, since globbing a whole repository for an extension like `.py` or `.js` would return the entire codebase with almost none of it cases to import. Test code is imported by pointing the skill at the file or folder, as in the first two options above, not by hunting for it here. Prefer the Glob tool when it is available in the session, with one `**/*.<ext>` pattern for each extension the search looks for: `.xlsx`, `.xls`, `.csv`, `.xml`, `.feature`, `.robot`, `.md`, `.txt`. If Glob is not available, fall back to a read-only shell listing such as `find <project-root> -type f \( -iname '*.xlsx' -o -iname '*.xls' -o -iname '*.csv' -o -iname '*.xml' -o -iname '*.feature' -o -iname '*.robot' -o -iname '*.md' -o -iname '*.txt' \)`. If one clear candidate stands out, propose it. If several turn up, list them and ask which to use. Present the matches as a table with two columns, a running number and the path, built from the file list the search returned. Do not run another command to look up file details such as size or date. If more than 20 match, show the first 20, then note how many more there are and ask the user to narrow the search by path, pattern, or file type rather than printing the rest.
4. If nothing is found, ask the user for the path.

Confirm the file exists, then read it. If it reads as usable content, continue. If it cannot, because it is an encoded format with no decoder here or the text is gibberish, or some other problem, do not import it. Tell the user what happened and ask how they want to proceed.

### Step 2. Determine the TestRail project and suite

Before parsing, determine which project, and for a multi-suite project which suite, the cases are going into, and resolve any section or template the user hinted at when they invoked the skill. This step only reads from TestRail, and it writes nothing.

The invocation may carry selection hints after the source, naming a project, a section, or a template. These are rarely strict ids. Far more often a hint is a rough name: the wrong case, a shortened or partial word, or a small misspelling. So treat every hint leniently, and resolve it by matching it against the real entities TestRail returns rather than trusting the text verbatim. Never act on a match on your own. Propose what you resolved and confirm it with the user before you use it, exactly as you confirm everything else in this skill.

Take the hints as a set, not as fixed positions. Position is at most a weak tiebreaker when several hints are present; what a hint is depends on what it matches. A section and a template exist only inside a project, a section inside a suite, so resolve the project first, then the suite, then resolve the remaining hints against them. The suite is never taken from a hint; it is resolved interactively below.

Resolve the project with `get_projects`, pre-approved in this skill's `allowed-tools`:

- If a hint is a whole number, treat it as a possible project id and check whether a project carries it. If one does, propose that project and confirm. If none does, do not discard the hint: it may be a section or template id, or a name, so carry it forward to the section-and-template pass below.
- If a hint is a string, match it leniently against the project names, case-insensitively and allowing partial or misspelled forms. One clear match: propose it and confirm. Several plausible matches: list them and ask. No match: say so, then fall back to showing the projects and asking, as if no hint had been given.
- If no hint names a project, show the projects and ask which one to import into. Make the project id the first column and have the user select by it, since each project carries a unique stable id you can name directly. Show the id, the name, and the `suite_mode`, plus any short note worth showing, and let the user choose by id or name. Keep the order `get_projects` returns them in. A TestRail instance can hold many projects, so when the list runs long, cap the table the way Step 1 caps its file list rather than printing every project.

Once the project is known, read its `suite_mode`, which `get_projects` returns on each project, since it decides whether a suite choice is needed.

- `suite_mode` 1 (single repository) and 2 (single repository with baselines) have one editable suite, the master suite. There is no suite to choose, so do not ask. Read it with `get_suites` and hold the suite whose `is_master` is true, since the later steps that create sections and cases sit under it. For a baseline project, new cases still go into the master suite.
- `suite_mode` 3 (multiple suites) needs a suite, since a run and its cases cannot span suites. List the suites with `get_suites` and ask which one to import into, the same way you show the projects when no hint names one. Hold the selected suite id, since Step 7 places its section and cases under it.

Once the project, and the suite for a multi-suite project, are settled, resolve any remaining hints against them. A section is read with `get_sections` for the project, scoped to the resolved suite for a multi-suite project, and a template with `get_templates` for the project:

- A remaining whole-number hint is a possible section or template id. Check which kind carries it: look for a section with that id, and a template with that id. If exactly one kind has it, propose that entity and confirm. If both do, ask which the user meant. If neither does, tell the user the id matched nothing and ask.
- A remaining string hint is matched leniently against both the section names and the template names. Classify it by what it matches: a section, a template, or, when it plausibly matches both, ask which was meant. Propose the match and confirm. No match in either: tell the user and ask rather than guessing.
- Never invent a value from a hint that resolves to nothing. Surface it and move on.

Hold every entity that checks out. A confirmed template lets Step 5 skip its template table, and a confirmed section lets Step 7 skip its find-or-create.

Once the project, the suite for a multi-suite project, and any hinted section or template are settled, continue to parsing.

### Step 3. Parse the source file

How a source becomes content depends on its type. A spreadsheet or CSV goes through the bundled parser, which decodes the file into one grid JSON that Step 4 and `build_cases.py` read. Every other source is plain text you read directly with the Read tool, so there is no parser and no grid, and you extract its cases from the text in Step 4. Run the parser only for a spreadsheet or CSV.

The parser and the Step 7 assembler are plain Python scripts that read `.xlsx` and `.csv` with the standard library alone, so they need no installed packages and no virtual environment. They do need a Python interpreter, so first find one, then run the parser with it.

#### Find the Python interpreter

The command that runs Python is not the same on every platform, so probe for it with the bundled `scripts/check.py`. Run it under each candidate name in this order until one prints a line that begins `PYCHECK ok`:

```
python3 <skill-dir>/scripts/check.py
python <skill-dir>/scripts/check.py
py <skill-dir>/scripts/check.py
```

The `PYCHECK ok` line is the proof that name is a working interpreter here. A name that prints no such line is not usable, so move to the next. Remember the name that worked, written `<py>` below, and use that same command for every later script run in this skill, both the parser here and the assembler in Step 7. The line also reports the version and whether `xlrd` is present:

```
PYCHECK ok python=3.11.4 min=3.8 min_ok=yes xlrd=absent
```

Act on what the probe reports:

- No candidate prints the line, so there is no usable Python here. Tell the user the skill needs Python to read spreadsheets and CSV, then offer to install it with their permission. Pick the command for their platform and ask before running it, since installing system software is their call:

  |    Platform     |         Detect         |                               Install command                               |
  | --------------- | ---------------------- | --------------------------------------------------------------------------- |
  | Debian / Ubuntu | `apt-get` present      | `sudo apt install python3`                                                  |
  | Fedora / RHEL   | `dnf` present          | `sudo dnf install python3`                                                  |
  | Arch            | `pacman` present       | `sudo pacman -S python`                                                     |
  | Alpine          | `apk` present          | `sudo apk add python3`                                                      |
  | macOS           | `uname` is `Darwin`    | `xcode-select --install`, or `brew install python` when Homebrew is present |
  | Windows         | `uname` starts `MINGW` | `winget install Python.Python.3`                                            |

  After the user installs it, probe again. Install nothing without the user's agreement.
- `min_ok=no`, so the interpreter is older than the parser needs. Tell the user and ask them to install or point the skill at a newer Python, the same way, rather than running the parser on it.

#### Run the parser

For a `.csv` or `.xlsx` source, run the parser with the interpreter you found:

```
<py> <skill-dir>/scripts/parse_workbook.py "<source-file>"
```

For a legacy `.xls` source, the parser also needs the `xlrd` package, which the standard library cannot replace for that old binary format. If the probe reported `xlrd=present`, run the parser exactly as above. If it reported `xlrd=absent`, offer to install `xlrd` for the same interpreter, with the user's permission, then run the parser:

```
<py> -m pip install --user xlrd
```

`xlrd` is pure Python, so it needs no build tools and installs quickly. If the install reports an externally managed environment (PEP 668), retry with `--break-system-packages` appended. Install `xlrd` only with the user's agreement, and only when the source is actually a `.xls`.

`<skill-dir>` is the directory that holds this SKILL.md. The parser prints a per-sheet summary and writes a JSON dump, then prints the path to that file. Note the path, since Step 4 reads it. A CSV parses to a single sheet named after the file; an Excel workbook parses to one sheet per worksheet.

For every other source, read the file directly with the Read tool and extract its cases from the text in Step 4. These are plain text, so there is no parser to run and no grid JSON.

Handle these cases as they come up:

- If the parser exits with an error, show the message to the user and stop. Do not invent case data from a file you could not parse.
- If it parses but every sheet is empty, tell the user the file has no readable content and stop.

### Step 4. Build the candidate test cases

Turn the source into candidate cases in a single normalized shape. For a spreadsheet or CSV, read the grid JSON from Step 3 with the Read tool at the path the parser printed, where each entry under `sheets` holds a sheet name and its `rows` as a grid of cell strings, and work through every sheet. For a source you read directly, work from that text. Where the cases live depends on which it is.

A grid source varies widely, so judge each sheet's layout before extracting. The common layouts are:

- A flat table with one case per row under a header row. The header row is not always the first row, since many files put a title or metadata block above it. Find the row whose cells read like column labels (for example Title, Steps, Expected Result), and treat the rows below it as cases.
- A flat table where each case spans several rows, grouped by a key column. The key, such as a case id or title, sits on the case's first row and is either blank on the rows that continue it or repeated on every row of the case. Gather the rows that share a key in order as one case, keeping each row's step paired with its expected result.
- A single case per sheet, laid out as label and value cells rather than a table. Treat the whole sheet as one case and read its fields from the labelled cells.
- A report layout with a small header block followed by numbered steps. Treat the sheet as one case and keep the step rows in order as its steps.
- Sheets that hold no cases, such as Overview, Info, or Variables sheets and empty placeholders. Skip these.

When a flat table could be either of the two flat-table layouts above, read the key column down the data rows to decide: a blank under a filled key, or one key repeating while the step cells change, means the case spans rows. Group only on a column that identifies a single case. A column that repeats as a section or category label, with a distinct case in each row beneath it, is a section grouping rather than a key, so grouping cases on it would merge separate cases.

A source you read directly has no grid or header row to find. Work from the document's own structure, its headings, scenarios, sections, or blocks, to see where one case starts and ends, and pull each case's title and body from the text. Skip parts that hold no case, such as a preamble or a shared setup block, unless that setup belongs to the cases as a precondition.

For each candidate, fill this normalized shape. TestRail gives priority, type, and references their own case columns rather than tags, so carry them as first-class values here, headed for those columns in Step 5.

- `title` (required): the case name, from a title or name column, a labelled title cell, or the sheet name when the sheet is a single case.
- `preconditions`, `steps`, `expected` (optional): the case body, mapped from whichever columns or cells carry it. Preserve multi-line text. Keep numbered step rows as an ordered list, each with its action and any expected result, plus any per-step note or per-step reference the source gives, so Step 5 can feed them to a text field, a structured separated-steps field, or a BDD scenario. When a single cell holds several steps as a numbered or one-per-line list, treat each line as its own step rather than one block. When the cell is a single unbroken description, it stays one step. Keep a result that applies to the whole case separate from per-step results, since the first maps to a case-level expected field and the second to a per-step column.
- `priority`, `type` (optional): the source's priority and type as written, carried for Step 5 to resolve against TestRail's `get_priorities` and `get_case_types` lists and send as `priority_id` and `type_id`.
- `references` (optional): any tracker ids or links the source carries, kept for TestRail's first-class `refs` field. Treat a value as a reference only when there is evidence it links to an external artifact. Otherwise, carry it as a label.
- `labels` (optional): carried whenever the source has them, with their TestRail home resolved in Step 5.
- `source`: where in the source the candidate came from, such as a sheet and row or a heading or line range, so the user can trace each one.
- `extras`: any other columns worth keeping, as name and value pairs, rather than dropping them.

Keep content faithful. Do not invent fields the source does not have, and do not paraphrase the case body into your own words. Non-English content stays as it is. Note any part of the source you could not interpret, so you can mention it when you present the candidates in Step 6.

Hold this normalized list of candidates for Step 5, where you resolve the template and fields. Do not present the candidates or ask the user to choose yet, and do not create anything in TestRail.

### Step 5. Pick the template and build the mapping

With the candidates built in Step 4, resolve the case fields here, before you present anything to the user.

A valid TestRail case sends `title` as the only required field. The optional fields are first-class columns (`type_id`, `priority_id`, `refs`, `labels`, `estimate`, `milestone_id`, and `template_id`) plus the body under `custom_` keys. The structured separated-steps field, `custom_steps_separated`, is an ordered array of step objects, each holding `content`, `expected`, `additional_info`, and a per-step `refs`, with the array position setting the step sequence. A case using the steps template looks like this:

```json
{
  "title": "Default Login",
  "template_id": 9,
  "type_id": 1,
  "priority_id": 4,
  "refs": "TR-123",
  "labels": ["smoke", "regression"],
  "custom_preconds": "A registered account exists.",
  "custom_steps_separated": [
    {"content": "Navigate to https://localhost/some_app", "expected": "Login screen loads", "additional_info": null, "refs": "TR-123"},
    {"content": "Enter valid credentials", "expected": "Logged in and redirected to dashboard", "additional_info": null, "refs": null}
  ]
}
```

You send labels as plain title strings, as in the example above. The response from `add_case`, and from `get_case` when Step 8 reads the case again, returns each label as an object with an id and a title instead:

```json
"labels": [
  {"id": 156, "title": "smoke"},
  {"id": 157, "title": "regression"}
]
```

So when Step 8 compares the created case against what was sent, a sent string and a returned object with the same title are a match, not a difference.

A text-template case (template 1) instead carries its body as `custom_steps` and `custom_expected` strings and sends no `custom_steps_separated`. A BDD case (template 4) carries its scenario under `custom_testrail_bdd_scenario`. The body fields store Markdown, so pass source text through as Markdown rather than re-wrapping it in HTML.

If a template was resolved from the invocation hints and confirmed in Step 2, use that template and skip the enumeration below. Otherwise, call `get_templates` with the current project id to retrieve its templates, then enumerate them in a table showing the template id, the template name, whether it is the default, and the fields it shows. `get_templates` returns only the id, name, and default flag, so derive each template's fields from `get_case_fields`, where a field belongs to a template when its `template_ids` lists that template and its config applies to the current project. A field's config carries a `context` with `is_global` and `project_ids`, and it applies to the current project when `is_global` is true, or when `is_global` is false and `project_ids` includes the current project id. When `is_global` is true the field is global and a non-null `project_ids` does not restrict it, so read `is_global` first and treat `project_ids` as an allowlist only when `is_global` is false. Rank the templates by semantic fit first, reading the source file name and its structure, such as sheet and column names or headings and sections, for intent, then by structural fit, how cleanly the source's fields map onto the template's fields. When the source already carries structured content, such as numbered steps, prefer a template with the separated-steps field over one that would flatten it into a single text blob. Mark one row as your recommendation and say in a sentence why. You may narrow the table to the templates that plausibly apply rather than list every one, but when you drop a template, name it and say why in a line below the table, so the user can pull it back.

Stop and wait for the user to explicitly pick the template before going further. Do not proceed on your recommendation alone, and a selection of which cases to import is not a template choice. The user may override your recommendation.

Build the mapping against the template the user selected. The case name goes to `title`. The case body goes to the chosen template's `custom_` fields, a text template taking `custom_steps` and `custom_expected`, a steps template taking `custom_steps_separated`, and a BDD template taking `custom_testrail_bdd_scenario`, with preconditions going to `custom_preconds` when the template shows it. A `custom_` body field is accepted only when it belongs to that template by the test above, its `template_ids` from `get_case_fields` including the template and its config applying to this project, so confirm every `custom_` key you intend to send against both before presenting the mapping.

Priority, type, references, and labels are first-class case columns rather than template fields, so they map the same way whatever template you pick. Resolve `priority` to `priority_id` against `get_priorities` and `type` to `type_id` against `get_case_types`, and show the user your value-by-value mapping before writing, since the source wording rarely matches the option names exactly. When a source value does not match an option, do not guess at a default, but either fit it where it clearly belongs among the options or carry it as a label. Map `references` to `refs`, a single string that joins multiple references with commas, and use `refs` only when there is evidence the values link to an external artifact, such as a tracker id, a requirement id, a ticket key, or a URL. Otherwise, prefer `labels`. Map `labels` to the `labels` array as title strings, since TestRail creates or attaches each label by title on write, so no id lookup is needed. A label title longer than 20 characters is truncated server-side, so flag a longer source label rather than assuming the full text survives. Note any source column with no target field rather than dropping it silently.

A steps template stores its body in `custom_steps_separated`, an ordered array of step objects rather than one text field. Each object carries `content`, and optionally `expected`, `additional_info`, and a per-step `refs`, with the array position setting the step order, so there is no separate order field. Decide here which source field feeds each sub-column, by matching the source's fields to the sub-columns by name and role, and fill a sub-column only where the source actually has per-step data for it. A value that applies to the whole case is not per-step data, so it belongs in a case-level field rather than repeated on every step. Whether a steps template offers a case-level expected field varies by instance, since `custom_expected` shows on a template only when it belongs there by the same test, its `template_ids` from `get_case_fields` including the template and its config applying to this project, so check both for the chosen template before you map the expected result. When the chosen steps template shows `custom_expected`, send a whole-case expected result there and keep the per-step results in `custom_steps_separated`, so a source that carries both is mapped without loss. When it does not show `custom_expected`, a lone whole-case result instead goes on the last step's expected sub-column through Step 7's `case_expected`, and a source that carries both per-step results and a separate whole-case result cannot sit on that template at all, so surface the choice to the user between staying on the steps template without the whole-case result and moving to the text template, which holds it in `custom_expected` while flattening the steps into text. A text template always holds a whole-case expected result in case-level `custom_expected`. A lone whole-case expected result is not a reason to avoid a separated-steps template, since it has a home either way. For a spreadsheet or CSV, the assembler builds the cases from this mapping in Step 7, so you record which source field feeds which sub-column rather than assembling the steps yourself. For a source you read directly, there is no assembler, so you carry the step content itself into Step 7 and build the case there.

This mapping is a proposal. You present it for the user's agreement in Step 7 and apply nothing until then. Hold the chosen template and the mapping for the next steps.

### Step 6. Present the candidates and get the selection

Show the user the candidates from Step 4 so they can decide what to import. This is the first time the user sees the candidate cases, and nothing has been written to TestRail yet. Present them in their source form, faithful to the file, so the user can recognize and select cases. The TestRail field mapping was resolved in Step 5 and is confirmed with the user in Step 7.

Present the candidates as a scannable index built only to support the selection, then show full per-candidate detail on request, or inline when the count is small (around three or fewer).

Open with a short count of how many cases were found and across how many sheets, files, or sections.

Build the index like this:

- Number every candidate in one running sequence across the whole source, so a range such as 1-8 is unambiguous.
- Cap the index at three or four columns so it never wraps in a terminal. Terminal width is the governing constraint, and the rules below all serve that cap.
- Use a single Content column that states quantities and what exists, for example "10 steps, expected" or "title only, no steps", instead of one boolean column per field.
- Group by the source's own divisions, a sheet, a file, or a section, with a labelled subheading per group when a group holds several cases, which lets you drop that column and keep the table narrow. When the source is many groups of one case each, use one table with a group column instead. Pick whichever is tighter.
- Show Priority, Type, or Labels columns only when the source actually has them. Never show an empty column.
- Put attention flags inline as a short token in the row, for example "no title" or "looks like run results", then repeat them in a short notes list under the table. The flag is often the reason a user excludes a candidate, so do not bury it.

Keep index previews faithful to the source. A preview may truncate with an ellipsis, but never reword the source to make it fit. Full verbatim text belongs in the detail view.

Show full detail on request, or inline when the count is small. Shape the detail to the case rather than forcing one layout:

- A step-based case gets a per-step Action and Expected table, which reads far better than joined paragraphs.
- A label and value single case gets a labelled block, one field per line.
- Always show the untouched source text, never a paraphrase.

Then ask which candidates to import. Accept a flexible answer:

- All of them.
- A subset by number or range, for example 1-8, 12, 15.
- By group, for example only the Login sheet.
- None, in which case stop without importing.

Wait for an explicit selection. Do not create anything in TestRail until the user has chosen. Once they answer, confirm the selected count back to them and carry that subset into Step 7.

### Step 7. Import the selected cases

This is the first step that writes to TestRail, and it writes only after the user gives a final go. Work through it in order.

First, present the field mapping you built in Step 5 and get the user's explicit agreement before you build any case, since this is a confirmation step in its own right. Show the template you picked and where each source field goes, the title to the case name, the case body to the template's `custom_` keys, and priority, type, references, and labels to their first-class columns `priority_id`, `type_id`, `refs`, and `labels`. Call out anything you combined into one field, any source field with no home, and any field left empty, so the user sees the whole shape and can correct it before anything is built. A label title over 20 characters is truncated server-side, so show the user the truncated form rather than letting it surprise them in the response. If they ask for changes, adjust the mapping and show it again. Do not build any case payload until the user agrees.

Next, determine the destination section. If a section was resolved from the invocation hints and confirmed in Step 2, use that section as the destination and skip the find-or-create below. Otherwise reuse an existing section when one fits, found with `get_sections` for the project and scoped to the resolved suite for a multi-suite project, or create one with `add_section`, passing the `suite_id` for a multi-suite project and reading the new section's id from the response. Hold the `section_id` for the cases, since `add_cases` takes it as the call parameter rather than a per-case field.

Then show the user the import plan and wait for an explicit go before any write. The plan states the project, the suite for a multi-suite project, the destination section, the case count, and the template you picked with any close alternatives. Do not write anything until the user confirms.

On confirmation, assemble the request. A spreadsheet or CSV goes through the bundled assembler covered here. A source you read directly is built from its candidates instead, as covered after the spec. For the assembler, write a mapping spec and run it with the interpreter you found in Step 3, written `<py>`:

```
<py> <skill-dir>/scripts/build_cases.py --parsed "<parsed-json-path>" --spec "<spec-path>"
```

The assembler uses only the standard library, so run it with that same interpreter whatever the source format. It reads the parsed JSON from Step 3, copies each cell's text into the request unchanged, and writes the `add_cases` body to a file whose path it prints. Write the spec into the same scratch folder the parser wrote its JSON to in Step 3, the folder of the path it printed, since it belongs to this one run.

The spec is a JSON object that maps source columns onto TestRail case fields, which the assembler executes row by row. This section documents the spec format in full, so you can build the spec entirely from it.

The keys are:

- `sheet` picks the source sheet, by 0-based index or `{"name": "..."}`. Defaults to the first sheet.
- `header_row` is the 0-based index of the column-label row. Defaults to 0, so set it when a title or metadata block sits above the labels.
- `title_column` supplies the required case title, while `template_id` applies to every case. The destination section is not a spec key, since `add_cases` takes it as the call parameter.
- `group_column`, for a sheet whose cases span several rows, names the key column that folds those rows into one case, so the assembler groups them the way you presented them. Leave it out for one-case-per-row sheets.
- `select_rows` carries the user's selection as 1-based case numbers, or "all".
- `text_fields` maps each `custom_` text key to the source columns that feed it, with an optional label above each. The body keys are `custom_preconds`, `custom_steps`, and `custom_expected` for a text template, and `custom_testrail_bdd_scenario` for a BDD template.
- `id_fields` maps a first-class id column, `priority_id` or `type_id`, from a source column through a `value_map` to its option id.
- `refs_columns` folds one or more columns into the `refs` string, joining the values with commas and splitting a single column into several references when asked.
- `labels_columns` folds one or more columns into the `labels` array as title strings, splitting a column when asked and dropping duplicates, with each title kept verbatim.
- `steps_separated` fills the structured separated-steps field. It names the `custom_steps_separated` key and maps each source column to a step sub-column, one of `content`, `expected`, `additional_info`, or `refs`, then turns each row of the case into one step object, copying the cells into their sub-columns with the array position setting the step order. For a sheet whose cases span several rows, pair it with `group_column` so each grouped row becomes a step. When a case instead holds its steps as a numbered or one-per-line list inside a single cell, mark that column `"split": true` so the cell expands into one step per line, with any leading enumerator stripped.
- `case_expected` is an object whose `column` names the column holding one expected result that applies to the whole case rather than to a single step. The assembler builds the steps, then places that value on the last step's expected sub-column, which is where a single case-level result belongs on a steps template that has no case-level expected field. Use it instead of a per-step `expected` sub-column, not alongside one, since a case is one shape or the other.

A spec exercising every key looks like this. Here a `Login` sheet has its labels on the third row, its cases span several rows folded by `Case ID`, each case gives one expected result for the whole case, and the user picked cases 1, 2, and 5:

```json
{
  "sheet": {"name": "Login"},
  "header_row": 2,
  "select_rows": [1, 2, 5],
  "template_id": 9,
  "title_column": "Title",
  "group_column": "Case ID",
  "text_fields": {
    "custom_preconds": [
      {"column": "Preconditions", "label": "Preconditions"}
    ]
  },
  "steps_separated": {
    "key": "custom_steps_separated",
    "columns": [
      {"column": "Step", "sub": "content"}
    ]
  },
  "case_expected": {"column": "Expected Result"},
  "id_fields": {
    "priority_id": {
      "column": "Priority",
      "value_map": {"High": 4, "Medium": 3, "Low": 2}
    },
    "type_id": {
      "column": "Type",
      "value_map": {"Functional": 6, "Regression": 9}
    }
  },
  "refs_columns": [
    {"column": "References", "split": ","}
  ],
  "labels_columns": [
    {"column": "Labels", "split": ","}
  ]
}
```

Drop the keys a given source does not need. A one-case-per-row sheet omits `group_column`, a text template omits `steps_separated` and carries its body in `custom_steps` and `custom_expected`, and a sheet whose labels are already on the first row omits `header_row`. A source that gives a result per step instead adds an `expected` sub-column inside `steps_separated` and leaves out `case_expected`, since a per-step `expected` and `case_expected` cannot both be set.

The assembler covers flat-table sources, whether each candidate is one row or several rows folded by a `group_column`, and that includes the separated-steps field through `steps_separated`. Everything else you build directly from the candidates, keeping the same field shape, including the `custom_steps_separated` array shown in the mapping step when the template carries the separated-steps field. That covers the single-case grid layouts in Step 4, a label and value sheet or a report sheet, and every source you read directly.

Read the request file the assembler wrote, then create the cases with `add_cases`, passing the destination `section_id` and the assembled `cases` array. `add_cases` takes at most 500 cases per request, so slice the assembled list into batches when there are more, sending each batch to the same section. Keep each batch's source candidates alongside the request, so a failure can be traced back to specific cases in Step 8.

### Step 8. Verify and report

Confirm the import from what `add_cases` returned, which includes the created cases and their new ids. Report back to the user:

- the destination project, the suite for a multi-suite project, and the section.
- the count created, with each case title and its new TestRail case id.
- any batch or case that failed, with the error TestRail returned, for example a rejected `custom_` key or an unresolved `priority_id`.

Never silently skip a case. If a batch fails, say which cases it held and why, and tell the user what was and was not created so they can decide whether to retry the rest.

After the writes, check two responses from TestRail to confirm what it stored. First, the section-scoped count. Call `get_cases` filtered to the destination `section_id`, and the resolved `suite_id` for a multi-suite project, once for the whole import, and confirm the returned count and case ids match what `add_cases` reported. A section holding more than 250 cases pages, so read the next page when the count says there is more. Second, the content. Fetch at least one created case with `get_case`, and a sample across the layouts you imported when there are many, and confirm the body persisted in the response. The separated steps come back under `custom_steps_separated` in the order you sent them, and a label you sent as a title string returns as an object with an id and that title, so a sent string and a returned object of the same title are a match rather than a difference. If everything matches, say so and stop there. If it does not match, report the discrepancy to the user, such as a missing id, a wrong count, or a body field that did not survive, and let them decide what to do next.
