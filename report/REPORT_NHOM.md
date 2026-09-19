# Báo Cáo Nhóm — Lab 7: Embedding & Vector Store

**Nhóm:** G11 — chủ đề Đăng ký học phần
**Thành viên:** Nguyễn Thế Hưng, Đinh Tiến Mạnh, Nguyễn Quang Minh, Nguyễn Minh Tuấn, Dương Xuân Vinh
**Ngày:** 19/09/2026

> Báo cáo này là bản tổng hợp chung của nhóm, không ghép nguyên văn các báo cáo cá nhân. Phần mô tả chiến lược, tham số và bài học được đối chiếu từ 5 file report cá nhân hiện có; số liệu retrieval được chuẩn hóa lại bằng `bench.py` và các log benchmark để mọi thành viên dùng cùng corpus, đúng 5 query, cùng `top_k=3` và cùng cách chấm.

### Phạm vi và nguyên tắc chuẩn hóa

- **Corpus chung:** 6 tài liệu Markdown trong `data/dang-ky-hoc-phan-final/`.
- **Năm chiến lược được so sánh:** FixedSize, Recursive, Sentence, Heading/section và Recursive kết hợp metadata filter.
- **Backend benchmark:** `keyword-hash offline fallback`, chạy được không cần API key hay tải model; đây là backend tái lập để so sánh pipeline, không phải semantic embedding production.
- **Quy ước đánh giá:** mỗi query trả về top-3; chunk được xem là liên quan khi thuộc đúng tài liệu gold và chứa marker của đáp án. Điểm 2 yêu cầu chunk gold ở hạng 1 và agent đủ marker; điểm 1 là có chunk liên quan trong top-3 nhưng hạng/đáp án chưa đầy đủ; điểm 0 là không có chunk liên quan đạt điều kiện.

Các report cá nhân là cơ sở để tổng hợp vai trò, rationale và bài học của từng thành viên. Khi cách diễn đạt query hoặc số tự đánh giá giữa các bản cá nhân khác nhau, báo cáo nhóm dùng bộ query và kết quả có thể tái lập trong `bench.py`, không tự cộng ghép các số liệu khác chuẩn.

## 1. Lựa chọn tài liệu

### Chủ đề và lý do chọn

**Chủ đề:** Đăng ký học phần.

Nhóm chọn chủ đề này vì có nhiều hướng dẫn công khai từ các trường đại học Việt Nam, có cấu trúc và thuật ngữ gần nhau nhưng khác nhau về quy trình. Đây là corpus phù hợp để kiểm tra truy xuất theo nguồn, chunking theo câu/heading và lọc metadata theo đối tượng sinh viên.

### Danh sách tài liệu

