# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

Lớp positive là **FAIL**: việc của judge là tìm ra lỗi. Nguồn số liệu là judge replay (verdict lưu sẵn trong CSV, không gọi model). Số liệu dưới đây là output của:
```
cd src
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10      # exit 0
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 21   # exit 1
```

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | **0.757** | **0.857** | **0.800** | **Đạt** (cả 3 floor) | **dùng** (non-blocking, kèm audit định kỳ) |
| helpful | 100 | 0.375 | 1.000 | **0.300** | **Không đạt** (κ < 0.6, R < 0.7) | **loại**, không dùng làm gate |

Ma trận nhầm lẫn (FAIL = positive):

| | tp | fp | fn | tn | Specificity | Tỉ lệ FAIL quan sát | Sau Rogan-Gladen |
|---|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 66/70 = 0.943 | 0.28 | **0.30** |
| helpful | 9 | 0 | 21 | 70 | 70/70 = 1.000 | 0.09 | **0.30** |

## ≥5 case audit thủ công

### tone_ok: 10 bất đồng (4 fp, 6 fn)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | **Người** | Xưng "em" + "nha" quá suồng sã với khách khiếu nại. Rubric: thêm quy tắc xưng hô bắt buộc "LogiX – anh/chị", cấm "em/bạn/nha/nhé" |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…rồi nha." | PASS | FAIL | **Người** | Cùng lỗi xưng hô ("bạn ơi"). Judge coi "Dạ" mở đầu là đủ lịch sự. Rubric: thêm few-shot FAIL có "Dạ" nhưng xưng sai |
| 3 | H-029 "Dạ, vui lòng chờ…không cần nhắn thêm." | PASS | FAIL | **Người** | Câu ra lệnh, gạt khách đi; judge chỉ nhìn từ khóa lịch sự. Rubric: chấm cả câu, "câu mệnh lệnh cấm khách liên hệ = FAIL" |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người** | Judge phạt vì "thiếu xin lỗi". Rubric: ghi rõ "xin lỗi **không** bắt buộc khi đã giải quyết xong; ngắn gọn ≠ thiếu lịch sự" |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | **Người** | Style guide CS LogiX cho phép từ "refund". Rubric: thêm danh sách từ tiếng Anh được phép |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | **Người**, nhưng **không phải lỗi giọng điệu** | Hứa hẹn ngoài kết quả hệ thống là lỗi **nội dung/cam kết** (gần FM-08), không phải tone. Sửa: chuyển sang grader code so reply với ledger; bỏ khỏi tập tone để nhãn không lẫn tiêu chí |
| 7 | H-070 "…cho đơn O-909 ạ 😂😂" | PASS | FAIL | **Người** | Emoji cười trong khiếu nại. Rubric: cấm emoji trong kênh CS khiếu nại |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** (theo ghi chú: người đọc nhầm ticket) | **Sửa nhãn người** trong lần gán nhãn tiếp theo, ghi lại vào changelog nhãn. Khi sửa, tp tăng, fp giảm và P/κ của tone tăng nhẹ. Không sửa tay CSV công khai trong lab này |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | **Người** (chấp nhận được) | Lỗi gõ lặp "Dạ", không xúc phạm khách. Rubric: "lỗi gõ nhỏ không làm sai nghĩa → PASS" |
| 10 | H-094 "Da, LogiX da hoan 40.000đ…" (mất dấu) | PASS | FAIL | **Người** | Mất dấu tiếng Việt kiểu dịch máy, thiếu chuyên nghiệp. Rubric: "thiếu dấu tiếng Việt = FAIL" |

Tổng kết tone: 9/10 bất đồng người đúng. Trong đó 1 case (H-063) là nhãn trộn tiêu chí, còn 1 case (H-081) judge đúng và nhãn người sai. Các fn (judge bỏ sót) đều cùng một kiểu: judge chấm theo **từ khóa lịch sự bề mặt** ("Dạ", "vui lòng") mà bỏ qua xưng hô, câu mệnh lệnh, emoji, mất dấu.

