"""
One-time setup script: creates the ElevenLabs agent and writes ELEVENLABS_AGENT_ID to .env.

Run: python -m elevenlabs_client.setup
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from config import ELEVENLABS_AGENT_ID, ELEVENLABS_API_KEY, ELEVENLABS_BASE_URL
from elevenlabs_client.agent import create_agent, _HEADERS
from refinement.system_prompt import get_initial_prompt

_AGENT_NAME = "Sky Airways Customer Service"


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


def _find_existing_agent() -> str | None:
    """Return the agent_id of an existing Sky Airways agent, or None."""
    resp = httpx.get(f"{ELEVENLABS_BASE_URL}/convai/agents", headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    for agent in resp.json().get("agents", []):
        if agent.get("name") == _AGENT_NAME:
            return agent["agent_id"]
    return None


def main() -> None:
    if not ELEVENLABS_API_KEY:
        print("ERROR: ELEVENLABS_API_KEY is not set. Add it to your .env file.")
        return

    if ELEVENLABS_AGENT_ID:
        print(f"Agent already exists: {ELEVENLABS_AGENT_ID}")
        print("To recreate, clear ELEVENLABS_AGENT_ID from .env and re-run.")
        return

    # Before creating, check if an agent with this name already exists on the account
    # to avoid accumulating duplicate agents and tool library entries.
    existing_id = _find_existing_agent()
    if existing_id:
        print(f"Found existing agent on ElevenLabs account: {existing_id}")
        _write_agent_id_to_env(existing_id)
        print(f"ELEVENLABS_AGENT_ID={existing_id} written to .env")
        return

    print("Creating Sky Airways ElevenLabs agent...")
    prompt = get_initial_prompt()
    agent_id = create_agent(prompt)
    print(f"Agent created: {agent_id}")

    _write_agent_id_to_env(agent_id)
    print(f"ELEVENLABS_AGENT_ID={agent_id} written to .env")


if __name__ == "__main__":
    main()
