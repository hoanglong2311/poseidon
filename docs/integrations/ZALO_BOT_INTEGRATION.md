# Zalo Bot — Hướng dẫn tổng hợp & Tích hợp với Agent Base (Green Node)

> Tổng hợp từ tài liệu chính thức Zalo Bot Platform (`bot.zaloplatforms.com/docs`).
> Cập nhật theo docs ngày: create-bot 17/12/2025, group 3/6/2026, webhook 11/6/2026, sendMessage 10/6/2026.
> Mục tiêu: dùng Zalo Bot thực tế, nhận tin nhắn (cá nhân + nhóm) và phản hồi tự động qua một AI agent backend.

> **Bối cảnh Poseidon:** Tài liệu này phục vụ hạng mục _Zalo group bot integration_ (Future phase) trong [`../product/PRODUCT_CONTEXT.md`](../product/PRODUCT_CONTEXT.md). Trong dự án, "Agent Base / Green Node" ở mục 9 chính là **Custom Agent runtime trên GreenNode AgentBase** — nơi chạy Report Engine. Bridge webhook ở mục 9 là cầu nối giữa Zalo Bot và agent để: (a) push báo cáo 9:00 / 17:30 ra group, (b) trả lời khi thành viên mention/reply bot.

---

## 1. Zalo Bot là gì

Zalo Bot là tài khoản tự động hoạt động trên nền tảng Zalo, cho phép doanh nghiệp/nhà phát triển tương tác tự động với người dùng ngay trong cửa sổ chat. Dùng để gửi thông báo, tự động hóa quy trình, và kết nối với hệ thống nội bộ (ERP, CRM, CDP, hoặc AI agent).

Mô hình hoạt động gồm 3 phần:

- **Zalo Bot Platform**: nơi tạo bot, cấp token, định tuyến tin nhắn.
- **Zalo Bot API** (`bot-api.zaloplatforms.com`): API để bot gửi/nhận dữ liệu.
- **Backend của bạn**: nơi nhận webhook, xử lý logic (gọi Agent Base), và gọi API gửi tin trả lời.

---

## 2. Tạo Bot và lấy Token

**Bước 1 — Truy cập Zalo OA**

1. Mở ứng dụng Zalo.
2. Tìm OA **Zalo Bot Manager**.
3. Trong menu cửa sổ chat, chọn **Tạo bot** để mở mini app **Zalo Bot Creator**.

**Bước 2 — Thiết lập thông tin Bot**

- Nhập tên Bot (bắt buộc bắt đầu bằng tiền tố `Bot`, ví dụ `Bot MyShop`) và các thông tin cần thiết.
- Nhấn **Tạo Bot**.
- Sau khi tạo thành công, hệ thống gửi **thông tin Bot** và **Bot Token** qua tin nhắn Zalo cho bạn.

**Bước 3 — Lập trình Bot**

Dùng Node.js, Python hoặc nền tảng no-code. Có 2 cơ chế nhận tin (xem mục 4):

- **Long polling** (`getUpdates`): dùng chạy thử/dev ở local.
- **Webhook** (`setWebhook`): dùng cho production.

---

## 3. Xác thực — Bot Token

- Token được cấp sau khi tạo bot, **không hết hạn** cho tới khi bạn chủ động reset.
- Dạng token: `12345689:abc-xyz`.
- Reset token: vào Zalo Bot Creator → Thiết lập → làm theo hướng dẫn; token mới sẽ gửi qua tin nhắn Zalo.

Token được nhúng trực tiếp vào URL khi gọi API:

```
https://bot-api.zaloplatforms.com/bot${BOT_TOKEN}/functionName
```

> ⚠️ Token tương đương mật khẩu của bot. Lưu trong biến môi trường/secret manager, không commit vào code.

---

## 4. Cách gọi API

**Định dạng URL** (bắt buộc HTTPS):

```
https://bot-api.zapps.me/bot<BOT_TOKEN>/<functionName>
# ví dụ
https://bot-api.zapps.me/bot123456789:abc123xyz/getMe
```

