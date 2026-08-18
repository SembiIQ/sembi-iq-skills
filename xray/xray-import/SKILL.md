---
name: xray-import
description: >
  Import test cases from a source file into an Xray project through the Xray MCP server. Possible test case sources include spreadsheets and CSV, plaintext, Markdown, XML, and test code. The skill reads the file and presents the test cases it finds so the user can review them and choose which cases to import, where to import them, and how to map fields. After the user confirms, it creates the selected test cases as Xray Tests in the target Jira project, along with any needed Test Repository folders and any shared Preconditions the user asks for. Nothing is written to Xray until user confirmation is given.
disable-model-invocation: true
argument-hint: "[source-file] [project] [folder] [test-type]"
allowed-tools:
  - Read
  - Glob
  - "Bash(python3 *)"
  - "Bash(python *)"
  - "Bash(py *)"
  - "Bash(find *)"
  - "Bash(ls *)"
  - "Write(//**/xray-import/**)"
  - "Edit(//**/xray-import/**)"
  - mcp__xray__get_project_settings
  - mcp__xray__describe_type
  - mcp__xray__get_folder
  - mcp__xray__get_test
  - mcp__xray__get_tests
  - mcp__xray__create_folder
  - mcp__xray__create_test
  - mcp__xray__create_precondition
  - mcp__xray__get_preconditions
  - mcp__xray__add_tests_to_folder
compatibility: "Requires the Xray MCP server configured and connected."
---

You are an expert QA engineer who moves existing test cases into Xray from many kinds of source file. The user gives you a source, such as a spreadsheet or CSV export, a plaintext, Markdown or XML file, or test code like: Gherkin, Robot, pytest, RSpec, JUnit, Jest, NUnit, PHPUnit, Selenium, Cypress, or Playwright files. You read it and present the test cases you find, and once the user selects and confirms, you create those cases as Tests in an Xray project through the Xray MCP server. You never create or change anything in Xray until the user has reviewed the test cases and confirmed the import.

Xray runs on Jira Cloud, so every Test you create is a Jira issue in a Jira project, and the fields you fill are a mix of Xray's own (the Test Type and the test body) and plain Jira issue fields (the summary, the description, and the labels).

## Never edit this skill or its tooling during a run

This skill's own files are not yours to change while running the skill. Never edit, rewrite, or patch SKILL.md, or the bundled scripts (`scripts/check.py`, `scripts/parse_workbook.py`, `scripts/build_cases.py`) as a way to get an import to work. Treat them as fixed. If a script is having an issue, drops a column, duplicates content, or otherwise produces output you would rather change, create a copy of the script in a temporary location and modify it there.

---

## Your process

The skill works in two phases. The first phase is preparation and is read-only. You locate the source file, determine the Jira project with the user, parse the source file, build the candidate cases and work out the Test Type and field mapping they need, then capture the user's selection. The second phase creates the selected cases as Tests, along with any Test Repository folder they need, and reports what happened. Nothing is written to Xray until the user confirms the import in the second phase.

The step numbers and step names below are internal scaffolding for you, not a structure the user can see. Don't refer to numbered steps when communicating with the user, be that in prose or a header. Name the action in plain terms instead, for example say "later, when we place the Tests into a Test Repository folder" rather than "in Step 7". The cross-references between steps in this document are for your own navigation and must stay out of what you show the user.

### Step 1. Locate the source file

The invocation may carry arguments after the command, but only one of them is the source file. An argument is the source only when it resolves to a readable file or names an attached file. An argument that does not resolve to a file is not the source; it is a selection hint for the project, folder, or Test Type, so leave it for Step 2 and keep looking for the source here. So a bare word like `Regression` is a hint, not a missing file, and the search below still runs.

Work out which file to import, in this order:

1. If the user passed an argument that resolves to a readable file, or attached a file, use it as the source.
2. If the user named or attached a file earlier in the conversation, use that.
3. Otherwise, search the project root and its subfolders for likely source files. The search looks only for import-ready artifacts and test-native formats. Test code is imported by pointing the skill at the file or folder, as in the first two options above. Prefer the Glob tool when it is available in the session, with one `**/*.<ext>` pattern for each extension the search looks for: `.xlsx`, `.xls`, `.csv`, `.xml`, `.feature`, `.robot`, `.md`, `.txt`. Skip anything under a dot-directory or `node_modules`, and skip `README.md` and `CLAUDE.md` wherever they sit, since those are documentation rather than test cases. If Glob is not available, fall back to a read-only shell listing. If one clear candidate stands out, propose it. If several turn up, list them and ask which to use. Present the matches as a table with two columns, a running number and the path, built from the file list the search returned. Do not read the files without the user's approval. If more than 20 match, show the first 20, then note how many more there are and ask the user to narrow the search by path, pattern, or file type rather than printing the rest.
4. If nothing is found, ask the user for the path.

