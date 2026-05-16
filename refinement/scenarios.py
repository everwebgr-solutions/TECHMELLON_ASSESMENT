"""
The 10 customer scenarios the refinement loop tests.
Each scenario has an id, description, and a detailed customer brief
that the simulator LLM uses to roleplay the customer.
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
            "You are flexible on the time but want the earliest available flight. "
            "You are happy with economy class. Your name is James Murphy and your email is james.murphy@email.com. "
            "Ask about the next available flight to Barcelona and book it if the price is under £200."
        ),
    },
    {
        "id": "cheapest_ticket",
        "description": "Find and book the cheapest available tickets within the following week",
        "customer_brief": (
            "You are on a tight budget and want the cheapest flight available anywhere within the next week. "
            "You don't mind the destination. Your name is Sarah Chen and email is sarah.chen@email.com. "
            "Ask the agent to find the cheapest available flights and book the cheapest one."
        ),
    },
    {
        "id": "pet_policy",
        "description": "Enquire whether pets are permitted on board and under what conditions",
        "customer_brief": (
            "You have a small cat (4 kg) and want to bring it on a flight to Amsterdam. "
            "Ask about the pet policy — specifically whether cats are allowed in the cabin, "
            "what the fee is, what carrier requirements apply, and how far in advance you need to arrange it."
        ),
    },
    {
        "id": "reschedule_booking",
        "description": "Reschedule an existing booking to a different date or flight",
        "customer_brief": (
            "You have an existing booking (the agent will need to look it up — ask the agent to help you find it "
            "or say your reference is BK-TEST01). You need to change your flight to a different date. "
            "Ask to move your flight from Dublin to Paris to two days later. "
            "If the agent cannot find BK-TEST01, ask them to search for flights and then say you want to change your plans."
        ),
    },
    {
        "id": "baggage_enquiry",
        "description": "Enquire about baggage allowance: weight limits, cabin vs hold, excess fees",
        "customer_brief": (
            "You are flying economy to Rome and want to understand the full baggage rules. "
            "Ask about: what you can bring in the cabin, whether hold baggage is included in economy, "
            "the weight limit for hold bags, and how much it costs to add an extra checked bag."
        ),
    },
    {
        "id": "refund_cancellation",
        "description": "Request a refund or cancellation for an existing booking",
        "customer_brief": (
            "You have a booking you need to cancel. Your booking reference is BK-TEST02 "
            "(if not found, ask the agent to help). You want to understand the refund policy first, "
            "then confirm you want to cancel and ask how long the refund will take."
        ),
    },
    {
        "id": "seat_preference",
        "description": "Book a flight with a specific seat preference",
        "customer_brief": (
            "You want to book a business class flight from Dublin to London. "
            "You specifically want a window seat. Your name is Maria Gonzalez and email is maria.g@email.com. "
            "Ask to book the next available business class flight to London with a window seat."
        ),
    },
    {
        "id": "add_extras",
        "description": "Add an extra bag or special item to an existing booking",
        "customer_brief": (
            "You have a booking (reference BK-TEST03 or ask agent to find it) and need to add a pram "
            "and one extra checked bag for your trip. Ask about the pram fee first, then add both to your booking."
        ),
    },
    {
        "id": "check_in_info",
        "description": "Enquire about check-in times, gate information, or flight status",
        "customer_brief": (
            "You are flying tomorrow and want to know: when online check-in opens, "
            "when you need to be at the airport, and when the gate closes. "
            "Also ask if there is a way to check the status of your specific flight."
        ),
    },
    {
        "id": "special_assistance",
        "description": "Request assistance for a passenger with reduced mobility or special needs",
        "customer_brief": (
            "You use a wheelchair and are booking a flight to Athens. You cannot climb stairs and need "
            "assistance from check-in to your seat. Ask what types of wheelchair assistance are available, "
            "how to request it, whether there is a fee, and how far in advance you need to arrange it."
        ),
    },
]


def get_scenario(scenario_id: str) -> Scenario:
    for s in SCENARIOS:
        if s["id"] == scenario_id:
            return s
    raise ValueError(f"Scenario '{scenario_id}' not found")


def get_rotating_scenario(iteration: int) -> Scenario:
    """Return scenarios in round-robin order by iteration (1-indexed)."""
    return SCENARIOS[(iteration - 1) % len(SCENARIOS)]
