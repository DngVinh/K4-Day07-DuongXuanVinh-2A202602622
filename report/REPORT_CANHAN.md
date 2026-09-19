# Báo Cáo Cá Nhân — Lab 7: Embedding & Vector Store

**Họ tên:** Dương Xuân Vinh
**Mã sinh viên:** 2A202602622
**Lớp:** K4-L3A
**Nhóm:** G11 — Đăng ký học phần
**Ngày:** 19/09/2026

> **Phạm vi cá nhân:** Báo cáo này ghi lại cách tôi hoàn thiện các module trong `src`, cách tôi thiết kế chiến lược metadata-filtered retrieval và kết quả chạy trên bộ benchmark chung của nhóm. Bộ 5 query trong phần benchmark khớp với [REPORT_NHOM.md](REPORT_NHOM.md); điểm dưới đây là kết quả của cấu hình cá nhân, không lấy điểm của thành viên khác thay thế.

**Tổng điểm phần cá nhân: 60** = Khởi động (5) + Hướng tiếp cận (10) + Hoàn thiện code (30) + Dự đoán độ tương tự (5) + Kết quả truy xuất (10).

---

## 1. Khởi động (Warm-up) — Cá nhân (5 điểm)

### 1.1. Độ tương tự Cosine (Cosine Similarity)

Sau khi một đoạn văn bản được đưa qua embedder, nó được biểu diễn thành một vector trong không gian nhiều chiều. Cosine similarity đo **góc** giữa vector query và vector tài liệu:

\[
\operatorname{cosine}(a,b)=\frac{a\cdot b}{\|a\|\,\|b\|}
\]

Giá trị gần `1` thường biểu thị hai vector cùng hướng, từ đó gợi ý nội dung/ngữ nghĩa tương đồng; giá trị gần `0` biểu thị ít liên quan; giá trị âm biểu thị hai vector có hướng ngược nhau trong không gian biểu diễn. Cách diễn giải “ngữ nghĩa” chỉ đáng tin khi dùng mô hình embedding thật có học ngôn ngữ.

**Ví dụ dự đoán tương đồng cao:**

- Câu A: “Tôi hoàn tất việc ghi danh các lớp cho học kỳ mới.”
- Câu B: “Tôi chọn môn để theo học trong kỳ tới.”
- Lý do: hai câu dùng từ khác nhau nhưng cùng nói về hành động đăng ký học phần trong một học kỳ.

**Ví dụ dự đoán tương đồng thấp:**

- Câu A: “Tôi kiểm tra lịch đăng ký môn học.”
- Câu B: “Hôm nay trời mưa ở Hà Nội.”
- Lý do: câu thứ nhất thuộc ngữ cảnh học vụ, câu thứ hai thuộc ngữ cảnh thời tiết; hai câu không có mục tiêu hay khái niệm chung đáng kể.

Cosine thường được ưu tiên hơn khoảng cách Euclid cho text embedding vì Euclid phụ thuộc cả vào độ dài vector. Một văn bản dài hơn có thể có magnitude lớn dù cùng chủ đề với văn bản ngắn; cosine chuẩn hóa ảnh hưởng của magnitude và tập trung vào hướng biểu diễn. Tuy vậy, cosine không tự làm cho embedding có chất lượng: nếu embedder không hiểu ngôn ngữ thì score vẫn không phản ánh đúng ý nghĩa.

### 1.2. Bài toán tính toán Chunking

Với tài liệu dài `L=10.000`, `chunk_size=S=500`, `overlap=O=50`, bước dịch giữa hai chunk là `S-O=450`. Áp dụng công thức đề bài:

```text
ceil((L - O) / (S - O))
= ceil((10000 - 50) / (500 - 50))
= ceil(9950 / 450)
= ceil(22.111...)
= 23 chunks
```

Tôi đã kiểm chứng bằng implementation hiện tại:

