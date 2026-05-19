# wssh

McKinnon Warpgate SSH client — setup, connect, tab completion, and on-demand server bootstrap.

## Install

```bash
git clone https://github.com/McKinnonIT/wssh.git
cd wssh

# Recommended: isolated install
pipx install .

# Or install into the current environment
pip install .

# Quick bootstrap (installs the package then runs setup)
./wssh-setup.sh
```

Requires Python 3.10+ and OpenSSH (`ssh`, `ssh-keygen`).

Optional: `pip install 'wssh[cookies]'` for automatic API token creation via browser cookies after SSO (macOS/Linux).

## First-time setup

```bash
wssh setup
```

This will:

1. Ask for your Google Workspace email (`sam.neal` is enough — `@mckinnonsc.vic.edu.au` is added automatically)
2. Find or generate an SSH key and upload it to Warpgate via the API
3. Sign you in with Google (browser) and store an API token
4. Install shell tab completion for Warpgate targets

Manual fallback if SSO/API fails:

```bash
wssh setup --manual-credentials
```

## Daily use

```bash
wssh dns01
wssh dns01 -- systemctl status bind9
```

## Commands

| Command | Description |
|---------|-------------|
| `wssh setup` | First-time configuration |
| `wssh auth login` | Browser SSO → API token |
| `wssh auth logout` | Remove stored token |
| `wssh targets list` | List SSH targets |
| `wssh targets refresh` | Refresh completion cache |
| `wssh setup-server <name>` | Add Warpgate keys + register target |
| `wssh credentials add-key` | Upload SSH public key |
| `wssh completion bash\|zsh` | Shell completion script |

## Configuration

`~/.config/wssh/config.yaml` (mode 600):

```yaml
user: sam.neal@mckinnonsc.vic.edu.au
host: ssh.mckinnon.tech
port: 2222
server_domain: noddy.mckinnonsc.vic.edu.au   # direct SSH hostnames for setup-server
api_token: "..."
```

Environment overrides:

- `WSSH_API_TOKEN` — API token
- `WSSH_ADMIN_API_TOKEN` — admin token for `setup-server`
- `WSSH_WARPGATE_CLIENT_KEYS` — newline-separated client public keys
- `WSSH_CONFIG` — config file path

Target names are cached in `~/.cache/wssh/targets.json` (default TTL 24 hours).

## On-demand server setup

If a target is missing or Warpgate cannot authenticate to the server:

```bash
wssh setup-server myserver
```

Or answer **yes** when `wssh myserver` detects the problem.

This will (with admin permission):

1. SSH directly to the server (school network)
2. Append Warpgate client keys to `~/.ssh/authorized_keys`
3. Register the server as a Warpgate SSH target

Requires `targets_create` admin permission on your Warpgate account (or `WSSH_ADMIN_API_TOKEN`).

## Warpgate APIs used

**User API** (`https://ssh.mckinnon.tech/@warpgate/api`):

- `GET /targets` — list targets / completion
- `POST /profile/credentials/public-keys` — upload SSH key
- `POST /profile/api-tokens` — create API token (after SSO)

**Admin API** (`https://ssh.mckinnon.tech/@warpgate/admin/api`):

- `GET /ssh/own-keys` — Warpgate client keys
- `POST /targets` — register SSH target

## Development

```bash
pip install -e '.[dev]'
pytest
```