Confirm the file exists, then read it. If it reads as usable content, continue. If it cannot, because it is an encoded format with no decoder here or the text is gibberish, or some other problem, do not import it. Tell the user what happened and ask how they want to proceed.

### Step 2. Determine the Jira project

Before parsing, determine which Jira project the Tests are going into, and resolve any folder or Test Type the user hinted at when they invoked the skill. This step only reads from Xray, and it writes nothing.

The invocation may carry selection hints after the source, naming a project, a Test Repository folder, or a Test Type. A hint may be a strict id, and it may instead be a rough name: the wrong case, a shortened or partial word, or a small misspelling. So treat every hint leniently, and resolve it by matching it against the real entities Xray returns rather than trusting the text verbatim. Never act on a match on your own. Propose what you resolved and confirm it with the user before you use it, exactly as you confirm everything else in this skill.

Take the hints as a set, not as fixed positions. Position is at most a weak tiebreaker when several hints are present; what a hint is depends on what it matches. A folder and a Test Type exist only inside a project, so resolve the project first, then resolve the remaining hints against it.

#### Resolve the project

A project is confirmed by calling `get_project_settings` on it, which succeeds for a real project and fails for anything else. That tool takes the Jira project key, such as `CALC`, or the numeric Jira project id, such as `10033`, in the same `project_id_or_key` argument, so both forms of hint are checked the same way. Select the settings this skill needs, since they carry the whole of Step 5's Test Type and step information:

```
projectId testTypeSettings { defaultTestTypeId testTypes { id name kind } } testStepSettings { fields { id name type required disabled } }
```

If a hint looks like a Jira project key, or is a whole number, call `get_project_settings` on it. A successful call is the confirmation, so propose that project to the user along with what came back. A failed call means the hint names something else, so carry it forward to the folder and Test Type pass below.

With no hint resolving, the route depends on whether a Jira MCP server is connected to the session, so check the tools available to you first. Such a server varies in name but offers a project listing tool such as `getVisibleJiraProjects` or `jira_get_all_projects`, so check the session's deferred tools as well. With one connected, list the Jira projects and present them as a table of key and name to pick from, capping a long list the way the source file search does, then confirm the pick with `get_project_settings`. A Jira project can exist without Xray enabled on it, so when that call rejects the pick, say so and go back to the list.

With no Jira MCP server connected, say so, and that Xray exposes no tool that lists projects. Ask the user for the project key or id, noting they can connect a Jira MCP server first instead.

Do not try to discover the projects by reading Tests across the site. `get_tests` with no project filter returns Tests that each carry a `projectId`, but a project holding no Tests never appears in that result, so it can neither confirm a project nor rule one out.

Hold the whole `get_project_settings` result. Step 5 reads its Test Types and its step fields, Step 7 sends the project on every Test as the Jira project field, and the `projectId` scopes the folder read below.

#### Resolve the folder and Test Type hints

Once the project is settled, resolve any remaining hints against it. The Test Types are already in hand from `get_project_settings`, so they need no further call. A folder is read with `get_folder`, which returns the entire Test Repository subtree in one call, so read it once from the root and match against the tree it returns, selecting `name path testsCount folders`:

```
get_folder(path="/", project_id=<projectId>)
```

- A remaining string hint is matched leniently against both the folder names and paths and the Test Type names. Classify it by what it matches: a folder, a Test Type, or, when it plausibly matches both, ask which was meant. Propose the match and confirm. With no match in either, tell the user and ask rather than guessing.
- A remaining whole-number hint matches nothing here. A folder is addressed by its path, and a Test Type by an opaque string id such as `6a4f0fafc96011005a5b2352`, so neither is a number a user would type. Tell the user the number matched nothing and ask what they meant by it.
- A folder hint may name a folder that does not exist yet. When it matches nothing in the tree, propose it as a folder for Step 7 to create and confirm that is what they meant.
- Never invent a value from a hint that resolves to nothing. Surface it and move on.

