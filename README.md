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

The installer adds Python, pipx, and OpenSSH where they are missing (Homebrew, apt, dnf, or pacman), then installs `wssh` with pipx.

`wssh setup` asks for your Warpgate host, username, and SSH key, signs you in, and installs shell tab completion. Settings are saved to `~/.wssh/config.yaml` (mode `0600`).

## Usage

```bash
# Connect — anything that is not a command is a target name
wssh dns01                                # open a shell
wssh dns01 -- systemctl status nginx      # run a remote command
wssh dns01 -L 8080:localhost:80           # extra arguments go to ssh

# Copy files — target:path in place of host:path
wssh scp ./notes.txt dns01:~/             # up
wssh scp -r dns01:/etc/nginx .            # down, options go to scp
wssh scp docker04:~/file.txt docker02:~/  # target to target

# Targets
wssh targets list                         # what you can reach
wssh targets refresh                      # update the completion cache now

# Register a new server in Warpgate
wssh setup-server dns01
```

Target names tab-complete once setup has run, and a misspelled one gets a suggestion rather than a failed connection.

## Help

`wssh --help` lists every command and global flag; `wssh <command> --help` covers that command's options.

```bash
wssh --help
wssh setup --help
wssh targets --help
```

Config file format and the `WSSH_*` environment variables are documented in [`config.example.yaml`](config.example.yaml).

## License

MIT — see [LICENSE](LICENSE).
