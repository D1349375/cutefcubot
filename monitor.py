"""監控排程與使用者關注清單管理器
負責持久化儲存 (watchlist.json)、定期背景輪詢，以及空位警報通知。
"""
import asyncio
import json
import logging
import os
import time
from typing import Callable, Coroutine, Any

from fcu_client import FCUClient

logger = logging.getLogger("CourseMonitor")
WATCHLIST_FILE = "watchlist.json"


class CourseMonitor:
    def __init__(self, fcu_client: FCUClient, poll_interval: int = 25):
        self.fcu = fcu_client
        self.poll_interval = poll_interval
        self.data: dict[str, list[dict]] = {}  # {user_id: [course_record, ...]}
        self.notify_callback: Callable[[str, dict], Coroutine[Any, Any, None]] | None = None
        self._is_running = False
        self._task: asyncio.Task | None = None
        self.load_data()

    def load_data(self):
        """從本機 JSON 載入關注資料"""
        if os.path.exists(WATCHLIST_FILE):
            try:
                with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                logger.info(f"已從 {WATCHLIST_FILE} 載入 {len(self.data)} 位使用者的關注清單")
            except Exception as e:
                logger.error(f"讀取 {WATCHLIST_FILE} 失敗: {e}")
                self.data = {}
        else:
            self.data = {}

    def save_data(self):
        """將關注資料持久化寫入本機 JSON"""
        try:
            with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"寫入 {WATCHLIST_FILE} 失敗: {e}")

    def add_watch(self, user_id: str, course_info: dict) -> tuple[bool, str]:
        """新增關注課程"""
        code = str(course_info["course_code"])
        user_watches = self.data.setdefault(user_id, [])

        # 檢查是否已在清單中
        for item in user_watches:
            if item["course_code"] == code:
                if item.get("status") == "notified":
                    item["status"] = "watching"
                    item["last_count"] = course_info["current_count"]
                    self.save_data()
                    return True, "已為您重新啟動該課程的退選監控！"
                return False, f"您已經在關注【{code} {item.get('course_name')}】囉！"

        record = {
            "course_code": code,
            "course_name": course_info.get("course_name", ""),
            "teacher": course_info.get("teacher", ""),
            "period": course_info.get("period", ""),
            "max_count": course_info.get("max_count", 0),
            "last_count": course_info.get("current_count", 0),
            "status": "watching",  # watching / notified / paused
            "added_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        user_watches.append(record)
        self.save_data()
        return True, "關注成功"

    def remove_watch(self, user_id: str, course_code: str) -> tuple[bool, str]:
        """取消關注指定課程"""
        code = str(course_code).strip()
        user_watches = self.data.get(user_id, [])
        initial_len = len(user_watches)
        user_watches = [w for w in user_watches if w["course_code"] != code]

        if len(user_watches) < initial_len:
            self.data[user_id] = user_watches
            self.save_data()
            return True, f"已取消對課程【{code}】的監控。"
        return False, f"您的關注清單中沒有找到代碼【{code}】的課程。"

    def get_user_watchlist(self, user_id: str) -> list[dict]:
        """取得指定使用者的所有關注項目"""
        return self.data.get(user_id, [])

    def get_all_active_codes(self) -> set[str]:
        """取得目前所有使用者正在 watching 的不重複課程代碼"""
        active_codes = set()
        for user_id, watches in self.data.items():
            for w in watches:
                if w.get("status") == "watching":
                    active_codes.add(w["course_code"])
        return active_codes

    def set_notify_callback(self, callback: Callable[[str, dict], Coroutine[Any, Any, None]]):
        """設定當釋出名額時要執行的通知函式 (通常為 LINE Push Message)"""
        self.notify_callback = callback

    async def start(self):
        """啟動非同步巡查工作"""
        if self._is_running:
            return
        self._is_running = True
        logger.info(f"啟動背景巡查排程器，每隔 {self.poll_interval} 秒巡檢一次")
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self):
        """停止背景排程"""
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("背景巡查排程器已停止")

    async def _poll_loop(self):
        """背景輪詢核心迴圈"""
        while self._is_running:
            try:
                active_codes = self.get_all_active_codes()
                if active_codes:
                    logger.info(f"🔍 [巡邏中] 本輪監控課程清單: {list(active_codes)}")
                    # 依序查詢每一個代碼 (多用戶重複關注的課只會查一次，節省流量)
                    for code in active_codes:
                        await self._check_single_course(code)
                        await asyncio.sleep(1)  # 每個請求之間微幅暫停，維持禮貌查詢
                else:
                    logger.debug("目前沒有任何正在追蹤的課程。")
            except Exception as e:
                logger.error(f"背景輪詢迴圈發生異常: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    async def _check_single_course(self, course_code: str):
        """查詢單一課程並在發現退選名額時觸發推播"""
        # 在執行緒池中跑同步 requests，避免阻塞 asyncio 事件迴圈
        course_info = await asyncio.to_thread(self.fcu.get_course_detail, course_code)
        if not course_info:
            logger.warning(f"巡檢找不到代號 {course_code} 的資訊")
            return

        current_cnt = course_info["current_count"]
        max_cnt = course_info["max_count"]
        has_vacancy = course_info["has_vacancy"]

        logger.info(
            f"課號 【{course_code}】 {course_info['course_name']}: "
            f"目前 {current_cnt:.0f} / {max_cnt:.0f} 人 "
            f"(剩餘名額: {course_info['remaining']:.0f})"
        )

        if has_vacancy:
            logger.info(f"🎉 發現空位！【{course_code}】有空位釋出！正在發送通知...")
            # 找到所有正在追蹤這門課的使用者
            for user_id, watches in list(self.data.items()):
                for w in watches:
                    if w["course_code"] == course_code and w.get("status") == "watching":
                        # 標記為已通知，避免每隔 25 秒重複洗版
                        w["status"] = "notified"
                        w["last_count"] = current_cnt
                        self.save_data()

                        if self.notify_callback:
                            try:
                                await self.notify_callback(user_id, course_info)
                            except Exception as ex:
                                logger.error(f"發送通知給使用者 {user_id} 失敗: {ex}")
        else:
            # 更新最新人數狀態
            for user_id, watches in self.data.items():
                for w in watches:
                    if w["course_code"] == course_code:
                        w["last_count"] = current_cnt
            self.save_data()