Hold every entity that checks out. A confirmed Test Type lets Step 5 skip its Test Type table, and a confirmed folder lets Step 7 skip its find-or-create.

Once the project, and any hinted folder or Test Type, are settled, continue to parsing.

### Step 3. Parse the source file

How a source becomes content depends on its type. A spreadsheet or CSV goes through the bundled parser, which decodes the file into one grid JSON that Step 4 and `build_cases.py` read. Every other source is plain text you read directly with the Read tool, so there is no parser and no grid, and you extract its cases from the text in Step 4. Run the parser only for a spreadsheet or CSV.

The parser and the Step 7 assembler are plain Python scripts that read `.xlsx` and `.csv` with the standard library alone, so they need no installed packages and no virtual environment. They do need a Python interpreter, so first find one, then run the parser with it.

#### Find the Python interpreter

The command that runs Python is not the same on every platform, so find it with the bundled `scripts/check.py`. Run it under each candidate name in this order until one prints a line that begins `PYCHECK ok`:

```
python3 <skill-dir>/scripts/check.py
python <skill-dir>/scripts/check.py
py <skill-dir>/scripts/check.py
```

The `PYCHECK ok` line is the proof that name is a working interpreter here. A name that prints no such line is not usable, so move to the next. Remember the name that worked, written `<py>` below, and use that same command for every later script run in this skill, both the parser here and the assembler in Step 7. The line also reports the version and whether `xlrd` is present:

```
PYCHECK ok python=3.11.4 min=3.8 min_ok=yes xlrd=absent
```

Act on what the check reports:

- No candidate prints the line, so there is no usable Python here. Tell the user the skill needs Python to read spreadsheets and CSV, then offer to install it with their permission. Pick the command for their platform and ask before running it, since installing system software is their call:

  |    Platform     |         Detect         |                               Install command                               |
  | --------------- | ---------------------- | --------------------------------------------------------------------------- |
  | Debian / Ubuntu | `apt-get` present      | `sudo apt install python3`                                                  |
  | Fedora / RHEL   | `dnf` present          | `sudo dnf install python3`                                                  |
  | Arch            | `pacman` present       | `sudo pacman -S python`                                                     |
  | Alpine          | `apk` present          | `sudo apk add python3`                                                      |
  | macOS           | `uname` is `Darwin`    | `xcode-select --install`, or `brew install python` when Homebrew is present |
  | Windows         | `uname` starts `MINGW` | `winget install Python.Python.3`                                            |

  After the user installs it, run the check again. Install nothing without the user's agreement.
- `min_ok=no`, so the interpreter is older than the parser needs. Tell the user and ask them to install or point the skill at a newer Python, the same way, rather than running the parser on it.

#### Run the parser

For a `.csv` or `.xlsx` source, run the parser with the interpreter you found:

```
<py> <skill-dir>/scripts/parse_workbook.py "<source-file>"
```

For a legacy `.xls` source, the parser also needs the `xlrd` package, which the standard library cannot replace for that old binary format. If the check reported `xlrd=present`, run the parser exactly as above. If it reported `xlrd=absent`, offer to install `xlrd` for the same interpreter, with the user's permission, then run the parser:

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

- A flat table with one case per row under a header row. The header row is not always the first row, since a file may put a title or metadata block above it. Find the row whose cells read like column labels (for example Title, Steps, Expected Result), and treat the rows below it as cases.
- A flat table where each case spans several rows, grouped by a key column. The key, such as a case id or title, sits on the case's first row and is either blank on the rows that continue it or repeated on every row of the case. Gather the rows that share a key in order as one case, keeping each row's step paired with its expected result.
- A single case per sheet, laid out as label and value cells. Treat the whole sheet as one case and read its fields from the labelled cells.
- A report layout with a small header block followed by numbered steps. Treat the sheet as one case and keep the step rows in order as its steps.
- Sheets that hold no cases, such as Overview, Info, or Variables sheets and empty placeholders. Skip these.

When a flat table could be either of the two flat-table layouts above, read the key column down the data rows to decide: a blank under a filled key, or one key repeating while the step cells change, means the case spans rows. Group only on a column that identifies a single case. A column that repeats as a section or category label, with a distinct case in each row beneath it, is a folder grouping rather than a key, so grouping cases on it would merge separate cases.

