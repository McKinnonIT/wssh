# wssh

SSH to [Warpgate](https://github.com/warp-tech/warpgate) targets from your terminal — interactive setup, tab completion, and optional server bootstrap.

```bash
wssh dns01
```

## Requirements

- Python 3.10+
- OpenSSH (`ssh`, `ssh-keygen`)
- [pipx](https://pipx.pypa.io/) — the installer sets it up if missing

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/McKinnonIT/wssh/main/install.sh | bash
wssh setup
```

The installer adds Python, pipx, and OpenSSH where they are missing (Homebrew, apt, or dnf), then installs `wssh` with pipx. Set `WSSH_REPO` to install from a fork.

From a clone instead:

```bash
git clone https://github.com/McKinnonIT/wssh.git
cd wssh
pipx install .
wssh setup
```

`wssh setup` asks for your Warpgate host, username, and SSH key, signs you in, and installs shell tab completion. Settings are saved to `~/.wssh/config.yaml` (mode `0600`).

## Usage

```bash
wssh dns01                              # open a shell on the target
wssh dns01 -- systemctl status nginx    # run a remote command
wssh dns01 -L 8080:localhost:80         # arguments pass through to ssh
```

Copy files with target names in place of hostnames:

```bash
wssh scp ./notes.txt dns01:~/           # up
wssh scp -r dns01:/etc/nginx .          # down, options pass through to scp
wssh scp docker04:~/file.txt docker02:~/  # target to target
```

Warpgate picks the target from the SSH username, so one `scp` can reach exactly one
target — a target-to-target copy runs as two copies staged on your local disk. If the
pull half is incomplete (`-r` over a tree with unreadable files), wssh pushes what did
copy, says so, and exits non-zero: the destination is left partial, not empty.

For a tree wssh cannot read in full, stream it as root instead — one pass, permissions
and ownership intact:

```bash
wssh docker02 -- sudo tar -czf - -C /apps guacamole-ap \
  | wssh docker04 -- sudo tar -xzf - -C /apps
```

Target names tab-complete once setup has run. Anything that is not a known subcommand is treated as a target name.

Misspelled names get a suggestion instead of a failed connection:

```
$ wssh pangoli
No target pangoli in Warpgate.
Did you mean pangolin01? [y/n] (y):
```

If a connection fails, `wssh` checks whether the target exists in Warpgate, whether your account can reach it, and offers to fix role access or run `setup-server`. When stdin is not a terminal, these prompts are skipped so scripted use never blocks.

## Commands

| Command | Purpose |
|---------|---------|
| `wssh <target> [args…]` | Connect to a target; remaining arguments go to `ssh` |
| `wssh setup` | First-time setup: host, username, SSH key, sign-in, completion |
| `wssh setup-server <name>` | Install Warpgate client keys on a server and register it as a target |
| `wssh scp [opts] SRC… DST` | Copy files using `target:path`; remaining options go to `scp` |
| `wssh auth login` | Sign in and store an API token |
| `wssh auth logout` | Remove the stored API token |
| `wssh targets list` | List SSH targets you can access |
| `wssh targets refresh` | Refresh the local target cache |
| `wssh credentials add-key` | Upload your SSH public key to Warpgate |
| `wssh completion bash\|zsh` | Print the completion script |
| `wssh update` | Install the latest version from GitHub, if there is one |
| `wssh update --check` | Report whether an update is available, without installing |
| `wssh version` | Show the installed commit, and check for an update |
| `wssh config-path` | Print the active config file path |

Useful options:

| Option | Applies to | Purpose |
|--------|-----------|---------|
| `--config <path>` | any command | Use a different config file |
| `--dry-run`, `-n` | `setup`, `setup-server` | Show what would change without doing it |
| `--manual-credentials` | `setup` | Paste the SSH key in the Warpgate UI instead of uploading via API |
| `--skip-auth` | `setup` | Skip the sign-in step |
| `--token <token>` | `auth login` | Store a token you already have |
| `--force`, `-f` | `targets list` | Refresh from the API instead of the cache |
| `--force`, `-f` | `update` | Reinstall even when already up to date |
| `--check` | `update` | Report update status without installing |
| `--cache-only` | `targets list` | Never hit the API (used by completion) |
| `--key <path>`, `--label <str>` | `credentials add-key` | Choose which public key to upload, and its label |

Targets are cached under `~/.wssh/cache/` for 24 hours so completion stays fast; `wssh targets refresh` updates it early.

## Staying up to date

`wssh` tells you when the repo has moved on, after the command finishes:

```
Update available (2db85ba → 5c019d5) — run wssh update
```

Then `wssh update` installs it, via `pipx` when it is on PATH and `pip` into the current interpreter otherwise. It compares first and does nothing when there is nothing to get:

```console
$ wssh update
Already up to date (26665e7)
Nothing to install — use --force to reinstall anyway.
```

`--force` reinstalls regardless, for a venv that needs rebuilding. If the remote cannot be reached, or the copy was not installed from git, there is nothing to compare and the install runs — you asked for it, and `ls-remote`'s short timeout can fail on a link a clone survives.

To ask directly:

```console
$ wssh version
e0a0d9d
Up to date
```

**A commit is the version here.** `wssh` is not released or tagged, and the version in `pyproject.toml` has been `0.1.0` since the first commit — so `wssh version` prints the commit `pip` recorded and nothing else. (`pipx list` still shows `0.1.0`, because a wheel needs some version; it means nothing. It is also why `wssh update` has to force the reinstall — pip cannot tell two builds apart.)

An install that did not come from git prints `unknown`, since there is no commit to name.

`wssh version` checks live rather than reading the cache, since you are asking right now. Piped (`wssh version | …`) it prints the commit alone and makes no network call, so scripts stay fast.

The check compares the commit `pip` recorded for your install against `git ls-remote` on the repo. Because two commits cannot be ordered without a local clone, a copy installed from a branch that is *ahead* of `main` also reports an update — both short commits are always shown so you can tell.

| Behaviour | |
|---|---|
| Frequency | Network is touched once per 24 hours; the result is cached in `~/.wssh/cache/update.json` |
| Output | stderr only, and only when stderr is a terminal — piping stays clean |
| Failure | Offline, no `git`, or no repo access means no notice, never an error or a delay |
| Not a git install | Silent, since there is no commit to compare |
| Opt out | `WSSH_NO_UPDATE_CHECK=1` silences the notice and the `wssh version` check. `wssh update --check` ignores it — checking is that command's whole purpose |

## Configuration

Config file: `~/.wssh/config.yaml`.

```yaml
user: alice@example.com          # your Warpgate account
host: bastion.example.com        # bastion, SSH and HTTPS
port: 2222                       # Warpgate SSH port
domain: example.com              # optional: appended to usernames without @
server_domain: internal.example.com  # optional: DNS suffix for short server names
api_token: "<your-api-token>"
default_ssh_user: root           # defaults used by setup-server
default_ssh_port: 22
```

Environment variables override file values:

| Variable | Purpose |
|----------|---------|
| `WSSH_CONFIG` | Path to the config file |
| `WSSH_HOST` | Warpgate bastion hostname |
| `WSSH_PORT` | Warpgate SSH port (default `2222`) |
| `WSSH_DOMAIN` | Append to usernames without `@` |
| `WSSH_SERVER_DOMAIN` | DNS suffix for `wssh setup-server` short names |
| `WSSH_API_TOKEN` | User API token |
| `WSSH_ADMIN_API_TOKEN` | Admin API token (for `setup-server`; falls back to `WSSH_API_TOKEN`) |
| `WSSH_WARPGATE_CLIENT_KEYS` | Newline-separated client public keys (offline bootstrap) |
| `WSSH_REPO` | Git repo `wssh update` and `install.sh` pull from |
| `WSSH_NO_UPDATE_CHECK` | Silence the update notice and the `wssh version` check |
| `WSSH_TERM` | TERM sent to hosts that lack your terminal's terminfo (Ghostty, Kitty). Default `xterm-256color`; set empty to send your real TERM |

See [`config.example.yaml`](config.example.yaml) for a commented template.

## Organization presets

Teams can ship **non-secret** defaults (bastion host, email domain, server DNS suffix, default SSH user) without forking `wssh`:

1. Maintain a partial config — see the preset note in [`config.example.yaml`](config.example.yaml). No `api_token`, `admin_api_token`, or per-user `user`.
2. Install `wssh` and copy the preset to `~/.wssh/config.yaml`.
3. Run `wssh setup` — connection prompts are skipped when `host` is already set, so staff only complete username, SSH key, sign-in, and completion.

Distribute the preset via a private repo and bootstrap script, MDM, or internal wiki. Keep secrets and personal tokens out of shared files.

## Troubleshooting

**Sign-in.** `wssh auth login` opens the Warpgate login page and waits for you to press Enter. It then tries to create an API token automatically; if it cannot, it asks you to paste one from **Profile → API Tokens**.

Automatic token creation needs an optional dependency:

```bash
pipx inject wssh browser-cookie3
```

**Completion not working.** Make sure the block `wssh setup` added to your rc file is after `compinit` in `.zshrc`, then start a new shell. Re-running `wssh setup` replaces the block rather than stacking a second one.

**`wssh` not found after install.** pipx installs to `~/.local/bin`:

```bash
export PATH="$HOME/.local/bin:$PATH"    # add to your rc file
```

**Key rejected.** Warpgate matches public keys on `<algorithm> <base64>` with no trailing comment. A key uploaded with a comment never authenticates — `wssh credentials add-key` strips it, and reports when an existing entry was stored in the wrong format.

**Uploading your key by hand:**

```bash
wssh setup --manual-credentials
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest
.venv/bin/ruff check src tests
```

Lint settings live in `pyproject.toml`. `B008` is ignored because `typer.Option()` in an argument default is how Typer is written.

## License

MIT — see [LICENSE](LICENSE).
