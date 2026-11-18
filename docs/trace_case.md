# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Case đã làm: `seeded_regression C-002@11` (FM-03)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`. Lỗi này cũng có trong baseline: `swarm C-002@55`. Run ID `E-seeded_regression-20261118-be71` (`reports/eval_seeded_regression.json`, eval set `be7107d122e5`); baseline `E-swarm-20261118-be71` |
| Triệu chứng | Grader Lab 8 FAIL `status resolved != denied`. Reply: "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." Ledger: `refund_vnd=20000`, `refund_count=1`. Label: `denied`, `refund_vnd=0`, `refund_count=0`. Lặp lại ở cả 5 seed |
| Bước sai đầu tiên | **Event 3 `model_override`**, payload `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` đúng (task `check_applicable_policy`, chỉ cho tool đọc). Event 2 `investigator` đọc DB đúng: O-202 `delay_days=2` (dưới mức được hoàn). Event 3 là lần đầu agent bỏ dữ kiện DB để lấy số "5 ngày" do khách tự khai trong ticket. Event 4 `quote` 20.000 theo SHIP-LATE-03 chỉ là hệ quả: tính đúng trên dữ kiện sai |
| Failure mode | FM-03 ticket_trust (layer model/prompt), xem `docs/failure_taxonomy.md` |
| Đối chứng | `fixed C-002@11`: event 2 giống hệt (`delay_days=2`), **không có** `model_override`; event 3 `quote {"amount_vnd": 0, "reason": "no_entitlement"}`; event 4 reply "chưa đủ điều kiện hoàn"; ledger 0, Lab 8 PASS |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_c002_ticket_trust_is_caught_on_seeded_regression` assert có `model_override` ngay sau event đọc DB `delay_days=2` và ledger ≠ label; `test_c002_fixed_keeps_the_db_fact` assert `fixed` không override, ledger = 0, `denied`. **Đã chạy: 2 passed**. Trong eval set, item E-002 (FM-03) được grader `db_fact_kept` (bước) và `refund_amount_correct` (ledger) bắt cùng lỗi này |
| Chưa chắc chắn | Trace không ghi lý do agent chọn tin ticket (MockLLM không có reasoning). Với `swarm`, override chỉ xảy ra ở `seed % 5 == 0`, nên 5 seed chỉ có đúng 1 trial lộ lỗi: tỉ lệ thật trên model thật có thể khác. Bản `quiet_override` (cùng lỗi nhưng không ghi event) sẽ qua `db_fact_kept`; khi đó chỉ ledger-level grader bắt được |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
