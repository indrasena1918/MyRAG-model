"""Build stable, user-readable source references for retrieved passages."""


def citations_for(passages: list[dict]) -> list[dict]:
    citations = []
    for index, item in enumerate(passages, start=1):
        metadata = item["metadata"]
        citations.append(
            {
                "label": f"S{index}",
                "source": metadata.get("source", "Unknown source"),
                "section": metadata.get("section") or None,
                "page": metadata.get("page") or None,
                "excerpt": item["text"][:320],
            }
        )
    return citations