```python
FixedSizeChunker(chunk_size=500, overlap=50).chunk("a" * 10000)  # 23 chunks
FixedSizeChunker(chunk_size=500, overlap=100).chunk("a" * 10000) # 25 chunks
```

Khi tăng overlap lên `100`, bước dịch giảm còn `400`, nên số chunk tăng lên `ceil(9900/400)=25`. Overlap lớn giúp giữ lại ngữ cảnh ở ranh giới, giảm nguy cơ một câu hoặc một điều kiện bị chia đôi; đổi lại, số vector cần tạo, dung lượng lưu trữ và số chunk gần giống nhau sẽ tăng.

---

## 2. Hướng tiếp cận của tôi (My Approach) — Cá nhân (10 điểm)

### 2.1. Luồng xử lý tổng thể

Tôi tổ chức pipeline theo thứ tự:

```text
Markdown + front matter
        ↓
parse metadata / làm sạch nội dung
        ↓
RecursiveChunker(chunk_size=350)
        ↓
Document(id, content, metadata)
        ↓
EmbeddingStore.add_documents()
        ↓
search() hoặc search_with_filter()
        ↓
KnowledgeBaseAgent tạo context và câu trả lời có nguồn
```

Trong benchmark, mỗi chunk được gán id dạng `doc_id#index`. Tiêu đề tài liệu được ghép vào content của chunk để kết quả vẫn biết mình thuộc nguồn nào; metadata giữ `source_url`, `retrieved_at`, `document_version`, `audience`, `department`, `category` và `language` để truy vết hoặc lọc.

### 2.2. Các hàm chia nhỏ (Chunking Functions)

#### `FixedSizeChunker`

Đây là implementation mẫu của lab, chia theo cửa sổ ký tự có overlap. Với `chunk_size=350`, overlap mặc định của lớp là `50`; chiến lược này dễ dự đoán về kích thước nhưng có thể cắt giữa câu hoặc giữa hai ý. Tôi dùng nó làm mốc tham khảo khi so sánh, không chọn làm chiến lược cá nhân.

#### `SentenceChunker.chunk`

Hàm chuẩn hóa khoảng trắng rồi tách câu bằng regex `(?<=[.!?])\s+`. Positive lookbehind giữ lại dấu câu ở cuối câu. Các câu liên tiếp được gom tối đa `max_sentences_per_chunk` câu, mặc định là 3. Văn bản rỗng hoặc chỉ có khoảng trắng trả về `[]`; câu cuối không có dấu câu vẫn được giữ vì nó vẫn là một phần nội dung hợp lệ.

Ưu điểm là chunk dễ đọc và không thường xuyên bị cắt giữa câu. Nhược điểm là một câu rất dài vẫn có thể vượt kích thước mong muốn, và regex chưa hiểu đầy đủ các viết tắt như `TS.` hoặc số thập phân.

#### `RecursiveChunker.chunk` và `_split`

Đây là chunker nền tôi chọn. Thuật toán thử các separator theo thứ tự ưu tiên:

```python
["\n\n", "\n", ". ", " ", ""]
```

Nếu đoạn hiện tại không vượt `chunk_size`, hàm giữ nguyên đoạn. Nếu quá dài, hàm tách theo separator lớn nhất còn phù hợp, sau đó gom các mảnh liền kề lại khi tổng độ dài vẫn không vượt giới hạn. Khi không còn separator, hàm fallback sang cắt cứng theo số ký tự. Các trường hợp biên gồm text rỗng trả `[]`, text ngắn trả một chunk và separator rỗng không làm vòng lặp vô hạn.

Recursive phù hợp với corpus hướng dẫn/quy định vì ưu tiên giữ đoạn văn và dòng Markdown trước khi cắt nhỏ hơn. Đổi lại, độ dài chunk không đều và một section không có heading rõ ràng vẫn có thể bị chia ở vị trí chưa tối ưu.

#### `ChunkingStrategyComparator.compare`

