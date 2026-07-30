"""Shared defaults for wssh (not tied to any deployment)."""

DEFAULT_WARPGATE_PORT = 2222

DEFAULT_TARGETS_CACHE_TTL_HOURS = 24
# Role granted on targets created/updated by wssh setup-server (Warpgate "Allow access for roles")
DEFAULT_TARGET_ROLE = "admin"
API_TOKEN_LABEL = "wssh-cli"

COMPLETION_BEGIN = "# >>> wssh completion >>>"
COMPLETION_END = "# <<< wssh completion <<<"
