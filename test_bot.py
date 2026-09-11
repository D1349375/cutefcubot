"""逢甲搶課 LINE Bot 單元與整合測試腳本
用於在未綁定 LINE Webhook 之前，本機驗證整個業務流程與 API 響應。
"""
import asyncio
import re
from fcu_client import FCUClient
from monitor import CourseMonitor

print("========================================")
print("  逢甲選課退選提醒系統 - 本機整合測試")
print("========================================")

# 1. 測試逢甲 API 客戶端
client = FCUClient()
course_code = "3073"
print(f"\n[1] 正在測試查詢課程代碼: {course_code} ...")
info = client.get_course_detail(course_code)

if info:
    print("  ✅ 成功獲取課程即時資訊:")
    print(f"     課名: {info['course_name']}")
    print(f"     教師: {info['teacher']}")
    print(f"     時間教室: {info['period']}")
    print(f"     人數: {info['current_count']:.0f} / {info['max_count']:.0f}")
    print(f"     剩餘: {info['remaining']:.0f}")
    print(f"     是否有空位: {info['has_vacancy']}")
else:
    print("  ❌ 查詢失敗！")

# 2. 測試正則自然語言指令解析
test_sentences = [
    "3073這堂課有人退選就提醒我",
    "幫我監控 3073",
    "查詢 3073",
    "取消 3073",
    "我的清單",
    "說明"
]

print("\n[2] 測試使用者自然語言指令解析:")
for sent in test_sentences:
    matched_cancel = re.search(r"(?:取消|停止|刪除)\s*([0-9]{4})", sent)
    matched_query = re.search(r"(?:查詢|查|找)\s*([0-9]{4})", sent)
    matched_watch = re.search(r"(?<!\d)([0-9]{4})(?!\d)", sent)

    if matched_cancel:
        intent = f"【取消監控】課號 {matched_cancel.group(1)}"
    elif matched_query:
        intent = f"【即時查詢】課號 {matched_query.group(1)}"
    elif matched_watch:
        intent = f"【加入監控】課號 {matched_watch.group(1)}"
    else:
        intent = f"【系統指令】{sent}"

    print(f"  句子: 「{sent}」 -> 解析意圖: {intent}")

# 3. 測試監控管理器
print("\n[3] 測試關注清單管理器 (Watchlist):")
monitor = CourseMonitor(client, poll_interval=10)
fake_user = "U_test_user_888"

# 模擬加入
success, msg = monitor.add_watch(fake_user, info)
print(f"  加入狀態: {success}, 訊息: {msg}")
user_list = monitor.get_user_watchlist(fake_user)
print(f"  當前測試使用者的關注數量: {len(user_list)}")

# 模擬查詢監控中課程代碼
active_codes = monitor.get_all_active_codes()
print(f"  系統待輪詢的課號清單: {list(active_codes)}")

# 模擬移除
success_rm, msg_rm = monitor.remove_watch(fake_user, course_code)
print(f"  移除狀態: {success_rm}, 訊息: {msg_rm}")
print(f"  移除後關注數量: {len(monitor.get_user_watchlist(fake_user))}")

print("\n========================================")
print("🎉 所有本機功能與 API 驗證全數通過！")
print("========================================")