Comparator chạy ba cấu hình trên cùng một text và trả về `count`, `avg_length`, cùng danh sách chunk. Overlap baseline được tính là `chunk_size // 10`; với `chunk_size=350` là 35 ký tự. Kết quả baseline trên ba tài liệu đầu tiên của corpus nhóm:

| Tài liệu | FixedSize | Sentence | Recursive |
|---|---:|---:|---:|
| HCMUT | 4 chunk / 282,5 ký tự | 3 / 339,0 | 4 / 254,8 |
| Hoa Sen | 2 / 272,5 | 2 / 254,0 | 2 / 254,0 |
| TDTU | 3 / 257,0 | 2 / 348,0 | 3 / 232,3 |

Kết quả cho thấy Sentence tạo ít chunk hơn trên TDTU nhưng chunk dài; Recursive tạo nhiều ranh giới hơn và giữ cấu trúc đoạn tốt hơn; FixedSize ổn định về kích thước nhưng dễ cắt ngang câu.

### 2.3. Lớp `EmbeddingStore`

Store dùng list in-memory để lab chạy được mà không phụ thuộc ChromaDB hay dịch vụ bên ngoài. Tôi triển khai các hành vi sau:

| Thành phần | Cách thực hiện | Lý do |
|---|---|---|
| `__init__` | Nhận `collection_name`, `embedding_fn`, khởi tạo `_store=[]` và dùng `_mock_embed` nếu không truyền embedder | Có backend mặc định, dễ kiểm thử và dễ thay embedder |
| `_make_record` | Tạo record gồm `id`, `content`, bản sao `metadata`, `embedding`; tự thêm `doc_id` nếu thiếu | Chuẩn hóa dữ liệu trước khi tìm kiếm |
| `add_documents` | Embed từng `Document`, append record vào store, cập nhật index | Tách ingestion khỏi logic search |
| `search` | Embed query, tính dot product với mọi record, sort giảm dần, cắt `top_k` | Với vector đã chuẩn hóa, dot product tương đương cosine |
| `get_collection_size` | Trả số record hiện có | Kiểm tra ingestion và delete |
| `search_with_filter` | Lọc metadata trước, sau đó mới search trên candidate set | Không để kết quả ngoài phạm vi chiếm chỗ trong top-k |
| `delete_document` | Xóa mọi record có `metadata["doc_id"]` trùng `doc_id`, trả `True` nếu store giảm | Xóa cả các chunk thuộc cùng một tài liệu |

Search có độ phức tạp tuyến tính theo số record và số chiều vector vì store hiện duyệt từng record. Đây là lựa chọn phù hợp cho lab nhỏ, nhưng khi corpus lớn cần index vector thực tế và cơ chế persistence.

### 2.4. Tác tử `KnowledgeBaseAgent`

`answer(question, top_k=3)` gọi `store.search`; `answer_with_filter` gọi `search_with_filter`. `_answer_from_results` xử lý kết quả theo các bước:

1. Nếu không có result, trả thông báo không tìm thấy thông tin thay vì gọi LLM với context rỗng.
2. Với mỗi chunk, đánh số `[1]`, `[2]`, ... và lấy nguồn từ `source_url`, `source` hoặc `doc_id`.
3. Ghép câu hỏi và context vào prompt, yêu cầu agent chỉ dùng context và trích dẫn số chunk.
4. Gọi `llm_fn` được inject từ bên ngoài; vì vậy agent không bị khóa vào một nhà cung cấp LLM cụ thể.

Thiết kế này thể hiện hai yêu cầu quan trọng của RAG: **grounding** (chỉ trả lời từ context) và **source traceability** (có thể lần ngược chunk đã dùng). Tuy nhiên, prompt không thể bù cho retrieval sai; nếu chunk đúng không vào top-k, agent vẫn có thể trả lời thiếu hoặc nói không tìm thấy.

