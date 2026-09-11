"""逢甲選課退選即時提醒 LINE 機器人 (FastAPI 後端)
完全基於本地家用網路運行，零資安疑慮、免學號密碼。
"""
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Dict, Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import HTMLResponse, JSONResponse

from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhook import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from fcu_client import FCUClient
from monitor import CourseMonitor

# 載入 .env 設定檔
load_dotenv()

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "25"))
PORT = int(os.getenv("PORT", "8000"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("FCU-LineBot")

# 初始化逢甲查課模組與監控排程模組
fcu_client = FCUClient()
course_monitor = CourseMonitor(fcu_client, poll_interval=POLL_INTERVAL)

# 初始化 LINE SDK
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN) if LINE_CHANNEL_ACCESS_TOKEN else None


async def send_push_notification(user_id: str, course_info: dict):
    """當背景巡檢發現有名額釋出時，主動推播給使用者"""
    if not line_config:
        logger.warning(f"尚未設定 LINE_CHANNEL_ACCESS_TOKEN，無法發送推播給 {user_id}")
        return

    code = course_info["course_code"]
    name = course_info["course_name"]
    curr = course_info["current_count"]
    max_c = course_info["max_count"]
    rem = course_info["remaining"]
    teacher = course_info["teacher"] or "未知"
    period = course_info["period"] or "未註記"

    msg = (
        f"🚨【空位警報！有人退選了！】\n\n"
        f"📚 課程：【{code}】{name}\n"
        f"👨‍🏫 授課教師：{teacher}\n"
        f"⏰ 上課時間：{period}\n"
        f"👥 目前人數：{curr:.0f} / {max_c:.0f} 人\n"
        f"⚡ 釋出名額：{rem:.0f} 個空位！\n\n"
        f"👉 請立即點擊下方連結登入搶課：\n"
        f"🔗 https://course.fcu.edu.tw/\n\n"
        f"💡 貼心提醒：搶課成功後，您可輸入「取消 {code}」解除監控；若名額又被搶走，輸入「{code}」可再次啟用巡檢！"
    )

    with ApiClient(line_config) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=msg)],
            )
        )
    logger.info(f"已成功推播退選警報至使用者 {user_id}")


# 設定監控模組的回呼函式
course_monitor.set_notify_callback(send_push_notification)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 服務啟動時：開始背景輪詢
    await course_monitor.start()
    yield
    # 服務關閉時：停止背景輪詢
    await course_monitor.stop()


app = FastAPI(title="FCU Course Alert LINE Bot", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index():
    active_count = len(course_monitor.get_all_active_codes())
    return f"""
    <html>
        <head><title>逢甲選課退選提醒機器人</title></head>
        <body style="font-family: sans-serif; padding: 40px; line-height: 1.6;">
            <h2>🎉 逢甲選課退選提醒機器人 (FCU Course Alert Bot) 運行中</h2>
            <p>✅ 伺服器狀態：正常連線中</p>
            <p>🔍 背景巡檢間隔：每 {POLL_INTERVAL} 秒一次</p>
            <p>📚 目前正在監控中的不重複課號數量：<strong>{active_count}</strong> 門</p>
            <hr/>
            <p>💡 LINE Webhook Callback 網址為：<code>/callback</code></p>
        </body>
    </html>
    """


@app.post("/callback")
async def callback(request: Request, x_line_signature: str = Header(None)):
    """接收 LINE 傳來的 Webhook 事件"""
    if not handler:
        raise HTTPException(status_code=500, detail="LINE_CHANNEL_SECRET 未設定")

    if not x_line_signature:
        raise HTTPException(status_code=400, detail="Missing X-Line-Signature header")

    body = await request.body()
    body_text = body.decode("utf-8")

    try:
        handler.handle(body_text, x_line_signature)
    except InvalidSignatureError:
        logger.error("簽名驗證失敗，請檢查 LINE_CHANNEL_SECRET 是否正確！")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"處理 Webhook 發生異常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse(content={"status": "OK"})


def reply_text(reply_token: str, text: str):
    """回覆使用者訊息輔助函式"""
    if not line_config:
        return
    try:
        with ApiClient(line_config) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=text)],
                )
            )
    except Exception as e:
        logger.error(f"回覆 LINE 訊息失敗: {e}")