> ⚠️ **Đính chính endpoint:** host thực tế đang hoạt động là **`bot-api.zapps.me`** (đã verify qua `scripts/zalo-bot-test.mjs`), không phải `bot-api.zaloplatforms.com` như một số tài liệu ghi. Agent dùng `ZALO_BASE_URL` (mặc định `https://bot-api.zapps.me`) — đổi được qua env nếu Zalo cập nhật host.

**HTTP method**: hỗ trợ cả `GET` và `POST` cho mọi API.
Khuyến nghị: `GET` cho API đọc dữ liệu, `POST` cho API ghi/cập nhật.

**Cách truyền tham số**: query string · `application/x-www-form-urlencoded` · `application/json` · `multipart/form-data` (khi upload file).

**Phản hồi** luôn là JSON:

| Trường | Ý nghĩa |
|---|---|
| `ok` | `true` nếu thành công, `false` nếu lỗi |
| `result` | Dữ liệu trả về khi thành công |
| `description` | Mô tả lỗi (nếu có) |
| `error_code` | Mã lỗi hệ thống |

**Lưu ý**: dùng encoding UTF-8; tên method **phân biệt hoa/thường**.

**Danh sách API chính**: `getMe`, `getUpdates`, `setWebhook`, `deleteWebhook`, `getWebhookInfo`, `sendMessage`, `sendPhoto`, `sendSticker`, `sendVoice`, `sendChatAction`.

---

## 5. Hai cơ chế nhận tin nhắn (loại trừ lẫn nhau)

> Quan trọng: `getUpdates` **không hoạt động** nếu đã thiết lập Webhook. Muốn dùng lại polling phải gọi `deleteWebhook` trước.

| | Long polling (`getUpdates`) | Webhook (`setWebhook`) |
|---|---|---|
| Cơ chế | Bạn chủ động gọi API định kỳ để lấy tin mới | Zalo chủ động POST tin về URL của bạn |
| Dùng cho | Local / development / thử nghiệm | **Production** |
| Rủi ro | Có thể bỏ lỡ event, tốn request | Ổn định, real-time |

> 🧪 **Kinh nghiệm thực tế (Poseidon, 2026-06-14):**
> - Host hoạt động cho getUpdates/sendMessage là **`bot-api.zapps.me`**; `bot-api.zaloplatforms.com` trả `Request timeout` khi getUpdates.
> - getUpdates là **long-poll real-time**: chỉ bắt được tin nhắn tới **trong lúc đang poll**; tin gửi trước đó KHÔNG replay. Muốn lấy `chat_id` member: chạy getUpdates (timeout 20-30s) **rồi bảo member nhắn bot ngay lúc đó**.
> - `getWebhookInfo`/`deleteWebhook` có thể trả 404/400 nếu chưa từng set webhook — bình thường.
> - Payload bắt được: `{"message":{"chat":{"id":"...","chat_type":"PRIVATE"},"text":"...","from":{"display_name":"..."}},"event_name":"message.text.received"}` → lấy `message.chat.id` làm `chat_id`.

### 5a. getUpdates (polling — dev/local)

```js
const axios = require("axios");
const entrypoint = `https://bot-api.zaloplatforms.com/bot${BOT_TOKEN}/getUpdates`;
const response = await axios.post(entrypoint, { timeout: 30 });
```

- `timeout` (tùy chọn): thời gian timeout HTTP request theo giây, mặc định 30s.
- Dữ liệu trả về có cấu trúc giống payload Webhook (mục 6).

### 5b. setWebhook (production)

```js
const axios = require("axios");
const entrypoint = `https://bot-api.zaloplatforms.com/bot${BOT_TOKEN}/setWebhook`;
const response = await axios.post(entrypoint, {
  url: "https://your-webhookurl.com",
  secret_token: "mykey-abcyxz"
});
```

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `url` | String | ✅ | URL nhận thông báo, dạng **HTTPS** |
| `secret_token` | String | ✅ | Khóa bí mật 8–256 ký tự. Zalo đính kèm trong header `X-Bot-Api-Secret-Token` ở mọi request gọi về |

Response mẫu:

```json
{ "ok": true, "result": { "url": "https://your-webhookurl.com", "updated_at": 1749538250568 } }
```

---

## 6. Cấu trúc dữ liệu Webhook (payload Zalo gửi về)

Zalo gửi `POST` (JSON) đến Webhook URL khi có tương tác. **Mọi request đều có header `X-Bot-Api-Secret-Token`** = `secret_token` bạn đã đặt → **phải xác thực header này trước khi xử lý.**

```js
app.use(express.json());
const WEBHOOK_SECRET_TOKEN = 'your-secret-token';