### 2.5. Chiến lược cá nhân: metadata-filtered retrieval

Tôi chọn Recursive làm chunker nền với `chunk_size=350`, sau đó dùng metadata pre-filter cho Q5:

```python
results = store.search_with_filter(
    query,
    top_k=3,
    metadata_filter={"audience": "student"},
)
```

Q5 hỏi về điều kiện đăng ký nhưng không chỉ rõ người hỏi hoặc trường trong câu query. Corpus có tài liệu Hoa Sen mang `audience=all` ở dạng directory, dễ đứng cao vì tiêu đề chứa nhiều từ khóa giống query. Lọc `audience=student` giúp loại tài liệu tổng quát khỏi candidate set, kiểm tra đúng chức năng `search_with_filter` và giảm một loại nhiễu. Tôi không coi filter là bằng chứng đủ để trả lời: filter chỉ giới hạn phạm vi, còn thứ hạng và độ đầy đủ vẫn phụ thuộc embedding/chunking.

Với các Q1–Q4, tôi dùng `search()` không lọc để giữ đúng ngữ cảnh nguồn cụ thể trong câu hỏi. Benchmark dùng 6 tài liệu, 23 chunk sau Recursive chunking và `top_k=3`.

---

## 3. Hoàn thiện code (Core Implementation) — Cá nhân (30 điểm)

Tôi đã hoàn thiện các TODO trong `src/chunking.py`, `src/store.py` và `src/agent.py`, gồm:

- `SentenceChunker` và `RecursiveChunker` với các base case cho text rỗng, text ngắn và fallback cắt cứng.
- `compute_similarity` với công thức cosine và bảo vệ mẫu số bằng 0.
- `ChunkingStrategyComparator` với ba chiến lược và thống kê số lượng/độ dài trung bình.
- `EmbeddingStore` với add, search, collection size, metadata filter và delete document.
- `KnowledgeBaseAgent` với retrieval, prompt context, source traceability và xử lý store rỗng.

### Kết quả kiểm thử

Lệnh kiểm thử đã chạy trong workspace:

```text
python -m pytest tests/ -v -p no:cacheprovider
============================= 42 passed in 0.08s ==============================
```

Các nhóm hành vi được test gồm:

| Nhóm | Nội dung đã kiểm tra |
|---|---|
| Project/interface | `main.py`, package `src`, các class chunker và mock embedder |
| Fixed-size chunking | kích thước, số chunk, text rỗng, overlap và kiểu trả về |
| Sentence/Recursive | giữ dạng list/string, giới hạn câu, separator và fallback |
| EmbeddingStore | add, search, score giảm dần, top-k, filter và delete |
| Agent/similarity | câu trả lời không rỗng, cosine 1/-1/0 và zero-vector |
| Comparator | đủ ba chiến lược, count dương và `avg_length` |

Đầu ra verbose được tạo trực tiếp bằng lệnh kiểm thử ở trên; repo chỉ giữ báo cáo và mã nguồn, không đưa raw console output vào commit. Kết quả hiện tại được ghi nhận bằng Python **3.14.7** vì máy chưa có Python 3.11; README của lab quy định 3.11 là interpreter chuẩn, nên khi nộp chính thức cần chạy lại đúng Python 3.11 nếu môi trường giảng viên yêu cầu.

Ngoài test tự động, tôi đã chạy smoke test `python main.py "Chunking là gì?"`: chương trình thoát bình thường, nạp 5 tài liệu demo, thực hiện search và gọi agent. File demo `data/customer_support_playbook.txt` bị bỏ qua vì không tồn tại/không đúng corpus hiện tại; cảnh báo này không làm pipeline lỗi.

---

## 4. Dự đoán độ tương tự (Similarity Predictions) — Cá nhân (5 điểm)