A source you read directly has no grid or header row to find. Work from the document's own structure, its headings, scenarios, sections, or blocks, to see where one case starts and ends, and pull each case's title and body from the text. Skip parts that hold no case, such as a preamble or a shared setup block, unless that setup belongs to the cases as a precondition.

For each candidate, fill this normalized shape. It is the source's own shape, not Xray's, so keep every value as the source words it and leave the mapping to Step 5.

- `title` (required): the case name, from a title or name column, a labelled title cell, or the sheet name when the sheet is a single case. This becomes the Jira issue summary, the one field a Test cannot be created without.
- `preconditions` (optional): the setup the case needs before its steps run, kept as its own value rather than merged into the body. A precondition has two possible homes in Xray, its own Precondition issue or the Jira description, and Step 5 settles which, so keep the text intact and keep it separate here.
- `steps`, `expected` (optional): the case body, mapped from whichever columns or cells carry it. Preserve multi-line text. Keep numbered step rows as an ordered list, each with its action, any test data it names, and any expected result, so Step 5 can feed them to a Test's steps, to a Gherkin scenario, or to an unstructured definition. When a single cell holds several steps as a numbered or one-per-line list, treat each line as its own step rather than one block. When the cell is a single unbroken description, it stays one step. Keep a result that applies to the whole case separate from per-step results, since Xray places the two differently.
- `priority` (optional): the source's priority as written, carried for Step 5 to resolve against the Jira priority names the project uses.
- `type` (optional): the source's own notion of a case type, such as manual or automated, carried as evidence for the Test Type choice in Step 5 rather than as a per-case field. One import applies one Test Type to every Test it creates, so a source that mixes types is something to raise with the user.
- `references` (optional): any tracker ids or links the source carries. A Test has no references field. Step 5 decides between carrying them as labels or writing them into the description.
- `labels` (optional): carried whenever the source has them, and joined by `references` when Step 5 chooses labels as the home for those.
- `source`: where in the source the candidate came from, such as a sheet and row or a heading or line range, so the user can trace each one.
- `extras`: any other columns worth keeping, as name and value pairs.

Keep content faithful. Do not invent fields the source does not have, and do not paraphrase the case body into your own words. Non-English content stays as it is. Note any part of the source you could not interpret, so you can mention it when you present the candidates in Step 6.

Hold this normalized list of candidates for Step 5, where you resolve the Test Type and the field mapping. Do not present the candidates or ask the user to choose yet, and do not create anything in Xray.

### Step 5. Pick the Test Type and build the mapping

With the candidates built in Step 4, resolve the Test's fields here, before you present anything to the user.

A Test is a Jira issue carrying an Xray body. `create_test` takes the Jira issue fields under `jira.fields`, where `summary` is the only required one, and the body as exactly one of `steps`, `gherkin`, or `unstructured`. There are no custom fields on a Test, so every mapping target is either a Jira issue field or the one body. A Test using a Steps Test Type looks like this:

```json
{
  "jira": {
    "fields": {
      "summary": "Default Login",
      "project": {"key": "CALC"},
      "description": "Preconditions\n\nA registered account exists.",
      "priority": {"name": "Medium"},
      "labels": ["smoke", "regression"]
    }
  },
  "test_type": {"name": "Manual"},
  "folder_path": "/Login",
  "steps": [
    {"action": "Navigate to the login page", "data": "user@example.com", "result": "Login screen loads"},
    {"action": "Enter valid credentials", "result": "Logged in and redirected to the dashboard"}
  ]
}
```

`description` is a plain string, and its newlines survive as written, so pass source text through unchanged. `priority` goes as an object holding the Jira priority name, and `labels` as an array of strings.

#### Pick the Test Type

If a Test Type was resolved from the invocation hints and confirmed in Step 2, use it and skip the table below. Otherwise build the table from the `testTypeSettings` you already hold from Step 2, so this needs no further call. Show each Test Type's name, its `kind`, and whether it is the project's default, and rank them by fit.

What the `kind` decides is which body key the Test carries, and that is the whole of it:

| kind           | Body key       | What it holds                                       |
| -------------- | -------------- | --------------------------------------------------- |
| `Steps`        | `steps`        | An ordered array of step objects                    |
| `Gherkin`      | `gherkin`      | One scenario as plain text                          |
| `Unstructured` | `unstructured` | One free-text definition                            |