app.post("/webhooks", async (req, res) => {
  const secretToken = req.headers["x-bot-api-secret-token"];
  if (secretToken !== WEBHOOK_SECRET_TOKEN) {
    return res.status(403).json({ message: "Unauthorized" });
  }
  const body = req.body;
  // Xử lý logic tại đây
  res.json({ message: "Success" });
});
```

**Các loại sự kiện (`event_name`)**:

- `message.text.received` — tin nhắn văn bản
- `message.image.received` — hình ảnh
- `message.sticker.received` — sticker
- `message.voice.received` — tin nhắn thoại
- `message.unsupported.received` — tin chưa hỗ trợ xử lý

**Payload mẫu:**

```json
{
  "ok": true,
  "result": {
    "message": {
      "from": { "id": "6ede9afa66b88fe6d6a9", "display_name": "Ted", "is_bot": false },
      "chat": { "id": "6ede9afa66b88fe6d6a9", "chat_type": "PRIVATE" },
      "text": "Xin chào",
      "message_id": "2d758cb5e222177a4e35",
      "date": 1750316131602
    },
    "event_name": "message.text.received"
  }
}
```

**Object `message`:**

| Trường | Kiểu | Mô tả |
|---|---|---|
| `from` | object | Người gửi (`id`, `display_name`, `is_bot`) |
| `chat` | object | Cuộc trò chuyện. `chat_type` = `PRIVATE` (cá nhân) hoặc `GROUP` (nhóm, Beta). **Dùng `chat.id` để gửi phản hồi** |
| `text` | String | Nội dung tin văn bản |
| `photo` | String | Link ảnh (tin hình ảnh) |
| `caption` | String | Chú thích kèm ảnh |
| `sticker` / `url` | String | Sticker và link sticker |
| `voice_url` | String | Link tệp âm thanh (tin thoại) |

> ⚠️ Nếu người gửi thuộc nhóm đối tượng đặc biệt (trẻ em, người khuyết tật, người không biết chữ…), bạn sẽ nhận `message.unsupported.received` thay vì nội dung tin nhắn — để tuân thủ pháp luật.

---

## 7. Gửi tin trả lời — sendMessage

```js
const axios = require("axios");
const entrypoint = `https://bot-api.zaloplatforms.com/bot${BOT_TOKEN}/sendMessage`;
const response = await axios.post(entrypoint, {
  chat_id: "abc.xyz",
  text: "Hello"
});
```

| Trường | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `chat_id` | String | ✅ | ID người nhận hoặc cuộc trò chuyện (lấy từ `chat.id` của webhook) |
| `text` | String | ✅ | Nội dung, độ dài 1–2000 ký tự |
| `parse_mode` | String | ❌ | `markdown` hoặc `html` — server tự suy ra định dạng từ `text` |
| `text_styles` | Array | ❌ | Danh sách style run áp trực tiếp lên text thô |

Response mẫu:

```json
{ "ok": true, "result": { "message_id": "82599fa32f56d00e8941", "date": 1749632637199 } }
```

### Định dạng văn bản (Rich Text)

Hai cách (nếu gửi cả hai, **`parse_mode` được ưu tiên**, `text_styles` bị bỏ qua):

**Cách 1 — `parse_mode`** (`markdown`/`html`):

```js
await axios.post(entrypoint, {
  chat_id: "abc.xyz",
  parse_mode: "markdown",
  text: "**Xin chào** _bạn_, đây là ~~tin nhắn~~ tin nhắn có định dạng"
});
```

Markdown hỗ trợ: `**đậm**`, `*nghiêng*`, `***đậm nghiêng***`, `~~gạch ngang~~`, `` `code` ``, tiêu đề `#`–`####`, danh sách `-`/`1.`, trích dẫn `>`, màu `{red}…{/red}` (red/orange/yellow/green), `{big}…{/big}`, `{underline}…{/underline}`, escape `\*`.
HTML hỗ trợ: `<b>/<strong>`, `<i>/<em>`, `<u>`, `<s>/<del>/<strike>`, `<h1>–<h6>`, `<ul>/<ol>/<li>`, `<p>/<div>`, và `style="..."` (font-size, font-weight, font-style, text-decoration, color trong bảng màu cho phép). Thẻ ngoài danh sách bị loại, nội dung text vẫn giữ.

