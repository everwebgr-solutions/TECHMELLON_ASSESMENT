"""
The 10 customer scenarios the refinement loop tests.
Each scenario has an id, description, and a detailed customer brief
that the simulator LLM uses to roleplay the customer.

Destinations and prices reflect the seeded database:
  Dublin → London £89 | Amsterdam £109 | Paris £119 | Barcelona £149 | Rome £169 | Athens £199
  (economy; business ≈ 2.8×; first ≈ 5.5×)

Scenarios that operate on an existing booking use the hardcoded seed reference BK-SKY001
(passenger: Alex Johnson, economy Paris flight) which is inserted by api/seed.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, TypedDict

_SCENARIO_STATE_FILE = Path("data/scenario_state.json")


class Scenario(TypedDict):
    id: str
    description: str
    customer_brief: str


SCENARIOS: List[Scenario] = [
    {
        "id": "book_next_available",
        "description": "Book the next available flight to a requested destination",
        "customer_brief": (
            "You want to fly from Dublin to Barcelona as soon as possible. "
            "You are flexible on the time but want the earliest available flight today or tomorrow. "
            "You are happy with economy class. Your name is James Murphy and your email is james.murphy@email.com. "
            "Ask about the next available flight to Barcelona and book it if the price is under £200. "
            "Economy flights to Barcelona from Dublin cost around £149 — that is within your budget."
        ),
    },
    {
        "id": "cheapest_ticket",
        "description": "Find and book the cheapest available tickets within the following week",
        "customer_brief": (
            "You are on a tight budget and want the absolute cheapest flight available anywhere within the next week. "
            "You don't mind the destination — you just want the lowest price. "
            "Your name is Sarah Chen and email is sarah.chen@email.com. "
            "Ask the agent to find the cheapest available flights. "
            "The cheapest route from Dublin is to London at around £89 economy."
        ),
    },
    {
        "id": "pet_policy",
        "description": "Enquire whether pets are permitted on board and under what conditions",
        "customer_brief": (
            "You have a small cat (4 kg) and want to bring it on a flight to Amsterdam. "
            "Ask about the pet policy — specifically whether cats are allowed in the cabin, "
            "what the fee is, what carrier requirements apply, and how far in advance you need to arrange it. "
            "You are ONLY gathering information; you are NOT booking a flight today."
        ),
    },
    {
        "id": "reschedule_booking",
        "description": "Reschedule an existing booking to a different date or flight",
        "customer_brief": (
            "You have an existing booking with reference BK-SKY001 (passenger name: Alex Johnson). "
            "You need to move it to a later Dublin→Paris flight. "
            "Ask the agent to reschedule booking BK-SKY001 to the next available economy flight to Paris "
            "that departs after your current one. Paris economy flights cost around £119. "
            "Confirm the new flight details and price once the reschedule is done."
        ),
    },
    {
        "id": "baggage_enquiry",
        "description": "Enquire about baggage allowance: weight limits, cabin vs hold, excess fees",
        "customer_brief": (
            "You are flying economy to Rome and want to understand the full baggage rules. "
            "Ask about: what you can bring in the cabin, whether hold baggage is included in economy, "
            "the weight limit for hold bags, and how much it costs to add an extra checked bag. "
            "You are ONLY gathering information; you are NOT booking a flight today."
        ),
    },
    {
        "id": "refund_cancellation",
        "description": "Request a refund or cancellation for an existing booking",
        "customer_brief": (
            "You have a booking with reference BK-SKY001 (passenger name: Alex Johnson) that you want to cancel. "
            "Call the agent, provide your booking reference, and ask to cancel the booking. "
            "Ask about the refund process: whether you get a full refund, any fees that apply, "
            "and how long the refund takes to process. "
            "Complete the cancellation if the agent can process it."
        ),
    },
    {
        "id": "seat_preference",
        "description": "Book a flight with a specific seat preference (window, aisle, extra legroom)",
        "customer_brief": (
            "You want to book a business class flight from Dublin to London. "
            "You specifically want a window seat if possible. "
            "Your name is Maria Gonzalez and email is maria.g@email.com. "
            "Ask to book the next available business class flight to London with a window seat. "
            "Business class to London from Dublin costs around £249."
        ),
    },
    {
        "id": "add_extras",
        "description": "Add an extra bag or special item (pram, sports equipment) to an existing booking",
        "customer_brief": (
            "You have a booking with reference BK-SKY001 (passenger name: Alex Johnson). "
            "You are travelling with a baby and need to add a pram and one extra checked bag to your booking. "
            "Call the agent, provide your booking reference BK-SKY001, and ask to add: "
            "1 extra checked bag and a pram as a special item. "
            "Confirm the updated booking details once the extras are added."
        ),
    },
    {
        "id": "check_in_info",
        "description": "Enquire about check-in times, gate information, or flight status",
        "customer_brief": (
            "You are flying tomorrow and want to know: when online check-in opens, "
            "when you need to be at the airport, and when the gate closes. "
            "Also ask if there is a way to check the status of your specific flight. "
            "You are ONLY gathering information; you are NOT booking a flight today."
        ),
    },
    {
        "id": "special_assistance",
        "description": "Request assistance for a passenger with reduced mobility or special needs",
        "customer_brief": (
            "You use a wheelchair and are planning a flight to Athens. You cannot climb stairs and need "
            "assistance from check-in to your seat. Ask what types of wheelchair assistance are available, "
            "how to request it, whether there is a fee, and how far in advance you need to arrange it. "
            "You are ONLY gathering information; you are NOT booking a flight today."
        ),
    },
]


def get_scenario(scenario_id: str) -> Scenario:
    for s in SCENARIOS:
        if s["id"] == scenario_id:
            return s
    raise ValueError(f"Scenario '{scenario_id}' not found")


def get_scenario_for_run() -> Scenario:
    """Pick one scenario for this entire loop run, rotating across runs.

    The next index is persisted to data/scenario_state.json so that each new
    run advances to the next scenario, cycling through all 10 in order.
    """
    idx = 0
    if _SCENARIO_STATE_FILE.exists():
        try:
            idx = json.loads(_SCENARIO_STATE_FILE.read_text()).get("next_index", 0)
        except Exception:
            idx = 0
    idx = idx % len(SCENARIOS)
    scenario = SCENARIOS[idx]
    _SCENARIO_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SCENARIO_STATE_FILE.write_text(json.dumps({"next_index": (idx + 1) % len(SCENARIOS)}))
    return scenario