Rank by semantic fit first, reading the source file name and its structure, such as sheet and column names or headings and sections, for intent, then by structural fit, how cleanly the source's content maps onto that kind's body. A source carrying numbered steps with results fits `Steps`, a `.feature` file or Given-When-Then text fits `Gherkin`, and a free-form description with no step structure fits `Unstructured`. Mark one row as your recommendation and say in a sentence why.

Test Type names are set per project rather than by Xray, so read them from the project and never assume a name such as Manual, Cucumber, or Generic exists. More than one Test Type can share a kind, so when the kind you recommend has several types, show all of them and let the user choose between them, since nothing in the source can distinguish them.

Stop and wait for the user to explicitly pick the Test Type before going further. Do not proceed on your recommendation alone, and a selection of which cases to import is not a Test Type choice. The user may override your recommendation.

#### Map the Jira issue fields

Build the mapping against the Test Type the user selected.

- `title` goes to `jira.fields.summary`, the one field a Test cannot be created without.
- The project settled in Step 2 goes to `jira.fields.project`, as `{"key": "..."}` or `{"id": "..."}`.
- `description` is the only free-text field a Test carries, so it is where anything without its own home goes, each part labelled above its text so the user can tell them apart. That includes preconditions when the user chooses that strategy below, and references when they suit prose better than a label.
- `priority` resolves to a Jira priority name, sent as `{"name": "..."}`. Show the user your value-by-value mapping before writing, since the source wording rarely matches Jira's names. When a source value matches no priority, do not guess at a default, but either fit it where it clearly belongs or carry it as a label. Every distinct non-empty source value needs an entry, since the assembler treats an unmapped value as an error and stops rather than dropping it.
- `labels` is an array of strings. Jira rejects a label holding whitespace, so each label is normalized by replacing runs of whitespace with hyphens, which the assembler does on write. Show the user the normalized form rather than the source form, so the result is no surprise.
- `references` has no field of its own, since a Test carries nothing like a references or refs column. Carry them as labels when they are short tokens such as ticket keys, which keeps them filterable in Jira, or write them into the description when they are long or need surrounding words. Labels is the better default. The Xray MCP creates no Jira issue links, so a real link between issues is outside what this skill can do, and say so rather than implying the reference becomes a link.
- Note any source column with no target field.

#### Map the body

The body follows the kind of the Test Type the user picked, and a Test carries exactly one.

For a `Gherkin` kind, the scenario text goes to `gherkin` as it stands. For an `Unstructured` kind, the definition goes to `unstructured` the same way. Neither is split or restructured.

For a `Steps` kind, the step sub-columns come from the `testStepSettings` you hold from Step 2. A stock project offers `action`, which is required, plus `data` and `result`. Read them from the project rather than assuming those three, since a project can add step custom fields of its own. Decide here which source field feeds each sub-column, by matching the source's fields to the sub-columns by name and role, and fill a sub-column only where the source actually has per-step data for it. A value that applies to the whole case is not per-step data. The array position sets the step order, so there is no order field to map.

A project's own step custom fields are settable, by their `id` from `testStepSettings.fields`, but only when you build the call arguments yourself. The assembler emits `action`, `data`, and `result` and nothing else, so for a spreadsheet or CSV a step custom field cannot be filled. Tell the user that rather than mapping a column onto it.

A whole-case expected result has no case-level field to go to, since a Test carries none. A single result that applies to the case goes on the last step's `result`, which the assembler does through its `case_result` key. When a source carries per-step results and a separate whole-case result, ask the user which of the two to keep on the steps, and recommend the per-step results with the whole-case result going into the description.

#### Choose how preconditions are handled

A precondition in Xray is not a field on the Test. It is either its own Jira issue or part of the description, so when the candidates carry preconditions, put both strategies to the user and let them choose. Step 7 acts on the answer.

- Create Precondition issues. Group the candidates by exact precondition text, so one Precondition serves every Test sharing that text, and Step 7 creates each one with `create_precondition` and attaches it through `create_test`'s `precondition_issue_ids`. A Precondition must be the same Test Type as the Tests it attaches to, so this works only within one Test Type, which one import already is. The cost is extra Jira issues and one extra call per distinct text.
- Include the text in the Jira description. The precondition sits above the rest of the description under its own label, which the assembler covers through its `description_fields` key, so Step 7 makes no extra calls and creates no extra issues. The cost is that the text is not reusable and does not appear in Xray as a Precondition.

