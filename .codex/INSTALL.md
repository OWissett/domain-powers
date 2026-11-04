# Install domain-powers in Codex

Requires superpowers and Python 3.11+ on the machine running the guard. Keep the
complete repository layout: the skills use shared scripts and reviewer instructions.

## Codex desktop plugin

The Codex compatibility manifest declares all nine skills and a dedicated hook
configuration. From a committed checkout, create an archive with the plugin files
at its root:

```bash
git archive --format=zip --output=/tmp/domain-powers-codex.zip HEAD \
  .codex-plugin .codex skills scripts hooks agents README.md
```

Install that archive through Codex desktop's manual plugin installation, enable
the plugin, and review and trust its hook definitions. Start a new chat after
installation. Installing skills alone does not enable hooks.

Codex supports manually installed plugin hooks and requires explicit trust before
running them ([official packaging documentation](https://developers.openai.com/plugins/build/plugins)).

The startup hook supplies the domain-powers routing table. During design work,
the agent uses that table to load modeling-the-domain and
defining-documentation-language alongside superpowers brainstorming. This pairing
is an agent instruction, not a deterministic hook on skill loading: Codex has no
Claude `Skill` event. The edit guard checks native patch calls after execution;
it reports findings but cannot undo an edit. Shell writes require a manual scan.

Codex passes patch text in `tool_input.command` with the canonical tool name
`apply_patch`, including when an Edit/Write matcher selects it
([official hook documentation](https://learn.chatgpt.com/docs/hooks)).

## Skills-only installation

For Codex without trusted plugin hooks, clone outside your project and link the
skills directory into the user skill discovery directory:

```bash
git clone git@github.com:OWissett/domain-powers.git ~/.agents/domain-powers
mkdir -p ~/.agents/skills
ln -s ~/.agents/domain-powers/skills ~/.agents/skills/domain-powers
```

Select your SSH identity through your existing SSH configuration or a per-command
`GIT_SSH_COMMAND`. These commands do not edit SSH or GitHub CLI authentication.
If a destination exists, inspect it rather than overwriting it. Avoid duplicate
copies of the skills in other discovery directories.

Codex discovers user skills under `~/.agents/skills` and follows skill-directory
symlinks ([official skill documentation](https://learn.chatgpt.com/docs/build-skills)).

Start a new chat, invoke `$using-domain-powers`, and have it read the Codex reference
before design work. Skill descriptions allow automatic selection, but this mode
does not inject startup instructions or run lifecycle hooks. Run the guard
explicitly after edits and at verification:

```bash
python3 ~/.agents/domain-powers/scripts/domain_guard.py --scan src docs README.md
```

## Update and uninstall

For skills-only installation, run `git -C ~/.agents/domain-powers pull --ff-only`;
the discovery link follows the updated files. Start a new chat to reload them.
For a desktop plugin, build and install an archive from the desired committed
revision and review any changed hook definition before trusting it.

To uninstall skills-only discovery, remove only the symlink you created. Keep the
checkout if it contains local changes. For a desktop plugin, use Codex's plugin
uninstall control. Neither path requires changing your authentication.
