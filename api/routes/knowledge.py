from __future__ import annotations

from fastapi import APIRouter, HTTPException

from knowledge_base.kb_service import get, list_topics, search

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/topics")
def topics():
    return {"topics": list_topics()}


@router.get("/{topic}")
def get_topic(topic: str):
    section = get(topic)
    if section is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown topic '{topic}'. Available: {list_topics()}",
        )
    return {"topic": topic, "content": section}


@router.get("/search/{query}")
def search_knowledge(query: str):
    results = search(query)
    if not results:
        raise HTTPException(status_code=404, detail=f"No policy found matching '{query}'")
    return {"query": query, "results": results}
