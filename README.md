# Sembi IQ — Agent skills

Agent-agnostic skills for the [TestRail](https://www.testrail.com/), [Testmo](https://www.testmo.com/), and [Xray](https://www.getxray.app/) test-management platforms — for any agent that supports the [Agent Skills](https://agentskills.io/specification) convention.

Test-driven workflows, one skill each, backed by the Testmo, TestRail, or Xray MCP server:

- **`spec-implementer`** — implement a feature whose acceptance criteria already exist as test cases. Reads the live cases and writes code that satisfies every one.
- **`regression-preventer`** — guard new or in-progress code against breaking behavior that existing test cases already protect. Works out what the change can reach, reads the cases guarding it, and presents a guard rail brief for your confirmation before writing or repairing any code. Xray only.
- **`change-evaluator`** — predict whether recent code changes will make test cases pass or fail, before running the suite.
- **`import`** — import test cases from a spreadsheet, CSV, Markdown, XML, plaintext, or test code into the platform. Presents what it found for review and writes nothing until you confirm. Testmo and TestRail only.

## Using Claude

If your agent is Claude (Claude Code, Claude Desktop, or Claude on the web), install the Claude plugins instead — they add slash commands and a subagent on top of these skills in a Claude specific manner. See [`sembi-iq-plugins`](https://github.com/SembiIQ/sembi-iq-plugins).

## Prerequisites

### Configure the Sembi MCP Server

These skills call the remote Sembi MCP server's tools, so you must have the matching server connected — **Testmo** for the Testmo skills, **TestRail** for the TestRail skills, **Xray** for the Xray skills.

**For TestRail**, follow the MCP connection steps at: [https://testrail.sembi.com/](https://testrail.sembi.com/)

**For Testmo**, follow the MCP connection steps at: [https://testmo.sembi.com/](https://testmo.sembi.com/)

**For Xray**, follow the MCP connection steps at: [https://xray.sembi.com/](https://xray.sembi.com/)

> [!IMPORTANT]
> If the MCP server isn't connected, the skills will reference tools that aren't available.

The `spec-implementer`, `regression-preventer`, and `change-evaluator` skills only read, so a read-only connection is enough for them. The **`import` skill creates cases and folders**, so it needs a connection with write access.

### Git

Installation uses [git](https://git-scm.com/), which must be installed and available.

### Python — for Excel and CSV imports only

The `import` skill needs a Python interpreter on the `PATH` **when importing Excel or CSV**, because it runs bundled scripts to parse those formats. Markdown, XML, plaintext, and test-code sources are read directly, and need no Python. Where it is needed, the skill probes for it (`python3`, then `python`, then `py`); if none is found it offers to install Python for your platform, with your permission.

No packages and no virtual environment are needed — `.xlsx` and `.csv` are read with the standard library alone. Legacy `.xls` is the one exception, needing the pure-Python `xlrd` package, which the skill installs only if and when an `.xls` source actually appears.

The `spec-implementer`, `regression-preventer`, and `change-evaluator` skills need no Python at all.

## Installation

To install, run one of the commands below. Each clones the repo to `~/.sembi-iq-skills`, then copies that product's skills into the cross-client `~/.agents/skills/` convention.

Agents look for skills as direct children of `~/.agents/skills/` — Zed states this explicitly — so the skills are copied rather than left nested under the clone.

> [!IMPORTANT]
> The commands below are written for a Bash or Z shell — run them in **Terminal on macOS/Linux**, or in **Git Bash on Windows** (installed with Git for Windows). **They won't run as-is in Windows CMD or PowerShell.**

### TestRail

**For TestRail**, run the following command:

```zsh
git clone --filter=blob:none --sparse https://github.com/SembiIQ/sembi-iq-skills.git ~/.sembi-iq-skills \
  && git -C ~/.sembi-iq-skills sparse-checkout set testrail \
  && mkdir -p ~/.agents/skills \
  && cp -R ~/.sembi-iq-skills/testrail/* ~/.agents/skills/
```

This results in the following layout on your file system:

```
~/.agents/skills/
├── testrail-spec-implementer/SKILL.md
├── testrail-change-evaluator/SKILL.md
└── testrail-import/
    ├── SKILL.md
    └── scripts/
```

### Testmo

**For Testmo**, run the following command:

```zsh
git clone --filter=blob:none --sparse https://github.com/SembiIQ/sembi-iq-skills.git ~/.sembi-iq-skills \
  && git -C ~/.sembi-iq-skills sparse-checkout set testmo \
  && mkdir -p ~/.agents/skills \
  && cp -R ~/.sembi-iq-skills/testmo/* ~/.agents/skills/
```

This results in the following layout on your file system:

```
~/.agents/skills/
├── testmo-spec-implementer/SKILL.md
├── testmo-change-evaluator/SKILL.md
└── testmo-import/
    ├── SKILL.md
    └── scripts/
```

### Xray

**For Xray**, run the following command:

```zsh
git clone --filter=blob:none --sparse https://github.com/SembiIQ/sembi-iq-skills.git ~/.sembi-iq-skills \
  && git -C ~/.sembi-iq-skills sparse-checkout set xray \
  && mkdir -p ~/.agents/skills \
  && cp -R ~/.sembi-iq-skills/xray/* ~/.agents/skills/
```

This results in the following layout on your file system:

```
~/.agents/skills/
├── xray-spec-implementer/SKILL.md
├── xray-regression-preventer/SKILL.md
└── xray-change-evaluator/SKILL.md
```

### Updates

Check for updates at any time later by pulling and re-copying — substitute the product you installed:

```zsh
git -C ~/.sembi-iq-skills pull && cp -R ~/.sembi-iq-skills/testrail/* ~/.agents/skills/
```

## Usage

Skills are auto-activated by the agent when a task matches the skill's description (the Agent Skills progressive-disclosure model); some agents also let you reference a skill by name, often with a slash command. Refer to the agent skills documentation for the specific details on directly invoking skills.

The `import` skills are the exception — they are marked user-invoked only, so ask for one by name rather than expecting it to activate on its own.

### TestRail

| Skill                       | What it does                                           |
|-----------------------------|--------------------------------------------------------|
| `testrail-spec-implementer` | Implement a feature from TestRail test cases           |
| `testrail-change-evaluator` | Predict pass/fail of TestRail cases for recent changes |
| `testrail-import`           | Import test cases from a source file into TestRail     |

### Testmo

| Skill                      | What it does                                         |
|----------------------------|------------------------------------------------------|
| `testmo-spec-implementer`  | Implement a feature from Testmo test cases           |
| `testmo-change-evaluator`  | Predict pass/fail of Testmo cases for recent changes |
| `testmo-import`            | Import test cases from a source file into Testmo     |

### Xray

| Skill                       | What it does                                       |
|-----------------------------|----------------------------------------------------|
| `xray-spec-implementer`     | Implement a feature from Xray Tests                |
| `xray-regression-preventer` | Guard changes against breaking existing Xray Tests |
| `xray-change-evaluator`     | Predict pass/fail of Xray Tests for recent changes |