Để đánh giá nhất quán với output của `MockEmbedder`, tôi dùng quy ước đơn giản: cặp dự đoán **cao** được xem là khớp khi score dương; cặp dự đoán **thấp** được xem là khớp khi score âm. Đây chỉ là quy ước đọc output của mock, không phải ngưỡng semantic dùng cho embedding thật.

| Cặp | Câu A | Câu B | Dự đoán | Score thực tế | Kết quả theo quy ước |
|---:|---|---|---|---:|---|
| 1 | Ghi danh các lớp cho học kỳ mới. | Chọn môn để theo học trong kỳ tới. | Cao | -0.0258 | Sai |
| 2 | Học phí học kỳ. | Thời tiết hôm nay. | Thấp | -0.0099 | Đúng |
| 3 | Học phần tiên quyết. | Điều kiện đăng ký môn học. | Cao | 0.1609 | Đúng |
| 4 | Thư viện. | Ký túc xá. | Thấp | 0.3675 | Sai |
| 5 | Hủy học phần. | Hủy môn học. | Cao | 0.0567 | Đúng |

**Kết quả:** 3/5 dự đoán khớp theo quy ước trên.

Điều bất ngờ nhất là cặp 1 có cùng chủ đề đăng ký học phần nhưng score âm, còn cặp 4 không liên quan lại có score dương cao nhất. Nguyên nhân là `MockEmbedder` băm chuỗi bằng MD5 rồi sinh vector giả lập; nó kiểm tra tính ổn định của pipeline chứ không học từ đồng nghĩa, chủ đề hay quan hệ ngữ nghĩa. Vì vậy, kết quả này không chứng minh rằng mô hình embedding thật sẽ đánh giá hai câu đăng ký học phần là không tương đồng. Muốn đánh giá semantic retrieval cần chạy cùng các cặp câu với multilingual embedding hoặc model embedding thương mại.

---

## 5. Kết quả truy xuất của tôi (Competition Results) — Cá nhân (10 điểm)

### 5.1. Thiết lập benchmark

| Thành phần | Cấu hình của tôi |
|---|---|
| Corpus | 6 Markdown trong `data/dang-ky-hoc-phan-final/` |
| Chunker | `RecursiveChunker(chunk_size=350)` |
| Retrieval | `search()` cho Q1–Q4; `search_with_filter()` cho Q5 |
| Filter | Q5: `{"audience": "student"}` |
| Top-k | 3 |
| Embedder | `keyword-hash offline fallback` |
| Agent | extractive `llm_fn` trong `bench.py`, kiểm tra các marker của gold answer |

Thang điểm bám `docs/SCORING.md`: 2 điểm khi chunk liên quan ở top-3, agent đủ ý và gold document ở hạng 1; 1 điểm khi có chunk liên quan nhưng agent thiếu ý hoặc gold không ở hạng 1; 0 điểm khi không có chunk liên quan đạt điều kiện. Marker là proxy minh bạch cho benchmark offline, không thay thế đánh giá ngữ nghĩa thủ công.

Log cá nhân có thể kiểm tra tại [ket_qua_benchmark.txt](../ket_qua_benchmark.txt) và bản đặt tên theo thành viên tại [ket_qua_benchmark_duong_xuan_vinh.txt](../ket_qua_benchmark_duong_xuan_vinh.txt).

### 5.2. Kết quả top-3

