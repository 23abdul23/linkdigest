class Skipped(Exception):
    """Job is not an error but will not be processed (for example a long video)."""


class ProcessingError(Exception):
    """Permanent failure. The message is shown to the user, so keep it plain."""


class Blocked(ProcessingError):
    """Instagram login wall or rate limit. The worker retries it at most once."""
