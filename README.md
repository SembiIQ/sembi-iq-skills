# Sembi IQ — Agent skills

Agent-agnostic skills for the [TestRail](https://www.testrail.com/) and [Testmo](https://www.testmo.com/) test-management platforms — for any agent that supports the [Agent Skills](https://agentskills.io/specification) convention.

Two test-driven workflows, one skill each, backed by the Testmo or TestRail MCP server:

- **`spec-implementer`** — implement a feature whose acceptance criteria already exist as test cases. Reads the live cases and writes code that satisfies every one.
- **`change-evaluator`** — predict whether recent code changes will make test cases pass or fail, before running the suite.

## Using Claude

If your agent is Claude (Claude Code, Claude Desktop, or Claude on the web), install the Claude plugins instead — they add slash commands and a subagent on top of these skills in a Claude specific manner. See [`sembi-iq-plugins`](https://github.com/SembiIQ/sembi-iq-plugins).

## Prerequisites

### Configure the Sembi MCP Server

These skills call the remote Sembi MCP server's tools, so you must have the matching server connected — **Testmo** for the Testmo skills, **TestRail** for the TestRail skills. (Each skill records this in its `compatibility` field.)

**For TestRail**, follow the MCP connection steps at: [https://testrail.sembi.com/](https://testrail.sembi.com/)

**For Testmo**, follow the MCP connection steps at: [https://testmo.sembi.com/](https://testmo.sembi.com/)

> [!IMPORTANT]
> If the MCP server isn't connected, the skills will reference tools that aren't available.

### Git

Installation uses [git](https://git-scm.com/), which must be installed and available.

## Installation

To install, run git clone into the cross-client `~/.agents/skills/` convention using one of the commands below.

> [!IMPORTANT]
> The commands below are written for a **Bash** or **Z shell** — run them in **Terminal** on macOS/Linux, or in **Git Bash** on Windows (installed with Git for Windows). They won't run as-is in Windows CMD or PowerShell.

### TestRail

**For TestRail**, run the following command:

```zsh
git clone --filter=blob:none --sparse git@github.com:SembiIQ/sembi-iq-skills.git ~/.agents/skills/sembi-iq \
  && git -C ~/.agents/skills/sembi-iq sparse-checkout set testrail
```

This results in the following layout on your file system:

```
~/.agents/skills/sembi-iq/
└── testrail/
    ├── testrail-spec-implementer/SKILL.md
    └── testrail-change-evaluator/SKILL.md
```

### Testmo

**For Testmo**, run the following command:

```zsh
git clone --filter=blob:none --sparse git@github.com:SembiIQ/sembi-iq-skills.git ~/.agents/skills/sembi-iq \
  && git -C ~/.agents/skills/sembi-iq sparse-checkout set testmo
```

This results in the following layout on your file system:

```
~/.agents/skills/sembi-iq/
└── testmo/
    ├── testmo-spec-implementer/SKILL.md
    └── testmo-change-evaluator/SKILL.md
```

### Updates

Check for updates at any time later by running:

```zsh
git -C ~/.agents/skills/sembi-iq pull
```

## Usage

Skills are auto-activated by the agent when a task matches the skill's description (the Agent Skills progressive-disclosure model); some agents also let you reference a skill by name, often with a slash command. Refer to the agent skills documentation for the specific details on directly invoking skills.

### TestRail

| Skill                       | What it does                                           |
|-----------------------------|--------------------------------------------------------|
| `testrail-spec-implementer` | Implement a feature from TestRail test cases           |
| `testrail-change-evaluator` | Predict pass/fail of TestRail cases for recent changes |

### Testmo

| Skill                      | What it does                                         |
|----------------------------|------------------------------------------------------|
| `testmo-spec-implementer`  | Implement a feature from Testmo test cases           |
| `testmo-change-evaluator`  | Predict pass/fail of Testmo cases for recent changes |