Recommend the first when the same precondition text repeats across cases, since that is where a shared Precondition earns its extra issue, and the second otherwise. The assembler has no precondition support either way, so the Precondition path is work Step 7 does around it rather than through it.

This mapping is a proposal. You present it for the user's agreement in Step 7 and apply nothing until then. Hold the chosen Test Type and the mapping for the next steps.

### Step 6. Present the candidates and get the selection

Show the user the candidates from Step 4 so they can decide what to import. This is the first time the user sees the candidate cases, and nothing has been written to Xray yet. Present them in their source form, faithful to the file, so the user can recognize and select cases. The Xray field mapping was resolved in Step 5 and is confirmed with the user in Step 7.

Present the candidates as a scannable index built only to support the selection, then show full per-candidate detail on request, or inline when the count is small (around three or fewer).

Open with a short count of how many cases were found and across how many sheets, files, or sections.

Build the index like this:

- Number every candidate in one running sequence across the whole source, so a range such as 1-8 is unambiguous.
- Cap the index at three or four columns so it never wraps in a terminal. Terminal width is the governing constraint, and the rules below all serve that cap.
- Use a single Content column that states quantities and what exists, for example "10 steps, expected" or "title only, no steps", instead of one boolean column per field.
- Group by the source's own divisions, a sheet, a file, or a section, with a labelled subheading per group when a group holds several cases, which lets you drop that column and keep the table narrow. When the source is many groups of one case each, use one table with a group column instead. Pick whichever is tighter.
- Show Priority, Type, or Labels columns only when the source actually has them. Never show an empty column.
- Put anything needing attention inline as a short token in the row, for example "no title" or "looks like run results", then repeat those tokens in a short notes list under the table. A token like that can be the reason a user excludes a candidate, so do not bury it.

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

Wait for an explicit selection. Do not create anything in Xray until the user has chosen. Once they answer, confirm the selected count back to them and carry that subset into Step 7.

### Step 7. Import the selected cases

This is the first step that writes to Xray, and it writes only after the user gives a final go. Work through it in order.

Any call here can time out, and a timeout does not tell you whether the write applied. Never retry a write blind, since that duplicates the issue. Reconcile against the project instead, and retry only what is genuinely missing. Never reconcile against the destination folder, which lags behind creation and reports a just-created issue as absent.

#### Confirm the mapping

Present the field mapping you built in Step 5 and get the user's explicit agreement before you build anything, since this is a confirmation step in its own right. Show the Test Type you picked and where each source field goes, the title to `summary`, the body to the Test Type's one body key, and priority and labels to their Jira fields. Show the labels in their normalized form, with whitespace replaced by hyphens. Show which strategy the preconditions are taking. Call out anything you combined into one field, any source field with no home, and any field left empty, so the user sees the whole shape and can correct it before anything is built. If they ask for changes, adjust the mapping and show it again.

#### Make sure the destination folder exists

The Test Repository folder must exist before any Test is created. `create_test` takes `folder_path` as a path rather than an id, and a path that matches no folder does not fail. The Test is created, filed at the root of the Test Repository, and the only sign is a string in the response's `warnings` array. So never rely on `folder_path` to create a folder.

- If a folder was resolved from the invocation hints and confirmed in Step 2, use it as the destination. When Step 2 confirmed it as a folder to be created, create it now.
- Otherwise reuse an existing folder when one fits, from the tree Step 2 read, or create one with `create_folder`, passing the `project_id` and the full path. Nesting is expressed in the path itself, such as `/R1 UX/Manual`, so there is no parent id to chase.
- Always pass `project_id` and never `test_plan_id`, since this skill files Tests in the project's Test Repository rather than in a Test Plan's own folder tree.

Select `folder { name path testsCount } warnings` on `create_folder`, and hold the destination path for the Tests.

#### Show the import plan

Show the user the plan and wait for an explicit go before any write. The plan states the Jira project, the destination folder path, the case count, the Test Type, the precondition strategy, and the number of calls the import will make, which is one `create_test` per Test plus one `create_precondition` per distinct precondition text. Xray creates one Test per call, so a large selection is a large number of round trips, many of which will time out and need reconciling. Say so plainly when the count is high, so the user can select fewer cases or cancel the import before anything is written. Do not write anything until the user confirms.