| # | Tên tài liệu | Nguồn | Ngày lấy / phiên bản | Số ký tự | Metadata chính |
|---|---|---|---|---:|---|
| 1 | HCMUT Course Registration Rules and Guide | [myBK](https://mybk.hcmut.edu.vn/bksi/public/vi/article/82) | 19/09/2026 / not-stated | 1.025 | student, academic-affairs, course-registration |
| 2 | Hoa Sen Academic Regulations Directory | [Hoa Sen](https://www.hoasen.edu.vn/dtdh/van-ban-bieu-mau/quy-dinh/) | 19/09/2026 / not-stated | 510 | all, academic-affairs, regulations |
| 3 | TDTU Student Course Registration Guide | [TDTU](https://undergrad.tdtu.edu.vn/huong-dan/huong-dan-sv-dang-ky-mon-hoc) | 19/09/2026 / not-stated | 701 | student, academic-affairs, course-registration |
| 4 | UEH Course Registration and Cancellation Regulation | [UEH](https://daotao.ueh.edu.vn/quy-dinh-dang-ky-va-huy-hoc-phan-da-dang-ky-cua-sinh-vien-dai-hoc-chinh-quy-trong-dao-tao-theo-he-thong-tin-chi-tai-truong-dai-hoc-kinh-te-tp-ho-chi-minh/) | 19/09/2026 / not-stated | 1.457 | student, academic-affairs, cancellation |
| 5 | UEL Main-Semester Course Registration Process | [UEL](https://pdt.uel.edu.vn/dai-hoc-chinh-quy-2370/quy-trinh-dang-ky-mon-hoc-hoc-ky-chinh) | 19/09/2026 / not-stated | 1.096 | student, academic-affairs, course-registration |
| 6 | UTE Course Registration Guide | [UTE](https://daotao.ute.udn.vn/reghelp.htm) | 19/09/2026 / not-stated | 906 | student, academic-affairs, course-registration |

Corpus chỉ dùng nội dung công khai, không chứa dữ liệu cá nhân, thông tin đăng nhập hay tài liệu nội bộ. Mỗi file có front matter với `doc_id`, `title`, `source_url`, `retrieved_at`, `document_version`, `audience` và các trường bổ sung. `sources.csv` ánh xạ 1–1 tới 6 file Markdown. Nguồn nào không công bố phiên bản được ghi đúng là `not-stated`; không tự suy đoán phiên bản.

### Cấu trúc metadata

| Trường | Kiểu | Ví dụ | Ích lợi cho retrieval |
|---|---|---|---|
| `doc_id` | string | `ueh-course-registration-regulation` | Định danh ổn định để truy vết chunk và xóa tài liệu |
| `title` | string | `UTE Course Registration Guide` | Bổ sung ngữ cảnh tên nguồn vào chunk |
| `source_url` | string | URL trang trường | Kiểm chứng và trích dẫn nguồn |
| `retrieved_at` | date | `2026-09-19` | Biết thời điểm thu thập |
| `document_version` | string | `not-stated` | Không nhầm ngày lấy với phiên bản văn bản |
| `audience` | enum/string | `student`, `all` | Cho phép `metadata_filter={"audience":"student"}` |
| `department` | string | `academic-affairs` | Lọc theo đơn vị nghiệp vụ |
| `category` | string | `course-registration` | Lọc theo loại nội dung |
| `language` | string | `vi` | Chọn ngôn ngữ khi mở rộng corpus |

## 2. Thiết kế chiến lược

### Phân tích đường cơ sở

Chạy `ChunkingStrategyComparator().compare(text, chunk_size=350)` trên ba tài liệu đầu tiên. Theo cài đặt của comparator, FixedSize dùng overlap `350 // 10 = 35` ký tự; đây là đường cơ sở, khác với cấu hình cá nhân của Nguyễn Thế Hưng dùng overlap 50.

| Tài liệu | Chiến lược | Số chunk | Độ dài trung bình | Nhận xét |
|---|---|---:|---:|---|
| HCMUT | FixedSize | 4 | 282,5 | Đều kích thước, nhưng có thể cắt giữa câu |
| HCMUT | Sentence | 3 | 339,0 | Giữ câu, chunk dài gần giới hạn |
| HCMUT | Recursive | 4 | 254,8 | Tách theo cấu trúc xuống dần |
| Hoa Sen | FixedSize | 2 | 272,5 | Phù hợp văn bản ngắn |
| Hoa Sen | Sentence | 2 | 254,0 | Giữ được câu/ý ngắn |
| Hoa Sen | Recursive | 2 | 254,0 | Kết quả tương đương Sentence |
| TDTU | FixedSize | 3 | 257,0 | Có overlap nên giảm rủi ro mất biên |
| TDTU | Sentence | 2 | 348,0 | Ít chunk, ngữ cảnh rộng |
| TDTU | Recursive | 3 | 232,3 | Cân bằng giữa cấu trúc và kích thước |

### Chiến lược và phân công

**Nguyễn Thế Hưng — FixedSize + overlap**

- Dùng `FixedSizeChunker(chunk_size=350, overlap=50)`.
- Cách này đơn giản, ổn định về kích thước embedding và giữ lại một phần ngữ cảnh ở biên chunk.

**Đinh Tiến Mạnh — Recursive**

- Dùng thứ tự separator `\n\n`, `\n`, `. `, khoảng trắng rồi cắt cứng.
- Phù hợp tài liệu hướng dẫn vì ưu tiên giữ đoạn và câu trước khi cắt theo ký tự.

**Nguyễn Quang Minh — Sentence**

- Gom tối đa ba câu/chunk bằng regex nhận diện dấu `.`, `!`, `?`.
- Phù hợp query hỏi một quy trình hoặc điều kiện vì câu trả lời thường nằm trong vài câu liên tiếp.

**Nguyễn Minh Tuấn — Heading/section**

- Giữ heading Markdown cùng phần nội dung; chỉ dùng Recursive khi một section quá dài.
- Giữ được nhãn như “Điều kiện đăng ký”, “Hai giai đoạn đăng ký”, giúp truy xuất theo chủ đề rõ hơn.

**Dương Xuân Vinh — Metadata-filtered retrieval**

- Dùng Recursive làm chunker nền; điểm khác biệt so với Recursive thuần của Đinh Tiến Mạnh là lọc `audience=student` trước khi tính similarity cho câu hỏi cần nội dung dành cho sinh viên.
- Lọc trước giúp loại tài liệu tổng quát khỏi candidate set và minh họa đúng yêu cầu metadata retrieval.

### Cấu hình chạy benchmark của từng thành viên

| Thành viên | Cấu hình chunk/retrieval | Tổng chunk lưu trong store | Vai trò khi so sánh |
|---|---|---:|---|
| Nguyễn Thế Hưng | `FixedSizeChunker(350, overlap=50)` | 21 | Baseline có overlap được tinh chỉnh |
| Đinh Tiến Mạnh | `RecursiveChunker(350)` | 23 | Giữ đoạn/câu trước khi cắt cứng |
| Nguyễn Quang Minh | `SentenceChunker(max_sentences_per_chunk=3)` | 21 | Giữ ranh giới câu |
| Nguyễn Minh Tuấn | `HeadingChunker(350)`; section dài fallback Recursive | 23 | Khai thác heading Markdown |
| Dương Xuân Vinh | `RecursiveChunker(350)` + `audience=student` ở Q5 | 23 | Đánh giá tác động của pre-filter |

Tổng chunk là số đo của lần chạy benchmark, không phải tiêu chí “càng nhiều càng tốt”. Chunk ít hơn thường dễ quản lý hơn; chunk nhiều hơn có thể giữ ngữ cảnh tốt hơn nhưng làm tăng chi phí embedding và số ứng viên cần xếp hạng.

### So sánh

| Thành viên | Chiến lược | Điểm benchmark tổng hợp (/10) | Điểm mạnh | Điểm yếu |
|---|---|---:|---|---|
| Nguyễn Thế Hưng | FixedSize + overlap | 8 / 10 | 5 câu có chunk liên quan; Q1/Q3/Q4 agent đủ marker | Q2/Q5 còn thiếu chi tiết |
| Đinh Tiến Mạnh | Recursive | 6 / 10 | Q1/Q3 agent đủ marker | Q4 gold doc hạng 2; Q5 chưa đủ marker |
| Nguyễn Quang Minh | Sentence | 7 / 10 | Q1/Q3/Q4 agent đủ marker | Q5 không đưa HCMUT vào top-3 |
| Nguyễn Minh Tuấn | Heading/section | 6 / 10 | Q1/Q3 agent đủ marker | Q4 gold doc hạng 2; Q5 bị nhiễu |
| Dương Xuân Vinh | Metadata-filtered + Recursive | 6 / 10 | Filter đổi candidate set ở Q5; Q1/Q3 đủ marker | Filter chưa đủ thay thế embedding ngữ nghĩa |

Với corpus nhỏ này, các chiến lược đều lấy được chunk liên quan ở bốn câu đầu. Chấm hai mức cho thấy FixedSize đạt 8/10, Sentence 7/10, Recursive/Heading/Filtered 6/10. Sentence thuận lợi cho câu hỏi quy trình; metadata filter có giá trị kiểm soát phạm vi nhưng không tự thay thế embedding ngữ nghĩa.

### Ma trận điểm theo query

| Thành viên / chiến lược | Q1 | Q2 | Q3 | Q4 | Q5 | Tổng |
|---|---:|---:|---:|---:|---:|---:|
| Nguyễn Thế Hưng — FixedSize | 2 | 1 | 2 | 2 | 1 | **8/10** |
| Đinh Tiến Mạnh — Recursive | 2 | 1 | 2 | 1 | 0 | **6/10** |
| Nguyễn Quang Minh — Sentence | 2 | 1 | 2 | 2 | 0 | **7/10** |
| Nguyễn Minh Tuấn — Heading/section | 2 | 1 | 2 | 1 | 0 | **6/10** |
| Dương Xuân Vinh — Filtered Recursive | 2 | 1 | 2 | 1 | 0 | **6/10** |

### Bằng chứng top-3 của từng chiến lược

Bảng dưới đây rút gọn trực tiếp từ các log riêng của 5 thành viên. Mã nguồn được viết tắt (`tdtu`, `uel`, `ute`, `ueh`, `hcmut`, `hoasen`) và đi kèm `#chunk_index`; số trong ngoặc là similarity score. Với Q5, cột “top-3 dùng” là kết quả **sau** `metadata_filter={"audience":"student"}`.

| Query | Hưng — FixedSize | Mạnh — Recursive | Quang — Sentence | Tuấn — Heading | Vinh — Filtered Recursive |
|---:|---|---|---|---|---|
| Q1 | `tdtu#1 (.2373), tdtu#0 (.1819), ute#0 (.1754)`; gold hạng 1; **2/2** | `tdtu#1 (.2971), tdtu#0 (.1907), hoasen#0 (.1382)`; hạng 1; **2/2** | `tdtu#0 (.2774), ute#0 (.2288), tdtu#1 (.1445)`; hạng 1; **2/2** | `tdtu#1 (.3977), tdtu#2 (.2558), hoasen#0 (.1382)`; hạng 1; **2/2** | `tdtu#1 (.2971), tdtu#0 (.1907), hoasen#0 (.1382)`; hạng 1; **2/2** |
| Q2 | `uel#0 (.3482), ute#2 (.3093), uel#1 (.2666)`; gold hạng 1, agent thiếu hủy/đổi; **1/2** | `uel#1 (.3110), ute#3 (.2918), uel#0 (.2367)`; hạng 1, agent thiếu hủy/đổi; **1/2** | `uel#1 (.4753), ute#2 (.3035), hcmut#2 (.2965)`; hạng 1, agent thiếu hủy/đổi; **1/2** | `uel#0 (.3527), ute#3 (.3035), hcmut#3 (.2659)`; hạng 1, agent thiếu hủy/đổi; **1/2** | `uel#1 (.3110), ute#3 (.2918), uel#0 (.2367)`; hạng 1, agent thiếu hủy/đổi; **1/2** |
| Q3 | `ute#0 (.4996), ute#1 (.1471), ute#2 (.1275)`; hạng 1; **2/2** | `ute#0 (.4801), ute#1 (.4149), ute#3 (.1313)`; hạng 1; **2/2** | `ute#0 (.5407), ute#1 (.2212), ute#2 (.1251)`; hạng 1; **2/2** | `ute#1 (.4868), ute#0 (.4801), ute#2 (.1858)`; hạng 1; **2/2** | `ute#0 (.4801), ute#1 (.4149), ute#3 (.1313)`; hạng 1; **2/2** |
| Q4 | `ueh#2 (.2864), ueh#3 (.2555), hcmut#3 (.2425)`; hạng 1; **2/2** | `uel#3 (.2729), ueh#2 (.2493), ueh#4 (.2391)`; gold hạng 2; **1/2** | `ueh#2 (.3621), uel#5 (.3351), ueh#3 (.2391)`; hạng 1; **2/2** | `uel#2 (.2918), ueh#4 (.2500), ueh#2 (.2477)`; gold hạng 2; **1/2** | `uel#3 (.2729), ueh#2 (.2493), ueh#4 (.2391)`; gold hạng 2; **1/2** |
| Q5 | `ueh#0 (.2179), tdtu#1 (.1855), hcmut#0 (.1591)`; gold hạng 3, agent thiếu marker; **1/2** | `ueh#0 (.1960), hcmut#3 (.1744), tdtu#1 (.1563)`; gold marker không có; **0/2** | `tdtu#0 (.2145), ueh#0 (.1953), ute#0 (.1652)`; HCMUT không vào top-3; **0/2** | `tdtu#1 (.2332), tdtu#2 (.2060), hcmut#3 (.1592)`; gold marker không có; **0/2** | `ueh#0 (.1960), hcmut#3 (.1744), tdtu#1 (.1563)`; gold marker không có; **0/2** |

Chi tiết câu trả lời agent, gold answer và toàn bộ context vẫn được giữ trong [ket_qua_benchmark_nhom.txt](../ket_qua_benchmark_nhom.txt) và 5 log cá nhân. Như vậy bảng nhóm vừa có ma trận điểm dễ so sánh, vừa có bằng chứng top-3 để kiểm tra lại kết luận.

## 3. Câu hỏi đánh giá và chất lượng truy xuất

| # | Câu hỏi | Gold answer rút gọn | Chunk/nguồn liên quan |
|---|---|---|---|
| 1 | Theo hướng dẫn TDTU, sinh viên được đăng ký học phần ngoài kế hoạch học tập khi nào? | Chỉ được đăng ký môn đã có trong kế hoạch học tập; môn ngoài kế hoạch chỉ được thêm ở đợt bổ sung nếu còn chỗ và không trùng thời khóa biểu. | `tdtu-course-registration-guide` — `## Đăng ký theo kế hoạch học tập` |
| 2 | Theo quy trình UEL, sau khi đăng ký thành công, sinh viên phải lưu kết quả có mã vạch và được điều chỉnh những gì? | Sinh viên phải xuất kết quả đăng ký có mã vạch để lưu; ở đợt điều chỉnh có thể hủy môn hoặc đổi môn tự chọn nhưng không được đăng ký bổ sung môn mới. | `uel-course-registration-process` — `## Quy trình chính` |
| 3 | Theo hướng dẫn UTE, kế hoạch đăng ký học phần gồm đăng ký sơ bộ và giai đoạn nào nữa? | Kế hoạch gồm hai giai đoạn: đăng ký sơ bộ và đăng ký hoàn chỉnh, trong đó giai đoạn sau dùng để điều chỉnh và hoàn tất đăng ký. | `ute-course-registration-guide` — `## Hai giai đoạn đăng ký` |
| 4 | Theo quy định UEH, nếu không đóng học phí đúng hạn thì học phần bị xử lý thế nào, và hạn hủy học phần là bao lâu? | UEH có thể hủy học phần chưa đóng học phí đúng hạn; yêu cầu hủy học phần phải theo thời hạn, thường là 10 ngày trước mốc thời khóa biểu hoặc kỳ thi tùy trường hợp. | `ueh-course-registration-regulation` — `## Đăng ký bổ sung và hủy học phần` |
| 5 | Quy định kế hoạch học tập, tổ chức và đăng ký học phần: cần kiểm tra những điều kiện nào trước khi đăng ký? | Cần kiểm tra trạng thái học tập, điều kiện tiên quyết hoặc học phần trước, chuẩn ngoại ngữ/công nghệ thông tin nếu áp dụng, chuẩn giáo dục thể chất/quốc phòng và tình trạng học phí. Query dùng filter `audience=student`. | `hcmut-course-registration-rules` — `## Điều kiện và chuẩn bị` |

### Bằng chứng gold answer trong corpus

| Query | Trích đoạn kiểm chứng |
|---:|---|
| Q1 | TDTU: “Môn chưa có trong kế hoạch chỉ được đăng ký thêm ở đợt bổ sung, khi môn còn chỗ và không trùng thời khóa biểu...” |
| Q2 | UEL: “sinh viên bắt buộc xuất kết quả đăng ký và lưu bản có mã vạch”; ở đợt điều chỉnh “được hủy môn hoặc đổi môn tự chọn”. |
| Q3 | UTE: “kế hoạch đăng ký môn học gồm hai giai đoạn”, gồm “Đăng ký sơ bộ” và “Đăng ký hoàn chỉnh”. |
| Q4 | UEH: “quá hạn, trường có thể hủy các học phần chưa đóng học phí” và quy định các mốc “10 ngày”. |
| Q5 | HCMUT: điều kiện gồm “tình trạng học tập”, “học phần tiên quyết hoặc học phần học trước”, các chuẩn liên quan và “tình trạng học phí”. |

Cả 5 gold answer đều được trích hoặc đối chiếu trực tiếp từ 6 file trong `data/dang-ky-hoc-phan-final/`; nhóm không suy đoán quy định ngoài corpus.

| # | Chiến lược tốt nhất | Chunk liên quan trong top-3 | Agent answer / điểm |
|---:|---|---|---|
| 1 | Tất cả | Có, cả 5 chiến lược | Agent đủ marker; 2/2 cho tất cả |
| 2 | Tất cả | Có, cả 5 chiến lược | Có mã vạch nhưng thiếu đủ hủy/đổi môn; 1/2 |
| 3 | Tất cả | Có, cả 5 chiến lược | Agent đủ hai marker; 2/2 cho tất cả |
| 4 | FixedSize / Sentence | Có, cả 5 chiến lược | FixedSize/Sentence gold hạng 1: 2/2; ba chiến lược còn lại hạng 2: 1/2 |
| 5 | FixedSize | FixedSize có chunk gold hạng 3; bốn chiến lược còn lại không có marker gold | FixedSize 1/2; các chiến lược còn lại 0/2 |

Kết quả benchmark đầy đủ của nhóm nằm ở [ket_qua_benchmark_nhom.txt](../ket_qua_benchmark_nhom.txt). Log riêng có thể kiểm tra tại: [Hưng](../ket_qua_benchmark_nguyen_the_hung.txt), [Mạnh](../ket_qua_benchmark_dinh_tien_manh.txt), [Quang](../ket_qua_benchmark_nguyen_quang_minh.txt), [Tuấn](../ket_qua_benchmark_nguyen_minh_tuan.txt) và [Vinh](../ket_qua_benchmark_duong_xuan_vinh.txt). Mã tái lập là [bench.py](../bench.py). Benchmark dùng `keyword-hash offline fallback`, không tải model và không cần API key. Điểm agent answer dùng các marker bắt buộc làm proxy minh bạch, không phải đánh giá ngữ nghĩa hoàn hảo; khi dùng model embedding thật, nhóm cần chạy lại.

Metadata filter giúp ở câu 5: câu hỏi không nêu người hỏi, top-1 unfiltered thường là tài liệu Hoa Sen `audience=all`, còn filtered loại tài liệu đó và đổi candidate set sang các tài liệu `student`. A/B top-3 được ghi trong từng file benchmark. Tuy nhiên filter không bảo đảm top-1 đúng; chất lượng cuối vẫn phụ thuộc chunking và embedding.

| Chiến lược | Top-3 không filter | Top-3 có `audience=student` |
|---|---|---|
| FixedSize | `hoasen#0, ueh#0, tdtu#1` | `ueh#0, tdtu#1, hcmut#0` |
| Recursive | `hoasen#0, ueh#0, hcmut#3` | `ueh#0, hcmut#3, tdtu#1` |
| Sentence | `hoasen#0, tdtu#0, ueh#0` | `tdtu#0, ueh#0, ute#0` |
| Heading | `hoasen#0, tdtu#1, tdtu#2` | `tdtu#1, tdtu#2, hcmut#3` |
| Filtered Recursive | `hoasen#0, ueh#0, hcmut#3` | `ueh#0, hcmut#3, tdtu#1` |

### A/B và failure analysis

**A/B câu 5:** Với FixedSize, top-3 unfiltered là `hoasen#0, ueh#0, tdtu#1`; sau filter là `ueh#0, tdtu#1, hcmut#0`. Với Recursive và chiến lược Filtered, unfiltered là `hoasen#0, ueh#0, hcmut#3`; sau filter là `ueh#0, hcmut#3, tdtu#1`. Sentence đổi từ `hoasen#0, tdtu#0, ueh#0` thành `tdtu#0, ueh#0, ute#0`; Heading đổi từ `hoasen#0, tdtu#1, tdtu#2` thành `tdtu#1, tdtu#2, hcmut#3`.

**Failure case thật — câu 5 với Sentence:** Không lọc, Hoa Sen đứng top-1 vì tiêu đề “Quy định kế hoạch học tập, tổ chức và đăng ký học phần” gần query; sau lọc, HCMUT vẫn không vào top-3. Nguyên nhân là keyword-hash chỉ nhìn từ vựng và corpus có tài liệu `all` dạng directory, không hiểu rằng câu hỏi cần hướng dẫn điều kiện dành cho sinh viên. Cách sửa là dùng embedding đa ngôn ngữ thật/reranker, đồng thời bổ sung nguồn `all` có nội dung tương phản rõ và nguồn `student` chi tiết hơn.

**Failure case thứ hai — câu 2:** UEL có chunk chứa “mã vạch” ở top-1 nhưng câu về hủy/đổi môn không vào context được chọn, nên agent answer chỉ trả phần lưu kết quả. Nguyên nhân là query có nhiều ý nhưng lexical ranking ưu tiên câu chứa mã vạch. Cách sửa là query decomposition hoặc reranker ưu tiên đủ các ý trong gold answer, sau đó mới tổng hợp câu trả lời.

## 4. Demo và bài học nhóm

- Cùng một corpus nhưng các chiến lược đều lấy được chunk liên quan ở bốn câu đầu; theo chấm hai mức, FixedSize đạt 8/10, Sentence 7/10 và ba chiến lược còn lại 6/10. Chênh lệch đến từ rank của gold doc và khả năng bao phủ đủ các ý trong câu trả lời.
- Heading chunker giữ được tên section, còn Recursive an toàn hơn với HTML/Markdown đã mất cấu trúc.
- Metadata có thể dùng như một lớp kiểm soát phạm vi trước similarity search; không nên coi nó là bằng chứng cho câu trả lời.

### Kịch bản demo có thể tái lập

1. Chạy `python -m pytest tests/ -q -p no:cacheprovider` để chứng minh phần code lõi vượt qua **42/42 tests**.
2. Chạy `python bench.py --strategy all` để trình bày cùng 5 query, top-3 và điểm của cả 5 chiến lược.
3. Mở Q5 và chạy đối chiếu `search()` với `search_with_filter(..., {"audience": "student"})` để minh họa metadata làm thay đổi candidate set nhưng chưa bảo đảm top-1.
4. Chạy `python main.py "Chunking là gì?"` để minh họa luồng nạp tài liệu → chunking → vector store → agent; cảnh báo bỏ qua file demo không tương thích định dạng được xem là bình thường theo hướng dẫn lab.

Trong phần trình bày, nhóm cần nói rõ benchmark hiện dùng fallback offline nên không kết luận rằng FixedSize luôn tốt hơn về semantic retrieval. Kết luận có giá trị trong phạm vi corpus, query và backend đã nêu; nếu đổi embedding backend, phải chạy lại benchmark.

Qua so sánh, chunking không chỉ là chọn kích thước. Với tài liệu có heading tốt, giữ heading giúp giải thích kết quả; với tài liệu lộn xộn, Recursive/overlap ít brittle hơn. Nếu làm lại, nhóm sẽ bổ sung 2–4 nguồn cùng một trường đại học, lưu snapshot HTML hợp lệ và chạy thêm backend embedding đa ngôn ngữ để đánh giá semantic retrieval.

## Tự đánh giá phần nhóm

| Tiêu chí | Điểm tự đánh giá |
|---|---:|
| Lựa chọn tài liệu | 9 / 10 |
| Thiết kế chiến lược | 13 / 15 |
| Chất lượng truy xuất | 8 / 10 |
| Thuyết trình/demo | 4 / 5 |
| **Tổng** | **34 / 40** |
