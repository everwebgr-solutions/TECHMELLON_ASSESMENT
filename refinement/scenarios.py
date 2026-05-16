"""
The 10 customer scenarios the refinement loop tests.
Each scenario has an id, description, and a detailed customer brief
that the simulator LLM uses to roleplay the customer.

Destinations and prices reflect the seeded database:
  Dublin → London £89 | Amsterdam £109 | Paris £119 | Barcelona £149 | Rome £169 | Athens £199
  (economy; business ≈ 2.8×; first ≈ 5.5×)
"""
from __future__ import annotations

from typing import List, TypedDict


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
]


def get_scenario(scenario_id: str) -> Scenario:
    for s in SCENARIOS:
        if s["id"] == scenario_id:
            return s
    raise ValueError(f"Scenario '{scenario_id}' not found")


def get_rotating_scenario(iteration: int) -> Scenario:
    """Return a scenario for the given iteration using round-robin rotation.

    Cycles through all 10 scenarios in order so each run covers a different
    subset and no scenario repeats until all others have been tested.
    iteration is 1-based.
    """
    return SCENARIOS[(iteration - 1) % len(SCENARIOS)]
