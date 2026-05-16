"""
The 10 customer scenarios the refinement loop tests.
Each scenario has an id, description, and a detailed customer brief
that the simulator LLM uses to roleplay the customer.

Destinations and prices reflect the seeded database:
  Dublin → London £89 | Amsterdam £109 | Paris £119 | Barcelona £149 | Rome £169 | Athens £199
  (economy; business ≈ 2.8×; first ≈ 5.5×)
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
        "description": "Find and book the cheapest available ticket within the following week",
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
        "description": "Enquire about rescheduling an existing booking to a different date",
        "customer_brief": (
            "You had a flight from Dublin to Paris but you are not sure of the exact booking reference. "
            "Ask the agent how rescheduling works and what options you would have to move to a later date. "
            "You want to understand the process and see available Dublin→Paris flights for the next few days. "
            "Paris economy flights cost around £119. "
            "You do NOT have a real booking reference — focus on understanding the rescheduling policy and available flights."
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
        "description": "Enquire about cancellation policy and the refund process",
        "customer_brief": (
            "You are considering cancelling a flight you booked but you want to understand the refund policy first. "
            "Ask the agent to explain: whether you can get a refund, any cancellation fees that apply, "
            "and how long the refund would take to process. "
            "You do NOT have a booking reference handy — you want to understand the policy before deciding. "
            "You are NOT necessarily completing a cancellation today, just gathering information."
        ),
    },
    {
        "id": "seat_preference",
        "description": "Book a business class flight with a specific seat preference",
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
        "description": "Enquire about adding a pram and extra bag to a booking",
        "customer_brief": (
            "You are travelling with a baby and need to bring a pram and one extra checked bag. "
            "Ask the agent about the pram policy: whether prams are allowed, what the fee is, "
            "and how to add it to a booking. Also ask about the extra checked bag fee. "
            "You do NOT have a booking reference with you — you just want to understand the costs "
            "and process before you proceed."
        ),
    },
    {
        "id": "check_in_info",
        "description": "Enquire about check-in times and airport procedures",
        "customer_brief": (
            "You are flying tomorrow and want to know: when online check-in opens, "
            "when you need to be at the airport, and when the gate closes. "
            "Also ask if there is a way to check the status of your specific flight. "
            "You are ONLY gathering information; you are NOT booking a flight today."
        ),
    },
    {
        "id": "special_assistance",
        "description": "Request wheelchair assistance for a passenger with reduced mobility",
        "customer_brief": (
            "You use a wheelchair and are planning a flight to Athens. You cannot climb stairs and need "
            "assistance from check-in to your seat. Ask what types of wheelchair assistance are available, "
            "how to request it, whether there is a fee, and how far in advance you need to arrange it. "
            "You are ONLY gathering information; you are NOT booking a flight today."
        ),
    },
    {
        "id": "delayed_flight_compensation",
        "description": "Claim EU261 compensation for a significantly delayed flight",
        "customer_brief": (
            "Your flight from Dublin to Rome last week was delayed by over 4 hours and you missed an important "
            "event. You want to know if you are entitled to compensation under EU261/2004 regulations. "
            "Ask specifically: what the compensation amount would be, how to claim it, and how long it takes. "
            "Push back if the agent is vague — you want concrete figures and a clear process. "
            "You do NOT have your booking reference handy but you remember it was a Sky Airways flight "
            "and you paid around £169 economy. You are frustrated but remain polite."
        ),
    },
    {
        "id": "last_minute_booking",
        "description": "Book a same-day flight with tight check-in window awareness",
        "customer_brief": (
            "You need to fly from Dublin to London today — it is urgent. Ask for the next available flight "
            "today. Your name is Daniel Walsh and email is d.walsh@email.com. "
            "Before confirming the booking, ask the agent what the check-in deadline is so you know if you "
            "can make it in time. Economy to London costs around £89. "
            "If the agent confirms there is a flight with enough time to check in, go ahead and book it."
        ),
    },
    {
        "id": "pet_plus_booking",
        "description": "Book a flight and arrange cabin pet transport in the same call",
        "customer_brief": (
            "You want to book a flight to Amsterdam and also bring your small dog (3 kg) in the cabin. "
            "Your name is Emma Kelly and email is emma.kelly@email.com. "
            "First ask whether your dog qualifies for cabin travel, then book the next available economy "
            "flight to Amsterdam (around £109), and finally ask how to add the pet to the booking and "
            "what the fee is. You want everything sorted in this one call."
        ),
    },
    {
        "id": "class_upgrade_enquiry",
        "description": "Enquire about upgrading an existing economy booking to business class",
        "customer_brief": (
            "You booked an economy flight to Paris a few days ago but now want to upgrade to business class. "
            "You do not have your booking reference with you. Ask the agent how upgrades work — whether you "
            "can change class on an existing booking or whether you need to cancel and rebook. "
            "Ask about any fees involved. If you need to rebook, ask to see available business class flights "
            "to Paris and what they cost (business to Paris is around £333). "
            "You are willing to pay the difference but want to understand the process first."
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
