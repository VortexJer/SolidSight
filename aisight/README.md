# aisight

Both ends of the family in one command. The five tools are independent
on purpose — install one, some or all, none depends on another — but
nothing knew about all of them at once, which is what you want on the
first day and on the last one.

```bash
pip install aisight   # brings in all five tools

aisight status        # what is installed on this machine
aisight uninstall     # the skills, the packages, the plugin marketplace
```

`pip install aisight` installs solidsight, animationsight, texturesight,
shadersight and pcbsight — solidsight's dependencies included, so it is
the heaviest way in. Want one tool? `pip install solidsight`.

## What it removes

| leftover | where | removed |
|---|---|---|
| skill | `~/.claude/skills/<tool>/` | yes |
| package | the pip distribution | yes (`--keep-packages` to keep) |
| plugin | `~/.claude/plugins/marketplaces/aisight/` + its registry entry | yes, only ours |
| checkout | a `git clone` of the repo | **only if you point at it** |

A checkout is yours, not ours, so it is never guessed. `--repo PATH`
deletes one — and only after checking the directory really is an AISight
working copy (`.claude-plugin/marketplace.json` naming this marketplace,
plus all five tool folders). A wrong path there would delete somebody's
work, so "looks about right" is not good enough.

```bash
aisight uninstall --dry-run                  # print the list, touch nothing
aisight uninstall --only solidsight          # one tool, keep the rest
aisight uninstall --repo ~/code/AISight -y   # everything, checkout included
```

`--only` never touches the plugin marketplace or a checkout: those belong
to the family, not to one tool. Each tool also keeps its own
`<tool> uninstall`, which removes that tool's skill and package.

Uninstalling everything removes `aisight` itself, last.
