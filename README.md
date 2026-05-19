# wssh

SSH to McKinnon Warpgate targets from your terminal.

## Requirements

- Python 3.10+
- [pipx](https://pipx.pypa.io/)
- OpenSSH (`ssh`, `ssh-keygen`)

## Quick start

```bash
git clone https://github.com/McKinnonIT/wssh.git
```

```bash
cd wssh
```

```bash
pipx install .
```

```bash
wssh setup
```

```bash
wssh dns01
```

`wssh setup` configures your email, SSH key, API token, and shell tab completion. Use your Google username only (e.g. `sam.neal`) — the school domain is added for you.

Run a remote command:

```bash
wssh dns01 -- systemctl status bind9
```

If browser SSO fails:

```bash
wssh setup --manual-credentials
```