if handler:
    @handler.add(MessageEvent, message=TextMessageContent)
    def handle_text_message(event: MessageEvent):
        user_id = event.source.user_id
        text = event.message.text.strip()
        reply_token = event.reply_token

        logger.info(f"收到來自使用者 {user_id} 的訊息: {text}")

        # 1. 幫助與使用說明
        if text in ["幫助", "說明", "help", "Help", "?", "？"]:
            help_msg = (
                "🤖【逢甲選課退選提醒小幫手】使用說明：\n\n"
                "1️⃣ 想要監控某門課：\n"
                "👉 直接輸入課號或自然語言，例如：\n"
                "「3073 這堂課有人退選就提醒我」或「監控 3073」\n\n"
                "2️⃣ 查詢課程目前人數：\n"
                "👉 輸入「查詢 3073」\n\n"
                "3️⃣ 查看自己目前關注中的課程：\n"
                "👉 輸入「我的清單」或「清單」\n\n"
                "4️⃣ 取消監控某門課：\n"
                "👉 輸入「取消 3073」\n\n"
                "🔒 本服務完全透過逢甲公開檢索系統查詢，100% 不索取您的學號或密碼，敬請安心使用！"
            )
            reply_text(reply_token, help_msg)
            return

        # 2. 查看我的清單
        if text in ["我的清單", "清單", "list", "List"]:
            watchlist = course_monitor.get_user_watchlist(user_id)
            if not watchlist:
                reply_text(reply_token, "📭 您目前沒有關注任何課程喔！\n您可以輸入如「3073 有人退選就提醒我」來開始監控。")
                return

            lines = ["📋【您目前的關注課程清單】\n"]
            for idx, item in enumerate(watchlist, 1):
                status_text = "🟢 監控中" if item.get("status") == "watching" else "🔔 已通知過"
                lines.append(
                    f"{idx}. 【{item['course_code']}】{item['course_name']}\n"
                    f"   狀態：{status_text}\n"
                    f"   人數：{item.get('last_count', 0):.0f} / {item.get('max_count', 0):.0f}"
                )
            lines.append("\n💡 輸入「取消 課號」可解除關注。")
            reply_text(reply_token, "\n".join(lines))
            return

        # 3. 取消關注指定課號
        cancel_match = re.search(r"(?:取消|停止|刪除)\s*([0-9]{4})", text)
        if cancel_match:
            code = cancel_match.group(1)
            success, msg = course_monitor.remove_watch(user_id, code)
            reply_text(reply_token, f"{'✅' if success else '⚠️'} {msg}")
            return

        # 4. 單純即時查詢指定課號
        query_match = re.search(r"(?:查詢|查|找)\s*([0-9]{4})", text)
        if query_match:
            code = query_match.group(1)
            course_info = fcu_client.get_course_detail(code)
            if not course_info:
                reply_text(reply_token, f"⚠️ 查無選課代碼【{code}】的課程資訊，請確認代碼是否正確。")
                return

            status_desc = (
                f"🎉 目前有空位！(剩餘 {course_info['remaining']:.0f} 個名額)"
                if course_info["has_vacancy"]
                else "🈵 目前額滿中"
            )
            res_msg = (
                f"📖【課程資訊查詢】\n"
                f"選課代碼：{code}\n"
                f"課程名稱：{course_info['course_name']}\n"
                f"學分：{course_info['credits']}\n"
                f"開課班級：{course_info['class_name']}\n"
                f"授課教師：{course_info['teacher'] or '未註記'}\n"
                f"時間教室：{course_info['period'] or '未註記'}\n"
                f"人數狀況：{course_info['current_count']:.0f} / {course_info['max_count']:.0f} 人 ({status_desc})\n\n"
                f"💡 想在此課程釋出名額時收到通知？請直接回覆「監控 {code}」！"
            )
            reply_text(reply_token, res_msg)
            return

        # 5. 核心功能：監控/提醒（捕捉 4 位數課號，不論前後是否有空格）
        code_match = re.search(r"(?<!\d)([0-9]{4})(?!\d)", text)
        if code_match:
            code = code_match.group(1)
            # 即時連線逢甲檢索系統查證此課堂
            course_info = fcu_client.get_course_detail(code)
            if not course_info:
                reply_text(
                    reply_token,
                    f"⚠️ 查無選課代碼為【{code}】的課程！\n請確認該課號是否為本學期開課課號。"
                )
                return

            # 如果當前就已經有名額
            if course_info["has_vacancy"]:
                vacancy_msg = (
                    f"🎉 這堂課現在就已經有空位囉！不用等退選！\n\n"
                    f"📚 【{code}】{course_info['course_name']}\n"
                    f"👥 目前人數：{course_info['current_count']:.0f} / {course_info['max_count']:.0f}\n"
                    f"⚡ 剩餘名額：{course_info['remaining']:.0f} 個\n\n"
                    f"👉 快手刀進系統加選：\n"
                    f"🔗 https://course.fcu.edu.tw/"
                )
                reply_text(reply_token, vacancy_msg)
                return

            # 加入排程監控
            success, msg = course_monitor.add_watch(user_id, course_info)
            if not success:
                reply_text(reply_token, f"ℹ️ {msg}")
                return

            confirm_msg = (
                f"✅ 已成功加入退選監控清單！\n\n"
                f"📚 【{code}】{course_info['course_name']}\n"
                f"👨‍🏫 授課教師：{course_info['teacher'] or '未註記'}\n"
                f"⏰ 上課時間：{course_info['period'] or '未註記'}\n"
                f"👥 目前狀態：{course_info['current_count']:.0f} / {course_info['max_count']:.0f} 人 (額滿中)\n\n"
                f"🤖 後台已啟動巡檢（每 {POLL_INTERVAL} 秒檢查一次）。\n"
                f"一旦有任何同學退選，我會第一時間傳訊息通知你快去搶！"
            )
            reply_text(reply_token, confirm_msg)
            return

        # 預設未知指令回覆
        reply_text(
            reply_token,
            "您好！我是逢甲搶課小幫手。\n"
            "請直接告訴我想關注的 4 位數課號，例如：\n"
            "👉「3073 這堂課有人退選就提醒我」\n"
            "輸入「說明」可查看完整功能列表！"
        )


if __name__ == "__main__":
    uvicorn.run("bot:app", host="0.0.0.0", port=PORT, reload=False)