**Cách 2 — `text_styles`** (mỗi run: `start`, `len` theo UTF-16 code unit, `st` là mảng mã định dạng):

```bash
curl -X POST "https://bot-api.zaloplatforms.com/bot<BOT_TOKEN>/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{ "chat_id": "abc.xyz", "text": "Xin chào bạn",
        "text_styles": [ { "start": 0, "len": 7, "st": ["b", "c_db342e"] } ] }'
```

Mã `st`: `b` đậm · `i` nghiêng · `u` gạch chân · `s` gạch ngang · `f_13/f_15/f_18/f_20` cỡ chữ · `c_050a19` mặc định / `c_15a85f` xanh lá / `c_f7b503` vàng / `c_f27806` cam / `c_db342e` đỏ · `lst_1`/`lst_2` danh sách · `ind_1`–`ind_5` mức thụt lề.

---

## 8. Bot tương tác trong Nhóm chat (Group — Beta)

> Tính năng đang thử nghiệm nội bộ, sẽ ra mắt sau.

**Thêm Bot vào nhóm:**

1. Mở mini app **Zalo Bot Creator**, chọn bot → vào trang thông tin Bot, lấy **Link Bot**.
2. Ở mục "Mời Bot vào nhóm", nhấn chia sẻ / gửi link vào nhóm chat.
3. Trong nhóm, **trưởng nhóm** nhấn vào link Bot.
4. Popup "Thêm Bot vào Nhóm" hiện ra → nhấn **Xác nhận**.
5. Bot gửi tin chào mừng / thông báo đã tham gia.

**Cách thành viên tương tác với Bot trong nhóm** (Bot chỉ nhận event trong 2 trường hợp này):

- **Reply (Quote)**: người dùng "Trả lời" một tin nhắn mà Bot đã gửi trước đó.
- **Mention**: người dùng gõ `@` và chọn tên Bot trong tin nhắn.

**Xử lý webhook trong nhóm:**

- Lấy ID nhóm từ trường **`chat.id`** trong payload (khi đó `chat.chat_type = "GROUP"`).
- Dùng `chat.id` này làm `chat_id` khi gọi `sendMessage` để trả lời đúng nhóm.

---

## 9. Tích hợp Zalo Bot với Agent Base (Green Node)

Ý tưởng: dựng một **webhook bridge** (backend nhỏ) đứng giữa Zalo và AI agent của bạn trên Agent Base / Green Node. Luồng:

```
Người dùng/Nhóm Zalo
        │  (1) gửi tin nhắn
        ▼
Zalo Bot Platform ──(2) POST webhook + X-Bot-Api-Secret-Token──► Bridge backend (của bạn)
                                                                      │ (3) gọi Agent Base API
                                                                      ▼
                                                                 Agent Base / Green Node
                                                                      │ (4) trả lời (text)
        ◄──(6) sendMessage(chat_id, text)──────────────────────  Bridge backend
        ▼
Zalo trả lời người dùng/nhóm
```

**Mẫu code bridge (Node.js / Express):**

```js
const express = require("express");
const axios = require("axios");
const app = express();
app.use(express.json());

const BOT_TOKEN = process.env.ZALO_BOT_TOKEN;
const WEBHOOK_SECRET_TOKEN = process.env.ZALO_WEBHOOK_SECRET;
const AGENT_BASE_URL = process.env.AGENT_BASE_URL;   // endpoint agent trên Green Node
const AGENT_API_KEY = process.env.AGENT_API_KEY;

const ZALO_API = `https://bot-api.zaloplatforms.com/bot${BOT_TOKEN}`;