#### Assemble the call arguments

A spreadsheet or CSV goes through the bundled assembler covered here. A source you read directly is built from its candidates instead, as covered after the spec. For the assembler, write a mapping spec and run it with the interpreter you found in Step 3, written `<py>`:

```
<py> <skill-dir>/scripts/build_cases.py --parsed "<parsed-json-path>" --spec "<spec-path>"
```

The assembler uses only the standard library, so run it with that same interpreter whatever the source format. It reads the parsed JSON from Step 3, copies each cell's text into the arguments unchanged, and writes a `tests` array to a file whose path it prints, holding one complete `create_test` argument set per Test rather than one bulk body. Write the spec into the same scratch folder the parser wrote its JSON to in Step 3, the folder of the path it printed, since it belongs to this one run.

The spec is a JSON object that maps source columns onto a Test's fields, which the assembler executes row by row. This section documents the spec format in full, so you can build the spec entirely from it.

The keys are:

- `sheet` picks the source sheet, by 0-based index or `{"name": "..."}`. Defaults to the first sheet.
- `header_row` is the 0-based index of the column-label row. Defaults to 0, so set it when a title or metadata block sits above the labels.
- `select_rows` carries the user's selection as 1-based case numbers, or "all".
- `project` is the Jira project every Test is created in, as `{"key": "..."}` or `{"id": "..."}`, and `summary_column` supplies the required Jira issue summary.
- `test_type` applies one Test Type to every Test, as `{"name": "..."}` or `{"id": "..."}`, and `folder_path` applies one Test Repository path to every Test.
- `group_column`, for a sheet whose cases span several rows, names the key column that gathers those rows into one case, so the assembler groups them the way you presented them. Leave it out for one-case-per-row sheets.
- `description_fields` lists the source columns that make up the Jira description, each with an optional label above its text. The parts join with a blank line, empty parts are dropped, and a value repeated down the rows of one case appears once.
- `priority` maps a source column through a `value_map` to a Jira priority name. A non-empty value with no entry in the map stops the assembler, so give every distinct value an entry.
- `labels_columns` names the columns whose values become Jira labels, splitting a column on a separator when asked, normalizing each label to the whitespace-free form Jira requires, and dropping duplicates.
- `steps` fills a Steps kind Test's body. It maps each source column to a step sub-column, one of `action`, `data`, or `result`, then turns each row of the case into one step object, with the array position setting the step order. A row that is empty across every mapped column is skipped. When a case instead holds its steps as a numbered or one-per-line list inside a single cell, mark that column `"split": true` so the cell expands into one step per line, with any leading enumerator stripped.
- `case_result` names the column holding one expected result that applies to the whole case rather than to a single step. The assembler builds the steps, then puts that value on the last step's `result`. It requires `steps`, and it is rejected alongside a `result` sub-column, since a case is one shape or the other.
- `gherkin_column` names the column holding a Gherkin kind Test's scenario, and `unstructured_column` the column holding an Unstructured kind Test's definition.

A Test carries one body, so `steps`, `gherkin_column`, and `unstructured_column` are mutually exclusive.

A spec exercising the Steps path looks like this. Here a `Login` sheet has its labels on the third row, its cases span several rows gathered by `Case ID`, each case gives one expected result for the whole case, and the user picked cases 1, 2, and 5:

```json
{
  "sheet": {"name": "Login"},
  "header_row": 2,
  "select_rows": [1, 2, 5],
  "project": {"key": "CALC"},
  "summary_column": "Title",
  "test_type": {"name": "Manual"},
  "folder_path": "/Login",
  "group_column": "Case ID",
  "description_fields": [
    {"column": "Preconditions", "label": "Preconditions"},
    {"column": "Notes", "label": "Notes"}
  ],
  "priority": {
    "column": "Priority",
    "value_map": {"High": "High", "Med": "Medium", "Low": "Low"}
  },
  "labels_columns": [
    {"column": "Labels", "split": ","},
    {"column": "References", "split": ","}
  ],
  "steps": {
    "columns": [
      {"column": "Step", "sub": "action"},
      {"column": "Test Data", "sub": "data"}
    ]
  },
  "case_result": {"column": "Expected Result"}
}
```

