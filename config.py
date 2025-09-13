EMAIL_SENDER = "kiranksk0512@gmail.com"
EMAIL_PASSWORD = "angr rxwb otyc omyr"
EMAIL_RECEIVER = "aquanumber01@gmail.com"

BASE_DATA_PATH = "data"

# Toggle versioning for each company individually
COMPANY_VERSIONING = {
    "apple": False,
    "google": False,
    "microsoft": False,
    # Add more companies as needed
}

COMPANY_EMAIL_NOTIFICATIONS = {
    "apple": True,
    "google": True,
    "meta": True,
}

# Backup retention policy (in days)
BACKUP_RETENTION_DAYS = 7


# Stability knobs
MISS_THRESHOLD = 3          # consecutive runs missing before we call a job deleted
REOPEN_GRACE_DAYS = 30      # if a job reappears within this, mark as reopened (informational)

# Big-drop refetch
BIG_DROP_REFETCH_RATIO = 0.6   # if current_count < prev_count * 0.6, do a second pass
MAX_REFETCHES = 1              # how many extra passes to try