# wssh

SSH to [Warpgate](https://github.com/warp-tech/warpgate) targets from your terminal — interactive setup, tab completion, and optional server bootstrap.

## Requirements

- Python 3.10+
- [pipx](https://pipx.pypa.io/)
- OpenSSH (`ssh`, `ssh-keygen`)

## Quick start

Clone the repository and run the installer:

```bash
git clone https://github.com/McKinnonIT/wssh.git
cd wssh
bash install.sh
wssh setup
```

Or install with pipx only:

```bash
git clone https://github.com/McKinnonIT/wssh.git
cd wssh
pipx install .
wssh setup
```

One-liner (after publishing; set `WSSH_REPO` to your fork if needed):

```bash
curl -fsSL https://raw.githubusercontent.com/McKinnonIT/wssh/main/install.sh | bash
wssh setup
```

`wssh setup` asks for your Warpgate host, username, SSH key, API token, and shell tab completion. Settings are saved to `~/.wssh/config.yaml`.

Connect to a target:

```bash
wssh myserver
```

Run a remote command:

```bash
wssh myserver -- systemctl status nginx
```

## Configuration

Config file: `~/.wssh/config.yaml` (override with `WSSH_CONFIG`).

Example:

```yaml
user: alice@example.com
host: bastion.example.com
port: 2222
domain: example.com
server_domain: internal.example.com
api_token: "<your-api-token>"
default_ssh_user: root
default_ssh_port: 22
```

Environment variables override file values:

| Variable | Purpose |
|----------|---------|
| `WSSH_HOST` | Warpgate bastion hostname |
| `WSSH_PORT` | Warpgate SSH port (default `2222`) |
| `WSSH_DOMAIN` | Append to usernames without `@` |
| `WSSH_SERVER_DOMAIN` | DNS suffix for `wssh setup-server` short names |
| `WSSH_API_TOKEN` | User API token |
| `WSSH_ADMIN_API_TOKEN` | Admin API token (for `setup-server`) |
| `WSSH_WARPGATE_CLIENT_KEYS` | Newline-separated client public keys (offline bootstrap) |

See [`config.example.yaml`](config.example.yaml) for a full template.

## Troubleshooting

If Warpgate sign-in does not finish during setup, complete sign-in in the browser and paste an API token when prompted, or run:

```bash
wssh auth login
```

For automatic API token creation after browser sign-in (optional):

```bash
pipx inject wssh browser-cookie3
```

To paste your SSH public key in the Warpgate web UI instead of uploading via API:

```bash
wssh setup --manual-credentials
```

Then run `wssh auth login` if you still need an API token.

Check for install issues (e.g. a legacy shell function shadowing `wssh`):

```bash
wssh doctor
```

## License

MIT — see [LICENSE](LICENSE).
