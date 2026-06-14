#!/usr/bin/env node
/**
 * Zalo Bot API – smoke test script
 *
 * Tài liệu: https://bot.zaloplatforms.com/docs/create-bot/
 * API base: https://bot-api.zapps.me/bot<TOKEN>/<method>  (tương thích kiểu Telegram)
 *
 * Yêu cầu:
 *   - Node >= 18 (đã có global fetch). Bạn đang dùng v26 -> OK.
 *   - Biến môi trường BOT_ZALO_TOKEN chứa bot token.
 *
 * Cách dùng:
 *   node scripts/zalo-bot-test.mjs getme
 *   node scripts/zalo-bot-test.mjs updates
 *   node scripts/zalo-bot-test.mjs send <chat_id> "Xin chào từ bot 👋"
 *   node scripts/zalo-bot-test.mjs all                       # getMe + getUpdates
 *   node scripts/zalo-bot-test.mjs setwebhook <https-url> [secret_token]
 *   node scripts/zalo-bot-test.mjs webhookinfo
 *   node scripts/zalo-bot-test.mjs delwebhook
 *
 * Ghi chú: secret_token cho setwebhook tối thiểu 8 ký tự. Nếu không truyền,
 * script lấy từ biến môi trường WEBHOOK_SECRET_TOKEN.
 */

const TOKEN = process.env.BOT_ZALO_TOKEN;
const BASE = process.env.BOT_ZALO_BASE_URL || "https://bot-api.zapps.me";

if (!TOKEN) {
  console.error("✗ Thiếu biến môi trường BOT_ZALO_TOKEN.");
  console.error("  Hãy export trước khi chạy, ví dụ:  export BOT_ZALO_TOKEN=123456:abcdef");
  process.exit(1);
}

/** Gọi 1 method của Bot API. */
async function call(method, params = {}) {
  const url = `${BASE}/bot${TOKEN}/${method}`;
  const hasBody = Object.keys(params).length > 0;

  const res = await fetch(url, {
    method: hasBody ? "POST" : "GET",
    headers: hasBody ? { "Content-Type": "application/json" } : undefined,
    body: hasBody ? JSON.stringify(params) : undefined,
  });

  const text = await res.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { ok: false, raw: text };
  }

  if (!res.ok || data.ok === false) {
    const err = new Error(
      `${method} thất bại (HTTP ${res.status}): ${data.description || data.raw || text}`
    );
    err.data = data;
    throw err;
  }
  return data.result !== undefined ? data.result : data;
}

async function getMe() {
  console.log("→ getMe …");
  const me = await call("getMe");
  console.log("✓ Bot hoạt động:");
  console.log(JSON.stringify(me, null, 2));
  return me;
}

async function getUpdates() {
  console.log("→ getUpdates …");
  const updates = await call("getUpdates", { offset: 0, timeout: 0 });
  if (!Array.isArray(updates) || updates.length === 0) {
    console.log("ℹ Chưa có update nào. Hãy nhắn tin cho bot trên Zalo rồi chạy lại để lấy chat_id.");
    return updates;
  }
  console.log(`✓ Nhận ${updates.length} update:`);
  for (const u of updates) {
    // Zalo trả về dạng { event_name, message } (xem docs Webhook).
    const msg = u.message || u.edited_message || u.result?.message || {};
    const chat = msg.chat || {};
    const event = u.event_name || u.result?.event_name || "?";
    console.log(
      `  • event=${event} chat_id=${chat.id ?? "?"} (${chat.chat_type ?? "?"}) from=${
        msg.from?.display_name || msg.from?.id || "?"
      } text=${JSON.stringify(msg.text)}`
    );
  }
  return updates;
}

async function setWebhook(url, secretToken) {
  if (!url) {
    console.error("Cú pháp: node scripts/zalo-bot-test.mjs setwebhook <https-url> [secret_token]");
    process.exit(1);
  }
  const secret = secretToken || process.env.WEBHOOK_SECRET_TOKEN;
  if (!secret || secret.length < 8) {
    console.error("✗ secret_token bắt buộc và tối thiểu 8 ký tự (truyền qua tham số hoặc WEBHOOK_SECRET_TOKEN).");
    process.exit(1);
  }
  console.log(`→ setWebhook ${url} …`);
  const res = await call("setWebhook", { url, secret_token: secret });
  console.log("✓ Đã đặt webhook:");
  console.log(JSON.stringify(res, null, 2));
  return res;
}

async function getWebhookInfo() {
  console.log("→ getWebhookInfo …");
  const info = await call("getWebhookInfo");
  console.log(JSON.stringify(info, null, 2));
  return info;
}

async function deleteWebhook() {
  console.log("→ deleteWebhook …");
  const res = await call("deleteWebhook");
  console.log("✓ Đã xoá webhook:");
  console.log(JSON.stringify(res, null, 2));
  return res;
}

async function sendMessage(chatId, text) {
  if (!chatId || !text) {
    console.error('Cú pháp: node scripts/zalo-bot-test.mjs send <chat_id> "nội dung"');
    process.exit(1);
  }
  console.log(`→ sendMessage tới ${chatId} …`);
  const sent = await call("sendMessage", { chat_id: chatId, text });
  console.log("✓ Đã gửi:");
  console.log(JSON.stringify(sent, null, 2));
  return sent;
}

async function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  switch ((cmd || "all").toLowerCase()) {
    case "getme":
      await getMe();
      break;
    case "updates":
      await getUpdates();
      break;
    case "send":
      await sendMessage(rest[0], rest.slice(1).join(" "));
      break;
    case "all":
      await getMe();
      console.log();
      await getUpdates();
      break;
    default:
      console.error(`Lệnh không rõ: ${cmd}. Dùng: getme | updates | send | all`);
      process.exit(1);
  }
}

main().catch((err) => {
  console.error("✗ Lỗi:", err.message);
  if (err.data) console.error(JSON.stringify(err.data, null, 2));
  process.exit(1);
});