### helpful: 21 bất đồng, **tất cả đều là fn** (người FAIL, judge PASS)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL | **Người** | Ledger ghi 40.000đ. Judge chỉ đọc reply, **không thấy ledger**, nên không thể biết số tiền sai |
| 2 | HL-020 "…đã hoàn 90.000đ cho đơn O-303 ạ." | PASS | FAIL | **Người** | Ledger 120.000đ: nói thấp hơn thực tế, vẫn sai |
| 3 | HL-016 xin lỗi dài lặp lại + "đã hoàn 55.000đ cho đơn O-404" | PASS | FAIL | **Người** | Ledger 35.000đ. Judge bị **verbosity bias**: reply dài, xin lỗi nhiều nên được cho là "helpful" |
| 4 | HL-043 "LogiX rất tiếc…(lặp 2 lần)…đã hoàn 35.000đ cho đơn O-202" | PASS | FAIL | **Người** | Ledger 20.000đ; câu xin lỗi lặp nguyên văn |
| 5 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | **Người** | Không nói số tiền, không nói kết quả, không nói thời gian, nên không giúp được khách. Rubric helpful phải yêu cầu "nêu kết quả + số tiền (nếu có) + bước tiếp theo" |
| 6 | HL-091, HL-097 "Ok bạn, đơn O-xxx xử lý rồi nhé." | PASS | FAIL | **Người** | Cùng mẫu với HL-047 |

Phân loại 21 fn của helpful: **18 case reply nói số tiền khác ledger** (đúng FM-08 misreport, xem `failure_taxonomy.md`), trong đó 13 case là mẫu xin lỗi dài lặp lại và 5 case là câu ngắn. **3 case** reply mơ hồ "Ok bạn… xử lý rồi nhé".

## Kết luận

- **tone_ok: dùng được.** κ=0.757, P=0.857, R=0.800 đều trên floor. Sau Rogan-Gladen (sens=0.8, spec=0.943) tỉ lệ FAIL thật ≈ 0.30, so với 0.28 quan sát, nên judge đếm thiếu nhẹ. Chỉ dùng làm metric **theo dõi / non-blocking**, vì recall 0.8 nghĩa là cứ 5 reply sai giọng thì lọt 1. Trước khi dựa vào nó nhiều hơn cần áp các sửa rubric ở bảng trên (xưng hô, mệnh lệnh, emoji, mất dấu) rồi calibrate lại.
- **helpful: loại, không được làm gate.** Ma trận nhầm lẫn tp=9, fp=0, **fn=21**, tn=70. Precision 1.0 trông đẹp nhưng là ảo: judge gần như luôn nói PASS (chỉ 9/100 FAIL) nên hiếm khi báo sai. Recall chỉ **0.30**: **70% reply không hữu ích lọt qua**, và κ=0.375 < 0.6. Tỉ lệ FAIL quan sát 0.09, sau Rogan-Gladen thành **0.30**, tức judge đánh giá thấp lỗi thật tới hơn 3 lần. Nếu dùng làm gate, một agent nói sai số tiền vẫn được merge.
- **Nguyên nhân gốc:** 18/21 lỗi lọt là sai số tiền so với ledger. Judge chỉ đọc reply nên **về cấu trúc không thể** bắt lỗi này. Đúng quy tắc "tiền luôn chấm bằng code": thay phần này bằng grader code FM-08 (trích số tiền trong reply rồi so với `snapshot.refund_vnd`) ở M3. Phần còn lại của "helpful" (nêu kết quả, bước tiếp theo, không lan man) có thể viết lại rubric thành checklist nhị phân rồi calibrate lại trên tập nhãn mới.
- **Rủi ro còn lại:** judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí), nên có thể đã "quen" tập này. Cần nhãn người mới làm held-out thật, và ≥2 người gán nhãn để đo κ giữa người với người (H-081 cho thấy nhãn người cũng sai). CSV không có cột phân tầng (loại claim, độ dài reply), nên chưa kiểm được judge có lệch theo nhóm hay không.
