"""common-operating-picture — Shared state tracker for distributed agent systems."""
__version__ = "1.0.0"

from common_operating_picture.cop import (
    COP,
    register_task,
    clear_task,
    check_cop,
    lock_resource,
    unlock_resource,
    post_bounty,
    bid_bounty,
    claim_bounty,
    register_exit_cleanup,
)

__all__ = [
    "COP",
    "register_task",
    "clear_task",
    "check_cop",
    "lock_resource",
    "unlock_resource",
    "post_bounty",
    "bid_bounty",
    "claim_bounty",
    "register_exit_cleanup",
]
