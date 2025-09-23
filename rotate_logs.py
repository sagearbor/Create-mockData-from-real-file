#!/usr/bin/env python
"""
Log rotation script that can be run manually or via cron/scheduler.

Usage:
    python rotate_logs.py

Cron example (runs daily at 2 AM):
    0 2 * * * cd /path/to/project && python rotate_logs.py

Azure Function Timer Trigger example:
    Schedule: 0 0 2 * * * (runs daily at 2 AM)
"""

from src.utils.log_rotation import LogRotator


def main():
    """Run log rotation and cleanup."""
    rotator = LogRotator(
        log_dir="logs/usage",
        archive_dir="logs/archives",
        retention_days=2  # Archive logs older than 2 days
    )

    print("Starting log rotation...")

    # Rotate old logs to archives
    rotator.rotate_logs()

    # Clean up very old archives (older than 12 months)
    rotator.cleanup_old_archives(max_age_months=12)

    print("Log rotation completed")


if __name__ == "__main__":
    main()