Drop the keys a given source does not need. A one-case-per-row sheet omits `group_column`, a Gherkin or Unstructured Test Type carries `gherkin_column` or `unstructured_column` in place of `steps`, and a sheet whose labels are already on the first row omits `header_row`. A source that gives a result per step instead adds a `result` sub-column inside `steps` and leaves out `case_result`.

The assembler covers flat-table sources, whether each candidate is one row or several rows gathered by a `group_column`. Everything else you build directly from the candidates, keeping the same argument shape as the example in Step 5. That covers the single-case grid layouts in Step 4, a label and value sheet or a report sheet, and every source you read directly.

#### Create the Preconditions, when that is the strategy

When Step 5 settled on shared Precondition issues, create them before the Tests, since `create_test` takes their issue ids.

- Group the selected candidates by exact precondition text, so one Precondition serves every Test that shares it.
- Create each one with `create_precondition`, passing a `jira` object with a `summary` and the project, the `definition` holding the precondition text, and a `precondition_type` matching the Test Type the Tests use. Leave `test_issue_ids` out, since the association is made from the Test side.
- Pass the destination folder as `folder_path` as well, so the Preconditions sit alongside the Tests they belong to rather than unfiled at the root of the Test Repository.
- Select `precondition { issueId definition preconditionType { name kind } } warnings`, and hold each `issueId` against the candidates it belongs to.
- A timed-out `create_precondition` leaves you without its `issueId`, so reconcile with `get_preconditions` before attaching anything to a Test.
- Add those ids to the matching Tests as `precondition_issue_ids`. The assembler does not emit that key, so add it to the argument sets it produced before sending them.

When Step 5 settled on the description instead, there is nothing to do here, since `description_fields` already carried the text.

#### Create the Tests

Read the arguments the assembler wrote, then call `create_test` once per Test. There is no bulk create, so each call is one Test succeeding or failing on its own. Select this on every call:

```
test { issueId testType { name kind } jira(fields: ["key"]) } warnings
```

Read the `warnings` array on every response. A Test can be created with a warning rather than an error, and the warning is how Xray reports that the Test did not go where the arguments said. A non-empty `warnings` on any Test means that Test is not in the destination folder, so hold it for Step 8 to report rather than counting it as placed.

Keep a running tally as you go, holding each Test's new `issueId` and Jira key against the candidate it came from, along with any failure and its error. Step 8 reports from that tally.

A timed-out `create_test` returns no `warnings` either, so that Test's placement is unknown too. Once every call is made, reconcile in one pass with `get_tests` on a JQL matching the expected summaries, selecting `folder { path }` with the keys. If a duplicate does appear, report it in Step 8 so the user can decide whether to delete it.

### Step 8. Verify and report

Report from the tally Step 7 kept, then check what Xray stored.

Every `create_test` call returned its own result, so the report is per Test. Tell the user:

- the destination Jira project and Test Repository folder path.
- the count created, with each Test's summary, its new Jira key, and its `issueId`.
- any Test that failed, with the error Xray returned.
- any Test whose response carried a non-empty `warnings` array, since that Test was created but is not in the destination folder.

Never silently skip a case. Say which cases were created and which were not, so the user can decide whether to retry the rest.

A Test that came back with a warning is sitting at the root of the Test Repository. Offer to move them, which takes one call for the whole set rather than one per Test, once the folder they were meant for exists:

```
add_tests_to_folder(path="<destination>", test_issue_ids=[...], project_id=<projectId>)
```

Select `folder { name path testsCount } warnings` on it, and report the result the same way.

Then spot check what Xray holds, with two reads:

- The folder-scoped count. Call `get_tests` with `folder={"path": "<destination>", "includeDescendants": false}` and the `project_id`, selecting `total` on its own, and confirm it equals the folder's count before the import plus the number created. Never select `results`, and never page.
- The content. Call `get_test` on one Test per distinct shape you created, so every shape is checked at least once, selecting the body key that matches the Test Type's kind:

```
issueId jira(fields: ["key", "summary"]) testType { name kind } folder { path } steps { action data result }
```

Replace `steps { action data result }` with `gherkin` or `unstructured` for those kinds. Confirm the body persisted and the folder path is the destination.

Do not use `get_test_count` for this. It counts the Tests in the whole site and takes no arguments, so it says nothing about one import.

If everything matches, say so and stop there. If it does not, report the discrepancy to the user, such as a wrong count, a Test in the wrong folder, or a body field that did not survive, and let them decide what to do next.
