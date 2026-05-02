"""Demo: two simulated agents coordinate via COP blackboard."""
import tempfile
import time
from pathlib import Path
from common_operating_picture import COP

with tempfile.TemporaryDirectory() as d:
    cop = COP(state_file=str(Path(d) / "cop_state.json"))

    # Agent A registers its task
    cop.register_task("agent-a", "building search index")
    print("Agent A registered task")

    # Agent B checks before writing the same file
    blocked = cop.lock_resource("agent-b", "search_index.db")
    print(f"Agent B lock attempt: {'blocked' if not blocked else 'acquired'}")

    # Agent A completes
    cop.unlock_resource("agent-a", "search_index.db")
    cop.clear_task("agent-a")
    print("Agent A cleared")

    # Agent B succeeds now
    blocked2 = cop.lock_resource("agent-b", "search_index.db")
    print(f"Agent B second attempt: {'blocked' if not blocked2 else 'acquired'}")

    # Blackboard share
    cop.share("latest_research", {"topic": "graph databases", "sources": 42})
    data = cop.get_shared("latest_research")
    print(f"Blackboard: {data}")
    cop.unlock_resource("agent-b", "search_index.db")
