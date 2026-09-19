from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from src import (
    Document,
    EmbeddingStore,
    FixedSizeChunker,
    KnowledgeBaseAgent,
    MockEmbedder,
    RecursiveChunker,
    SentenceChunker,
)


def _configure_console_encoding() -> None:
    """Keep Vietnamese benchmark output readable in Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_console_encoding()


ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / "data" / "dang-ky-hoc-phan-final"

OWNERS = {
    "fixed": "Nguyễn Thế Hưng",
    "recursive": "Đinh Tiến Mạnh",
    "sentence": "Nguyễn Quang Minh",
    "heading": "Nguyễn Minh Tuấn",
    "filtered": "Dương Xuân Vinh",
}

OUTPUT_STEMS = {
    "fixed": "nguyen_the_hung",
    "recursive": "dinh_tien_manh",
    "sentence": "nguyen_quang_minh",
    "heading": "nguyen_minh_tuan",
    "filtered": "duong_xuan_vinh",
}

QUERIES = [
    {
        "id": 1,
        "question": "Theo hướng dẫn TDTU, sinh viên được đăng ký học phần ngoài kế hoạch học tập khi nào?",
        "expected_doc": "tdtu-course-registration-guide",
        "gold_marker": "kế hoạch học tập",
        "answer_markers": ["đợt bổ sung", "còn chỗ", "không trùng"],
        "gold_answer": "Chỉ được đăng ký môn đã có trong kế hoạch học tập; môn ngoài kế hoạch chỉ được thêm ở đợt bổ sung nếu còn chỗ và không trùng thời khóa biểu.",
    },
    {
        "id": 2,
        "question": "Theo quy trình UEL, sau khi đăng ký thành công, sinh viên phải lưu kết quả có mã vạch và được điều chỉnh những gì?",
        "expected_doc": "uel-course-registration-process",
        "gold_marker": "mã vạch",
        "answer_markers": ["mã vạch", "hủy môn", "đổi môn"],
        "gold_answer": "Sinh viên phải xuất kết quả đăng ký có mã vạch để lưu; ở đợt điều chỉnh có thể hủy môn hoặc đổi môn tự chọn nhưng không được đăng ký bổ sung môn mới.",
    },
    {
        "id": 3,
        "question": "Theo hướng dẫn UTE, kế hoạch đăng ký học phần gồm đăng ký sơ bộ và giai đoạn nào nữa?",
        "expected_doc": "ute-course-registration-guide",
        "gold_marker": "hai giai đoạn",
        "answer_markers": ["hai giai đoạn", "đăng ký hoàn chỉnh"],
        "gold_answer": "Kế hoạch gồm hai giai đoạn: đăng ký sơ bộ và đăng ký hoàn chỉnh, trong đó giai đoạn sau dùng để điều chỉnh và hoàn tất đăng ký.",
    },
    {
        "id": 4,
        "question": "Theo quy định UEH, nếu không đóng học phí đúng hạn thì học phần bị xử lý thế nào, và hạn hủy học phần là bao lâu?",
        "expected_doc": "ueh-course-registration-regulation",
        "gold_marker": "10 ngày",
        "answer_markers": ["học phí", "10 ngày"],
        "gold_answer": "UEH có thể hủy học phần chưa đóng học phí đúng hạn; yêu cầu hủy học phần phải theo thời hạn, thường là 10 ngày trước mốc thời khóa biểu hoặc kỳ thi tùy trường hợp.",
    },
    {
        "id": 5,
        "question": "Quy định kế hoạch học tập, tổ chức và đăng ký học phần: cần kiểm tra những điều kiện nào trước khi đăng ký?",
        "expected_doc": "hcmut-course-registration-rules",
        "gold_marker": "điều kiện",
        "answer_markers": ["học phí", "tiên quyết"],
        "metadata_filter": {"audience": "student"},
        "gold_answer": "Cần kiểm tra trạng thái học tập, điều kiện tiên quyết hoặc học phần trước, chuẩn ngoại ngữ/công nghệ thông tin nếu áp dụng, các chuẩn giáo dục thể chất/quốc phòng và tình trạng học phí.",
    },
]


STOPWORDS = {
    "theo", "hướng", "dẫn", "sinh", "viên", "được", "đăng", "ký", "học", "phần",
    "khi", "nào", "gì", "và", "những", "các", "cần", "trước", "cho", "tài", "liệu",
    "dành", "với", "nếu", "thì", "điều", "gì", "bao", "nhiêu", "gồm", "mấy",
}


class HeadingChunker:
    """Keep a Markdown heading with its section; recurse only when needed."""

    def __init__(self, chunk_size: int = 350) -> None:
        self.chunk_size = chunk_size

    def chunk(self, text: str) -> list[str]:
        lines = text.splitlines()
        heading_positions = [
            index for index, line in enumerate(lines)
            if re.match(r"^\s{0,3}#{1,6}\s+\S", line)
        ]
        if not heading_positions:
            return RecursiveChunker(chunk_size=self.chunk_size).chunk(text)

        sections: list[str] = []
        if heading_positions[0] > 0:
            prefix = "\n".join(lines[: heading_positions[0]]).strip()
            if prefix:
                sections.append(prefix)
        for position, start in enumerate(heading_positions):
            end = heading_positions[position + 1] if position + 1 < len(heading_positions) else len(lines)
            section = "\n".join(lines[start:end]).strip()
            if section:
                sections.append(section)

        chunks: list[str] = []
        for section in sections:
            if len(section) <= self.chunk_size:
                chunks.append(section)
                continue
            heading = section.splitlines()[0].strip()
            body = "\n".join(section.splitlines()[1:]).strip()
            for part in RecursiveChunker(chunk_size=self.chunk_size - min(len(heading) + 2, 80)).chunk(body):
                chunks.append(f"{heading}\n\n{part}".strip())
        return chunks


class KeywordHashEmbedder:
    """Small deterministic lexical fallback for an offline benchmark.

    The required tests continue to use the course MockEmbedder. This fallback
    gives the benchmark a reproducible lexical signal without API keys or a
    model download, while ``--provider mock`` remains available for the lab's
    default behavior.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self._backend_name = "keyword-hash offline fallback"
        self.vocabulary: dict[str, int] = {}
        self.idf: dict[str, float] = {}

    def fit(self, texts: list[str]) -> None:
        document_frequency: dict[str, int] = {}
        for text in texts:
            tokens = {
                token
                for token in re.findall(r"[\wÀ-ỹ]+", text.lower(), flags=re.UNICODE)
                if token not in STOPWORDS
            }
            for token in tokens:
                document_frequency[token] = document_frequency.get(token, 0) + 1

        ordered = sorted(document_frequency, key=lambda token: (-document_frequency[token], token))
        self.vocabulary = {token: index for index, token in enumerate(ordered)}
        total_documents = max(len(texts), 1)
        self.idf = {
            token: 1.0 + (total_documents / (1 + frequency)) ** 0.5
            for token, frequency in document_frequency.items()
        }
        self.dim = max(len(self.vocabulary), 1)

    def __call__(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = re.findall(r"[\wÀ-ỹ]+", text.lower(), flags=re.UNICODE)
        for token in tokens:
            if token in STOPWORDS:
                continue
            index = self.vocabulary.get(token)
            if index is not None:
                vector[index] += self.idf.get(token, 1.0)
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        return [value / norm for value in vector]


def parse_frontmatter_and_content(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3:
        raise ValueError(f"Missing YAML frontmatter: {path}")
    metadata: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip().strip('"')
    content = parts[2].strip()
    if content.startswith("# "):
        content = content.split("\n", 1)[1].strip() if "\n" in content else ""
    return metadata, content


def load_corpus() -> list[tuple[Path, dict[str, str], str]]:
    documents = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        metadata, content = parse_frontmatter_and_content(path)
        documents.append((path, metadata, content))
    if not documents:
        raise RuntimeError(f"No Markdown documents found in {CORPUS_DIR}")
    return documents


def choose_chunker(strategy: str):
    if strategy == "fixed":
        return FixedSizeChunker(chunk_size=350, overlap=50)
    if strategy in {"recursive", "filtered"}:
        return RecursiveChunker(chunk_size=350)
    if strategy == "sentence":
        return SentenceChunker(max_sentences_per_chunk=3)
    if strategy == "heading":
        return HeadingChunker(chunk_size=350)
    raise ValueError(f"Unknown strategy: {strategy}")


def build_store(strategy: str, embedder) -> tuple[EmbeddingStore, dict[str, int]]:
    chunker = choose_chunker(strategy)
    store = EmbeddingStore(collection_name=f"registration_{strategy}", embedding_fn=embedder)
    chunk_counts: dict[str, int] = {}
    records: list[Document] = []
    for path, metadata, content in load_corpus():
        chunks = chunker.chunk(content)
        chunk_counts[path.stem] = len(chunks)
        for index, chunk in enumerate(chunks):
            records.append(
                Document(
                    id=f"{path.stem}#{index}",
                    content=f"{metadata.get('title', path.stem)}\n\n{chunk}",
                    metadata={**metadata, "doc_id": path.stem},
                )
            )
    store.add_documents(records)
    return store, chunk_counts


def extractive_llm(prompt: str) -> str:
    question_match = re.search(r"Question:\s*(.+)", prompt)
    question = question_match.group(1).lower() if question_match else ""
    keywords = [token for token in re.findall(r"[\wÀ-ỹ]+", question, flags=re.UNICODE) if token not in STOPWORDS]
    blocks = re.findall(r"\[(\d+)\] source=.*?\n(.*?)(?=\n\n\[\d+\] source=|\Z)", prompt, flags=re.S)
    candidates: list[tuple[int, str, str]] = []
    for number, block in blocks:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", block):
            sentence = sentence.strip()
            if sentence:
                score = sum(1 for keyword in keywords if keyword in sentence.lower())
                candidates.append((score, number, sentence))
    candidates.sort(key=lambda item: item[0], reverse=True)
    relevant_candidates = [candidate for candidate in candidates if candidate[0] > 0]
    selected = relevant_candidates[:8] if relevant_candidates else candidates[:1]
    if not selected:
        return "Không tìm thấy thông tin phù hợp trong ngữ cảnh được truy xuất."
    return " ".join(f"[{number}] {sentence}" for _, number, sentence in selected)


def make_embedder(provider: str):
    if provider == "mock":
        return MockEmbedder()
    if provider == "keyword":
        return KeywordHashEmbedder()
    if provider == "local":
        from src import LocalEmbedder

        return LocalEmbedder()
    raise ValueError("provider must be mock, keyword, or local")


def run(provider: str, strategies: list[str]) -> str:
    embedder = make_embedder(provider)
    if hasattr(embedder, "fit"):
        fitting_texts = []
        for path, metadata, content in load_corpus():
            fitting_texts.append(f"{metadata.get('title', path.stem)}\n{content}")
        fitting_texts.extend(query["question"] for query in QUERIES)
        embedder.fit(fitting_texts)
    lines = [
        "Lab 07 benchmark: Đăng ký học phần",
        f"Embedding backend: {getattr(embedder, '_backend_name', type(embedder).__name__)}",
        f"Corpus: {CORPUS_DIR.relative_to(ROOT)}",
        "",
    ]
    for strategy in strategies:
        store, chunk_counts = build_store(strategy, embedder)
        agent = KnowledgeBaseAgent(store=store, llm_fn=extractive_llm)
        strategy_score = 0
        lines.append(f"=== Strategy: {strategy} | Owner: {OWNERS[strategy]} ===")
        lines.append(f"Stored chunks: {store.get_collection_size()}")
        lines.append("Chunk counts: " + ", ".join(f"{key}={value}" for key, value in chunk_counts.items()))
        for query in QUERIES:
            metadata_filter = query.get("metadata_filter")
            filtered = store.search_with_filter(
                query["question"],
                top_k=3,
                metadata_filter=metadata_filter,
            )
            unfiltered = store.search(query["question"], top_k=3)
            answer = agent._answer_from_results(query["question"], filtered)
            relevant = any(
                result["metadata"].get("doc_id") == query["expected_doc"]
                and query["gold_marker"].lower() in result["content"].lower()
                for result in filtered
            )
            expected_rank = next(
                (
                    index
                    for index, result in enumerate(filtered, start=1)
                    if result["metadata"].get("doc_id") == query["expected_doc"]
                ),
                None,
            )
            answer_markers = query.get("answer_markers", [query["gold_marker"]])
            answer_correct = all(
                marker.lower() in answer.lower() for marker in answer_markers
            )
            if relevant and answer_correct and expected_rank == 1:
                score = 2
            elif relevant:
                score = 1
            else:
                score = 0
            strategy_score += score

            def format_results(results: list[dict]) -> str:
                return " | ".join(
                    f"{item['metadata'].get('doc_id')}#{item['id'].split('#')[-1]} score={item['score']:.4f}"
                    for item in results
                )

            lines.append(f"Q{query['id']}: {query['question']}")
            lines.append(f"  Filter: {metadata_filter or 'none'}")
            lines.append(f"  Top-3 unfiltered: {format_results(unfiltered)}")
            if metadata_filter:
                lines.append(f"  Top-3 filtered: {format_results(filtered)}")
            else:
                lines.append(f"  Top-3 used: {format_results(filtered)}")
            lines.append(f"  Relevant chunk+gold marker in top-3: {'YES' if relevant else 'NO'}")
            lines.append(f"  Expected doc rank: {expected_rank or 'not in top-3'}")
            lines.append(
                f"  Agent answer markers: {'YES' if answer_correct else 'NO'} "
                f"({', '.join(answer_markers)})"
            )
            lines.append(f"  Score: {score}/2")
            if metadata_filter:
                changed = [item["id"] for item in unfiltered] != [item["id"] for item in filtered]
                lines.append(f"  Filter changed candidates: {'YES' if changed else 'NO'}")
            lines.append(f"  Agent: {answer}")
            lines.append(f"  Gold: {query['gold_answer']}")
        lines.append(f"Total benchmark score: {strategy_score}/10")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Lab 07 course-registration benchmark.")
    parser.add_argument("--provider", choices=["keyword", "mock", "local"], default="keyword")
    parser.add_argument(
        "--strategy",
        choices=["all", *OWNERS.keys()],
        default="filtered",
        help="Personal strategy by default; use 'all' for the group comparison.",
    )
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Also write one ket_qua_benchmark_<member>.txt per strategy.",
    )
    args = parser.parse_args()
    strategies = list(OWNERS) if args.strategy == "all" else [args.strategy]
    report = run(args.provider, strategies)
    print(report)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for strategy, stem in OUTPUT_STEMS.items():
            member_report = run(args.provider, [strategy])
            (args.output_dir / f"ket_qua_benchmark_{stem}.txt").write_text(
                member_report + "\n", encoding="utf-8"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