| # | Query | Top-3 sau xử lý | Gold/ranking và grounding | Tóm tắt agent | Điểm |
|---:|---|---|---|---|---:|
| 1 | Theo hướng dẫn TDTU, sinh viên được đăng ký học phần ngoài kế hoạch học tập khi nào? | `tdtu#1 .2971`, `tdtu#0 .1907`, `hoasen#0 .1382` | Gold TDTU hạng 1; có các marker “đợt bổ sung”, “còn chỗ”, “không trùng” | Trả đủ điều kiện đăng ký ngoài kế hoạch | **2/2** |
| 2 | Theo quy trình UEL, sau khi đăng ký thành công, sinh viên phải lưu kết quả có mã vạch và được điều chỉnh những gì? | `uel#1 .3110`, `ute#3 .2918`, `uel#0 .2367` | Gold UEL hạng 1; context có “mã vạch” nhưng không bao phủ đủ “hủy môn”, “đổi môn” | Trả được việc lưu kết quả nhưng thiếu phần điều chỉnh | **1/2** |
| 3 | Theo hướng dẫn UTE, kế hoạch đăng ký học phần gồm đăng ký sơ bộ và giai đoạn nào nữa? | `ute#0 .4801`, `ute#1 .4149`, `ute#3 .1313` | Gold UTE hạng 1; có marker “hai giai đoạn”, “đăng ký hoàn chỉnh” | Trả đúng hai giai đoạn | **2/2** |
| 4 | Theo quy định UEH, nếu không đóng học phí đúng hạn thì học phần bị xử lý thế nào, và hạn hủy học phần là bao lâu? | `uel#3 .2729`, `ueh#2 .2493`, `ueh#4 .2391` | Gold UEH hạng 2; top-3 vẫn có “học phí” và “10 ngày” | Agent nêu đúng nội dung nhưng nguồn gold không ở top-1 | **1/2** |
| 5 | Quy định kế hoạch học tập, tổ chức và đăng ký học phần: cần kiểm tra những điều kiện nào trước khi đăng ký? | `ueh#0 .1960`, `hcmut#3 .1744`, `tdtu#1 .1563` | HCMUT hạng 2 nhưng chunk được chọn không chứa đủ “học phí” và “tiên quyết” theo gold marker | Trả điều kiện chung, thiếu các điều kiện then chốt | **0/2** |

**Tổng kết:** có 4/5 query lấy được chunk liên quan theo tiêu chí `expected_doc + gold marker` trong top-3; tổng điểm là **6/10**. Q1 và Q3 đạt trọn điểm; Q2 thiếu coverage trong context; Q4 có bằng chứng nhưng gold document đứng hạng 2; Q5 cho thấy filter đổi candidate set nhưng chưa bảo đảm context đủ ý.

### 5.3. A/B metadata filter ở Q5

| Chế độ | Top-3 |
|---|---|
| Không filter | `hoasen#0`, `ueh#0`, `hcmut#3` |
| `audience=student` | `ueh#0`, `hcmut#3`, `tdtu#1` |

Filter đã loại tài liệu Hoa Sen có `audience=all`, nên candidate set thay đổi và HCMUT vẫn xuất hiện trong top-3. Tuy nhiên, HCMUT chỉ ở hạng 2 và chunk đó không chứa đầy đủ các marker cần cho câu trả lời. Kết quả A/B này cho thấy metadata hữu ích để kiểm soát phạm vi nhưng không thể thay thế embedding semantic hoặc reranker.

---

## 6. Những gì tôi học được và phân tích lỗi

### 6.1. Failure case 1 — query có nhiều ý ở Q2

Q2 đồng thời hỏi hai việc: phải lưu kết quả có mã vạch và ở đợt điều chỉnh được hủy/đổi gì. Retriever ưu tiên chunk chứa từ “mã vạch”; chunk đứng đầu trả lời tốt ý thứ nhất nhưng context không chứa trọn ý thứ hai. Agent vì thế trả lời có grounding nhưng không đầy đủ, được 1/2 thay vì 2/2.

**Cải thiện:** tách query thành hai sub-query (“phải lưu gì?” và “đợt điều chỉnh được thay đổi gì?”), lấy union các chunk rồi rerank; hoặc tăng `top_k` trong bước retrieve rồi giới hạn context sau khi rerank. Cách này phải giữ citation để agent không trộn nhầm nguồn UEL với nguồn trường khác.

### 6.2. Failure case 2 — filter đúng phạm vi nhưng chưa đủ semantic ở Q5

