Dựa trên nội dung từ tài liệu **day08_langgraph_student.pdf**, dưới đây là tóm tắt đầy đủ và chính xác các nội dung thực hành (Lab) trong buổi học về LangGraph & Agentic Orchestration:

### 1. Mục tiêu cốt lõi của bài thực hành
Mục tiêu chính là xây dựng một **workflow LangGraph cho agent xử lý yêu cầu hỗ trợ (support ticket)**. Hệ thống này không chỉ thực hiện tác vụ đơn giản mà phải tích hợp các tính năng nâng cao sau:
*   **Routing (Định hướng động):** Phân loại yêu cầu để đi theo các nhánh xử lý khác nhau (ví dụ: câu hỏi dễ, cần công cụ, hoặc hành động rủi ro).
*   **Human-in-the-Loop (HITL):** Cơ chế dừng (interrupt) để con người phê duyệt các hành động quan trọng và tiếp tục (resume) sau đó.
*   **Error Recovery (Khôi phục lỗi):** Triển khai cơ chế thử lại (retry), mô hình dự phòng (fallback) và xử lý lỗi nghiêm trọng (dead-letter).
*   **Persistence (Lưu trữ trạng thái):** Sử dụng checkpointer để đảm bảo hệ thống có thể khôi phục sau khi gặp sự cố (crash-resume).

### 2. Các kịch bản thử nghiệm (6 Scenarios)
Học viên phải hoàn thiện logic để agent vượt qua **6 tình huống thực tế**:
1.  **Simple:** Xử lý yêu cầu đơn giản (single-shot).
2.  **Tool:** Yêu cầu cần sử dụng công cụ hỗ trợ.
3.  **Missing-info:** Agent biết dừng lại để hỏi thêm thông tin khi thiếu dữ liệu.
4.  **Risky-action:** Kịch bản rủi ro yêu cầu sự phê duyệt từ con người (HITL).
5.  **Transient-error:** Lỗi tạm thời có thể tự phục hồi bằng cơ chế retry.
6.  **Max-error:** Lỗi vượt quá số lần thử lại, yêu cầu chuyển sang quy trình xử lý thủ công (dead-letter).

### 3. Các cột mốc thực hiện (Timeline 4 giờ)
Tiến trình thực hành được chia làm các giai đoạn cụ thể:
*   **0-30 phút:** Thiết lập môi trường, đọc hiểu State Schema và chạy các bài kiểm tra cơ sở (baseline).
*   **30-75 phút:** Triển khai các node chức năng cơ bản và kết nối đồ thị (graph wiring).
*   **75-120 phút:** Cài đặt định hướng có điều kiện (conditional routing), cơ chế retry và giả lập phê duyệt (HITL mock).
*   **120-180 phút:** Tích hợp bộ lưu trữ trạng thái (persistence/checkpoint) và xử lý khôi phục sau sự cố (crash-resume).
*   **180-225 phút:** Chạy bộ công cụ đo lường (metrics runner) và hoàn thiện báo cáo theo mẫu.
*   **225-240 phút:** Demo sản phẩm, dọn dẹp và tự đánh giá.

### 4. Sản phẩm đầu ra (Deliverables)
Sản phẩm cuối cùng bao gồm:
*   **Mã nguồn (Code):** Repo hoàn thiện các vùng "TODO" với cấu trúc node nhỏ, dễ kiểm thử và định nghĩa trạng thái (State) chuẩn.
*   **File metrics.json:** Ghi lại các thông số vận hành như: tỷ lệ thành công, số node đã đi qua, số lần thử lại (retry count), số lần dừng phê duyệt (interrupt count), và lỗi xác thực trạng thái.
*   **File report.md:** Báo cáo kỹ thuật bao gồm sơ đồ kiến trúc, State Schema, kết quả các kịch bản kiểm thử, phân tích lỗi và kế hoạch cải thiện.

### 5. Tiêu chí đánh giá (Scoring Rubric)
Điểm số được phân bổ dựa trên các yếu tố:
*   **Kiến trúc & Trạng thái (20đ):** Trạng thái được định nghĩa rõ ràng (Typed state), sử dụng Reducer đúng cách.
*   **Hành vi của Graph (25đ):** Routing chính xác, cơ chế retry có giới hạn và HITL hoạt động tốt.
*   **Khả năng lưu trữ & Khôi phục (15đ):** Triển khai thành công Checkpoint và Thread ID để tiếp tục workflow.
*   **Đo lường & Kiểm thử (20đ):** Vượt qua 6 kịch bản và xuất file metrics hợp lệ.
*   **Báo cáo & Demo (15đ):** Phân tích lỗi sâu sắc và sơ đồ minh họa rõ ràng.
*   **Vệ sinh mã nguồn (5đ):** Tuân thủ quy tắc lập trình, có file README và quản lý cấu hình tốt.