app.post("/webhooks", async (req, res) => {
  // (A) Xác thực request đến từ Zalo
  if (req.headers["x-bot-api-secret-token"] !== WEBHOOK_SECRET_TOKEN) {
    return res.status(403).json({ message: "Unauthorized" });
  }

  // (B) Trả 200 nhanh để Zalo không timeout, xử lý nền
  res.json({ message: "Success" });

  const result = req.body?.result;
  if (!result || result.event_name !== "message.text.received") return;

  const { chat, from, text } = result.message;
  const chatId = chat.id;            // dùng để gửi trả lời (cá nhân lẫn nhóm)

  try {
    // (C) Gọi Agent Base / Green Node
    const agentResp = await axios.post(
      AGENT_BASE_URL,
      {
        session_id: chatId,          // giữ ngữ cảnh hội thoại theo chat
        message: text,
        user: from.display_name,
        chat_type: chat.chat_type    // PRIVATE | GROUP
      },
      { headers: { Authorization: `Bearer ${AGENT_API_KEY}` } }
    );

    const reply = (agentResp.data.reply || "").slice(0, 2000); // text tối đa 2000 ký tự

    // (D) Gửi trả lời về Zalo
    await axios.post(`${ZALO_API}/sendMessage`, {
      chat_id: chatId,
      text: reply || "Xin lỗi, hiện tôi chưa trả lời được."
    });
  } catch (e) {
    console.error("Agent/Zalo error:", e.message);
    await axios.post(`${ZALO_API}/sendMessage`, {
      chat_id: chatId,
      text: "Hệ thống đang bận, vui lòng thử lại sau."
    });
  }
});

app.listen(process.env.PORT || 3000, () => console.log("Bridge running"));
```

**Thiết lập một lần:** gọi `setWebhook` với `url` là domain HTTPS của bridge và `secret_token` trùng `WEBHOOK_SECRET_TOKEN`.

**Lưu ý khi nối với Agent Base:**

- Dùng `chat.id` làm khóa session để agent giữ ngữ cảnh theo từng người/nhóm.
- Cắt câu trả lời ≤ 2000 ký tự; nếu dài, chia thành nhiều `sendMessage`.
- Nếu agent xử lý lâu, trả `200` cho Zalo ngay rồi gọi `sendMessage` sau (như mẫu) để tránh timeout webhook; có thể gửi `sendChatAction` để báo "đang soạn".
- Phần đặc tả chính xác endpoint/định dạng request–response của **Agent Base / Green Node** phụ thuộc tài liệu nội bộ của nền tảng đó — phần trên là khung mẫu, bạn thay `AGENT_BASE_URL` và schema body cho khớp.

---

## 10. Checklist triển khai production

- [ ] Tạo bot, lưu `BOT_TOKEN` vào secret manager (không hardcode).
- [ ] Backend có domain **HTTPS** công khai cho webhook.
- [ ] Đặt `secret_token` đủ mạnh (8–256 ký tự) và **luôn xác thực** header `X-Bot-Api-Secret-Token`.
- [ ] Gọi `setWebhook`; kiểm tra bằng `getWebhookInfo`.
- [ ] Không dùng `getUpdates` song song với Webhook (loại trừ lẫn nhau).
- [ ] Trả HTTP 200 nhanh; xử lý agent ở chế độ nền.
- [ ] Xử lý đủ các `event_name`, kể cả `message.unsupported.received`.
- [ ] Encoding UTF-8; tên method phân biệt hoa/thường.
- [ ] Giới hạn `text` ≤ 2000 ký tự.

---

## Nguồn (Zalo Bot Platform docs)

- Giới thiệu: https://bot.zaloplatforms.com/docs/
- Tạo Bot: https://bot.zaloplatforms.com/docs/create-bot/
- Xác thực: https://bot.zaloplatforms.com/docs/authorize/
- Sử dụng API: https://bot.zaloplatforms.com/docs/call-api/
- getUpdates: https://bot.zaloplatforms.com/docs/apis/getUpdates/
- setWebhook: https://bot.zaloplatforms.com/docs/apis/setWebhook/
- sendMessage: https://bot.zaloplatforms.com/docs/apis/sendMessage/
- Webhook: https://bot.zaloplatforms.com/docs/webhook/
- Tương tác với Nhóm Chat: https://bot.zaloplatforms.com/docs/build-bot-interaction-with-group/
