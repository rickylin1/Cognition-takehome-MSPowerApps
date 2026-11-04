"""Role -> permissions. The only place role names are defined.

Each role is scoped to a single app (or to core). No combined cross-app roles.
"""

ROLES: dict[str, list[str]] = {}
