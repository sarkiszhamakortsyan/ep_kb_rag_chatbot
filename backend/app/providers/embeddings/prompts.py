"""Task prefixes for retrieval embedding models, shared by the Ollama and in-process providers.

Retrieval models are trained with these prefixes; omitting them hurts ranking. A key matches
when it appears in the model name, so "embeddinggemma" (Ollama) and "google/embeddinggemma-300m"
(Hugging Face) get the same prompts. Documents use {title} and {text}.
"""

PROMPTS: dict[str, tuple[str, str]] = {
    "embeddinggemma": ("task: search result | query: {text}", "title: {title} | text: {text}"),
    "nomic-embed-text": ("search_query: {text}", "search_document: {text}"),
}
PLAIN = ("{text}", "{text}")


def prompts_for(model: str) -> tuple[str, str]:
    """(query template, document template) for a model name."""
    return next((p for key, p in PROMPTS.items() if key in model.lower()), PLAIN)
