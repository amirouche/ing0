# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run tests
python3 -m pytest ing0.py

# Run directly
python3 ing0.py

# Install globally (requires sudo)
sudo uv tool install git+https://github.com/amirouche/ing0
```

## Architecture

Everything lives in a single file: `ing0.py`. There are no submodules.

CLI dispatch is done via `match sys.argv[1:]` in `main()`, which maps subcommands to `cli_*` functions. The entrypoint is `sys.exit(main())`.

### Subcommands

| Command | Function | Notes |
|---|---|---|
| `baggify PATH` | `baggify()` | Bag-of-words word frequency over `*.py` files |
| `summary PATH` | `summary()` | Per-directory SLOC + baggify top-10 |
| `fastapi routes` | `fastapi_routes()` | Lists routes from a local `app` module (must be in cwd) |
| `vm available` | `cli_images_available()` | Fetches LXC image index from `images.linuxcontainers.org` |
| `vm create DIR DISTRO RELEASE ARCH` | `cli_create()` | Downloads and unpacks a rootfs via wget |
| `vm exec DIR [CMD...]` | `cli_exec()` | Runs a command inside the rootfs via `systemd-nspawn` |
| `vm spawn DIR` | `cli_spawn()` | Boots the rootfs as a machine via `systemd-nspawn --boot` |
| `vm boot DIR` | `cli_boot()` | Emulates via QEMU using the rootfs as a 9p filesystem |
| `sqli URI` | `sqli()` | Renders a database ER diagram via `eralchemy2` |

### Key helpers

- `_images_index_fetch(url)` — fetches an HTML directory listing with `curl` (via `subprocess.run`), parses it with `lxml`, returns sorted entries.
- `_images_iter_available_version()` / `_images_iter_available()` — walks the LXC image index to enumerate available rootfs URLs.
- `_iter_directories(root)` — walks a directory tree, skipping hidden dirs, `node_modules`, and `__pycache__`.
- `sloc(directory)` — counts non-blank Python lines.
- `run(command)` — thin wrapper around `subprocess.run(shell=True)`.

### Dependencies

- `lxml` — HTML parsing of LXC image index pages.
- `curl` — HTTP fetching (system binary, no Python dependency).
- `eralchemy2` — optional, only needed for `sqli`.
- `systemd-nspawn`, `qemu-system-x86_64`, `wget` — system tools used by `vm` subcommands.

## Notes

- All shell commands use `shlex.quote()` on interpolated values to prevent injection.
- `DEBUG=1` causes `_images_index_fetch` to re-raise exceptions instead of silently returning `None`.
- The `requests` library is listed in `pyproject.toml` dependencies but is no longer used in code (replaced by curl).
