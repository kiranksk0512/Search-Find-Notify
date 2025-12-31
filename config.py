EMAIL_SENDER = "kiranksk0512@gmail.com"
EMAIL_PASSWORD = "angr rxwb otyc omyr"
EMAIL_RECEIVER = "aquanumber01@gmail.com"

import os

BASE_DATA_PATH = "data"

# Toggle versioning for each company individually
COMPANY_VERSIONING = {
    "apple": False,
    "google": False,
    "microsoft": False,
    "intuit": False,
    "cisco": False,
    "walmart": False,
    "waymo": False,
    # Add more companies as needed
}

COMPANY_EMAIL_NOTIFICATIONS = {
    "apple": True,
    "google": True,
    "meta": True,
    "intuit": True,
    "cisco": True,
    "walmart": True,
    "waymo": True,
}

# Backup retention policy (in days)
BACKUP_RETENTION_DAYS = 7


# Stability knobs
MISS_THRESHOLD = 10          # consecutive runs missing before we call a job deleted
REOPEN_GRACE_DAYS = 30      # if a job reappears within this, mark as reopened (informational)

# Big-drop refetch
BIG_DROP_REFETCH_RATIO = 0.6   # if current_count < prev_count * 0.6, do a second pass
MAX_REFETCHES = 1              # how many extra passes to try


# --- Stability controls ---
# Which companies use the stability layer (consecutive-miss deletion + reopened tracking)
STABILITY_ENABLED = {
    "microsoft": True,
    "meta": True,
    # "netflix": False,
    # "apple": False,
}

# disable one source if it misbehaves:
BLACKROCK_USE_KIRAN=True
# or
BLACKROCK_USE_CLASSIC=True


# ---------------- Waymo (careers.withwaymo.com) ----------------
# NOTE: Waymo is protected by AWS WAF and may return HTTP 202 + challenge unless
# you provide fresh browser cookies (especially `aws-waf-token`).
#
# Prefer setting these as Lambda environment variables or via AWS Secrets Manager.
# Keeping real cookie values in source control is not recommended.

# Full cookie string copied from browser devtools (same format as curl -b 'k=v; ...').
# WARNING: this value is effectively a secret and expires/rotates; avoid committing real values.
WAYMO_COOKIES = os.getenv(
    "WAYMO_COOKIES",
    "ctc=a6d16c1225748641889cb4370db1468108fb5985179f846be3415067edd3abb298bccf7f0d254e; ctc_session=1c34a3033734710b34665b7cbe9f2254def43c1496ac3ae41bed880a5e7a49acb4c4945870f80d; _clinch_session=RfFrjkGQCCZAOfj0Cx4fUCtOLBNuK%2B8BfKhzD60QQ0X1N3gpO%2B%2FMCAICUy4yhXCHSt8Sj%2Fep6AHpetzeNCgtv0pwPEJY9NVgsPS4ikhZiI6y0bLBJ4R4Aq5L2TVyGcWFs1h7kaFVa79Ic7Xv%2F8vzQm5pw4ZaJGw6NqJtjGmLeU9hhg2%2FPWiMsTt4o2plvlVp9kxzWsIZg3zCn7CCkxuxlX9Fqjo6eUdQrGgrrJsVp1vS99tO1YTAX%2FsXCvSg4s35d1At02pRTdNGwjUdS8HNRbgZUPGZoQg%3D--UYxuEQBqhgSfXzxT--DJtZqlR%2BPV9CZkS9bvuaWA%3D%3D; aws-waf-token=332e9c22-6522-489d-92bd-b87dff5f94cd:EQoAnMembP9pAAAA:Bc1QVxc5ShQkLptuYnbpQpi2WHIc4fBKxkoqQrsnwRUuQ6UPWZSnr2H/gIg+FYFhbB+CvPSx/rI2BtMuZ+OhQlEW8OgXphlAazzQazipS3WFyAbMxfeHv1Poki65U3IijYF9SjIVeJbLXgYW+YrN/0Xqce6nVOse+WJTCm1GYKYMf+Clr8aXoUSdcXI+LavjjzamMHMi7jvsIPwUqzi/p/QE6zvZS7hhVIv1gpH3LPR1n7mt/uDXiVYA6nSRBdU+1K4xPqfG5YRMfj4o"
)

# Optional: override the full search URL if Waymo rotates the block/page version params.
WAYMO_SEARCH_URL = os.getenv("WAYMO_SEARCH_URL", "")

# Optional filters (comma-separated)
WAYMO_DEPARTMENT_UIDS = os.getenv("WAYMO_DEPARTMENT_UIDS", "")
WAYMO_COUNTRY_CODES = os.getenv("WAYMO_COUNTRY_CODES", "US")
WAYMO_QUERY = os.getenv("WAYMO_QUERY", "")

# Optional controls
WAYMO_MAX_PAGES = int(os.getenv("WAYMO_MAX_PAGES", "20"))
WAYMO_MIN_EXPECTED_COUNT = int(os.getenv("WAYMO_MIN_EXPECTED_COUNT", "40"))
