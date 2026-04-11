# Claude Code Skills for Querri

Pre-built [Claude Code skills](https://docs.anthropic.com/en/docs/claude-code/skills) for working with the Querri platform.

## Available Skills

| Skill | Description |
|-------|-------------|
| [querri-cli](querri-cli/) | Interact with the Querri data analysis platform via the `querri` CLI — projects, files, chat, dashboards, sharing, and more. |

## Installation

Copy or symlink the skill folder into your Claude Code skills directory:

```bash
# Option 1: Symlink (recommended — stays in sync with SDK updates)
ln -s "$(pwd)/skills/querri-cli" ~/.claude/skills/querri-cli

# Option 2: Copy
cp -r skills/querri-cli ~/.claude/skills/querri-cli
```

After installation, Claude Code will automatically detect and use the skill when you ask it to perform Querri CLI operations.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
- The `querri` CLI installed (`pip install querri`) and authenticated (`querri auth login`)
