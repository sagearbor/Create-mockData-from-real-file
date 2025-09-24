"""Log rotation utility for usage logs."""

import os
import gzip
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import shutil
import fcntl


class LogRotator:
    """Handles log rotation and archiving for usage logs."""

    def __init__(self, log_dir: str = "logs/usage", archive_dir: str = "logs/archives",
                 retention_days: int = 2):
        """
        Initialize the log rotator.

        Args:
            log_dir: Directory containing daily log files
            archive_dir: Directory for archived logs
            retention_days: Number of days to keep logs before archiving
        """
        self.log_dir = Path(log_dir)
        self.archive_dir = Path(archive_dir)
        self.retention_days = retention_days

        # Ensure directories exist
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def rotate_logs(self) -> None:
        """Rotate logs older than retention period."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)

        for log_file in self.log_dir.glob("usage_*.jsonl"):
            # Parse date from filename
            try:
                date_str = log_file.stem.replace("usage_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")

                if file_date < cutoff_date:
                    self._archive_log(log_file)
            except ValueError:
                # Skip files that don't match expected pattern
                continue

    def _archive_log(self, log_file: Path) -> None:
        """Archive a single log file."""
        # Create monthly archive file
        date_str = log_file.stem.replace("usage_", "")
        file_date = datetime.strptime(date_str, "%Y-%m-%d")
        archive_name = f"usage_{file_date.strftime('%Y-%m')}.jsonl.gz"
        archive_path = self.archive_dir / archive_name

        # Append to existing archive or create new one
        mode = 'ab' if archive_path.exists() else 'wb'

        with open(log_file, 'rb') as src:
            with gzip.open(archive_path, mode) as dst:
                dst.write(src.read())
                # Add newline separator if appending
                if mode == 'ab':
                    dst.write(b'\n')

        # Remove original file after successful archiving
        log_file.unlink()
        print(f"Archived {log_file.name} to {archive_name}")

    def cleanup_old_archives(self, max_age_months: int = 12) -> None:
        """Remove archives older than specified months."""
        cutoff_date = datetime.now() - timedelta(days=max_age_months * 30)

        for archive_file in self.archive_dir.glob("usage_*.jsonl.gz"):
            try:
                # Parse year-month from filename
                date_str = archive_file.stem.replace("usage_", "").replace(".jsonl", "")
                file_date = datetime.strptime(date_str, "%Y-%m")

                if file_date < cutoff_date:
                    archive_file.unlink()
                    print(f"Deleted old archive: {archive_file.name}")
            except ValueError:
                continue


def safe_append_log(log_file: Path, data: dict) -> bool:
    """
    Safely append to log file with file locking to handle concurrent access.

    Args:
        log_file: Path to the log file
        data: Dictionary to append as JSON line

    Returns:
        True if successful, False otherwise
    """
    try:
        # Ensure parent directory exists
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Open file in append mode with exclusive lock
        with open(log_file, 'a') as f:
            # Try to acquire exclusive lock (non-blocking)
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                json.dump(data, f)
                f.write('\n')
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return True
            except IOError:
                # Could not acquire lock, try again with blocking lock
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(data, f)
                f.write('\n')
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                return True
    except Exception as e:
        print(f"Error writing to log: {e}")
        return False


if __name__ == "__main__":
    # Example usage
    rotator = LogRotator()
    rotator.rotate_logs()

    # Could be run as a scheduled job:
    # - Cron job: 0 2 * * * python -m src.utils.log_rotation
    # - Azure Function with Timer Trigger
    # - Python schedule library in main app