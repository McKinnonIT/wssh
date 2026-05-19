"""Organization defaults for McKinnon Warpgate."""

WARPGATE_HOST = "ssh.mckinnon.tech"
WARPGATE_PORT = 2222
WARPGATE_DOMAIN = "mckinnonsc.vic.edu.au"
# Internal server hostnames (direct SSH, before Warpgate)
SERVER_DOMAIN = "noddy.mckinnonsc.vic.edu.au"
WARPGATE_HTTPS_PORT = 443

USER_API_PREFIX = "/@warpgate/api"
ADMIN_API_PREFIX = "/@warpgate/admin/api"

CREDENTIALS_URL = f"https://{WARPGATE_HOST}/@warpgate/#/profile/credentials"
API_TOKENS_URL = f"https://{WARPGATE_HOST}/@warpgate/#/profile/api-tokens"
LOGIN_URL = f"https://{WARPGATE_HOST}/@warpgate/#/login"

DEFAULT_TARGETS_CACHE_TTL_HOURS = 24
# Role granted on targets created/updated by wssh setup-server (Warpgate "Allow access for roles")
DEFAULT_TARGET_ROLE = "admin"
API_TOKEN_LABEL = "wssh-cli"

COMPLETION_BEGIN = "# >>> wssh completion >>>"
COMPLETION_END = "# <<< wssh completion <<<"
LEGACY_WRAPPER_BEGIN = "# >>> warpgate wssh wrapper >>>"
LEGACY_WRAPPER_END = "# <<< warpgate wssh wrapper <<<"
