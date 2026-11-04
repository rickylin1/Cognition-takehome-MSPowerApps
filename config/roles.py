"""Role -> permissions. The only place role names are defined.

Each role is scoped to a single app (or to core). No combined cross-app roles.
"""

ROLES: dict[str, list[str]] = {
    "auditor": ["core:audit.view"],
    "kyc_analyst": ["kyc:case.view", "kyc:case.decide"],
    "kyc_senior_analyst": ["kyc:case.view", "kyc:case.decide", "kyc:case.second_review"],
}
