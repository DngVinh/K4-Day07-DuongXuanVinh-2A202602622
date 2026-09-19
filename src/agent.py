from typing import Callable

from .store import EmbeddingStore


class KnowledgeBaseAgent:
    """
    An agent that answers questions using a vector knowledge base.

    Retrieval-augmented generation (RAG) pattern:
        1. Retrieve top-k relevant chunks from the store.
        2. Build a prompt with the chunks as context.
        3. Call the LLM to generate an answer.
    """

    def __init__(self, store: EmbeddingStore, llm_fn: Callable[[str], str]) -> None:
        self.store = store
        self.llm_fn = llm_fn

    def answer(self, question: str, top_k: int = 3) -> str:
        results = self.store.search(question, top_k=top_k)
        return self._answer_from_results(question, results)

    def answer_with_filter(
        self,
        question: str,
        top_k: int = 3,
        metadata_filter: dict | None = None,
    ) -> str:
        results = self.store.search_with_filter(
            question,
            top_k=top_k,
            metadata_filter=metadata_filter,
        )
        return self._answer_from_results(question, results)

    def _answer_from_results(self, question: str, results: list[dict]) -> str:
        if not results:
            return "I could not find relevant information in the knowledge base."

        context_parts = []
        for index, result in enumerate(results, start=1):
            metadata = result.get("metadata", {})
            source = metadata.get("source_url") or metadata.get("source") or metadata.get("doc_id", "unknown")
            context_parts.append(
                f"[{index}] source={source}\n{result.get('content', '').strip()}"
            )

        prompt = (
            "You are a grounded knowledge-base assistant. Answer the question using only the "
            "context below. If the context does not contain the answer, say that it was not found. "
            "Cite the relevant context number(s) in brackets.\n\n"
            f"Question: {question.strip()}\n\n"
            "Context:\n"
            + "\n\n".join(context_parts)
        )
        answer = self.llm_fn(prompt)
        return answer if isinstance(answer, str) else str(answer)
