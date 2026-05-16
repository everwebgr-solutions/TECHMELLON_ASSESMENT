"""
One-time setup script: creates the ElevenLabs agent and writes ELEVENLABS_AGENT_ID to .env.

Run: python -m elevenlabs_client.setup
"""
from __future__ import annotations

import re
from pathlib import Path

from config import ELEVENLABS_AGENT_ID, ELEVENLABS_API_KEY
from elevenlabs_client.agent import create_agent
from refinement.system_prompt import get_initial_prompt


def _write_agent_id_to_env(agent_id: str) -> None:
    env_path = Path(".env")
    if not env_path.exists():
        env_path.write_text(f"ELEVENLABS_AGENT_ID={agent_id}\n")
        return

    content = env_path.read_text()
    if "ELEVENLABS_AGENT_ID" in content:
        content = re.sub(
            r"^ELEVENLABS_AGENT_ID=.*$",
            f"ELEVENLABS_AGENT_ID={agent_id}",
            content,
            flags=re.MULTILINE,
        )
    else:
        content += f"\nELEVENLABS_AGENT_ID={agent_id}\n"

    env_path.write_text(content)


def main() -> None:
    if not ELEVENLABS_API_KEY:
        print("ERROR: ELEVENLABS_API_KEY is not set. Add it to your .env file.")
        return

    if ELEVENLABS_AGENT_ID:
        print(f"Agent already exists: {ELEVENLABS_AGENT_ID}")
        print("To recreate, clear ELEVENLABS_AGENT_ID from .env and re-run.")
        return

    print("Creating Sky Airways ElevenLabs agent...")
    prompt = get_initial_prompt()
    agent_id = create_agent(prompt)
    print(f"Agent created: {agent_id}")

    _write_agent_id_to_env(agent_id)
    print(f"ELEVENLABS_AGENT_ID={agent_id} written to .env")


if __name__ == "__main__":
    main()