Q5 không nêu rõ trường và dùng từ gần với tiêu đề directory Hoa Sen. Không filter, Hoa Sen đứng top-1; có filter, tài liệu Hoa Sen bị loại nhưng HCMUT vẫn chỉ ở hạng 2 và chunk được chọn chưa chứa đầy đủ điều kiện “tiên quyết” và “học phí”. Đây là lỗi precision/grounding chứ không phải lỗi API filter: filter đã hoạt động đúng, nhưng candidate set sau filter vẫn còn nhiều tài liệu có từ khóa chung.

**Cải thiện:** thêm metadata `institution` và `document_type`, viết query rõ nguồn HCMUT khi mục tiêu là kiểm tra HCMUT, dùng multilingual embedding/reranker, và bổ sung một chunk summary chứa đầy đủ các điều kiện chính. Cần chạy lại A/B sau mỗi thay đổi để biết filter cải thiện recall hay chỉ loại nhiễu.

### 6.3. Giới hạn của thí nghiệm

- `keyword-hash offline fallback` ổn định và không cần API key nhưng chủ yếu dựa trên token; score không đại diện cho semantic embedding thật.
- Corpus chỉ có 6 tài liệu thuộc các trường khác nhau; một số query dễ bị ảnh hưởng bởi tên trường và tiêu đề section.
- Store là in-memory, chưa có persistence/index ANN; kết quả phù hợp quy mô lab, chưa phải thiết kế production.
- Điểm agent dùng marker gold để chấm tái lập; khi đánh giá thực tế cần đọc thủ công câu trả lời, nguồn và mức độ bao phủ ý.

### 6.4. Bài học từ các chiến lược trong nhóm

Qua demo của nhóm, tôi rút ra:

- FixedSize + overlap có kích thước ổn định và đạt điểm benchmark cao nhất trong backend offline hiện tại, nhưng có nguy cơ cắt giữa câu.
- Sentence dễ đọc và phù hợp câu hỏi hỏi một quy trình ngắn.
- Recursive là lựa chọn cân bằng khi tài liệu có đoạn/Markdown không đồng đều.
- Heading/section giữ được nhãn điều khoản, làm kết quả dễ giải thích và truy vết.
- Metadata filter nên được xem là lớp kiểm soát phạm vi trước similarity search, không phải bằng chứng rằng câu trả lời đã đúng.

Nếu làm lại, tôi sẽ giữ pre-filter nhưng kết hợp `institution` với `audience`, dùng query decomposition cho câu hỏi nhiều ý và chạy lại cùng 5 query trên embedding đa ngữ thật.

---

## 7. Tự đánh giá (Phần cá nhân)

| Tiêu chí | Điểm tự đánh giá | Căn cứ |
|---|---:|---|
| Khởi động (Warm-up) | 5 / 5 | Giải thích cosine, ví dụ cao/thấp và kiểm chứng công thức chunking 23/25 |
| Hướng tiếp cận (My Approach) | 10 / 10 | Mô tả các chunker, comparator, store, agent và chiến lược metadata cá nhân |
| Hoàn thiện code (Core Implementation) | 30 / 30 | Bộ test hiện tại vượt qua 42/42 |
| Dự đoán độ tương tự | 3 / 5 | 3/5 dự đoán khớp theo quy ước dấu của mock backend; có reflection về giới hạn |
| Kết quả truy xuất | 6 / 10 | 5 query, top-3, A/B filter và failure analysis được ghi lại |
| **Tổng phần cá nhân** | **54 / 60** | — |

**Kết luận cá nhân:** Tôi đã hoàn thiện pipeline từ chunking, embedding, vector store đến agent grounding và có kết quả benchmark tái lập. Điểm yếu chính không nằm ở việc filter không chạy, mà ở chất lượng biểu diễn/ngữ cảnh của backend offline và khả năng bao phủ nhiều ý trong một query. Đây là cơ sở để cải thiện bằng embedding semantic thật, reranking và metadata giàu hơn.
