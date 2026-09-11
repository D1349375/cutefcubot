"""逢甲大學課程檢索系統 API 客戶端
支援自動 Session 維持、Token 跳轉、學期偵測與課程即時名額查詢。
完全無需登入、無需帳密、無驗證碼。
"""
import re
import time
import logging
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger("FCUClient")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class FCUClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        })
        self.base_host: str | None = None
        self.token_url: str | None = None
        self.year: str = "113"
        self.sms: str = "2"
        self.last_init_time: float = 0
        self.init_session()

    def init_session(self, force: bool = False) -> bool:
        """初始化 Session，取得檢索系統跳轉網址與當前學年度學期。"""
        # 每 30 分鐘或強制時重新獲取 Token
        now = time.time()
        if not force and self.base_host and (now - self.last_init_time < 1800):
            return True

        try:
            logger.info("正在連線逢甲課程檢索入口取得最新權杖...")
            r = self.session.get("https://coursesearch.fcu.edu.tw/", timeout=15, verify=False)
            m = re.search(r'url=(https://coursesearch\d+\.fcu\.edu\.tw/main\.aspx\?token=[^"\'>\s]+)', r.text)
            if not m:
                m = re.search(r'href="([^"]+main\.aspx\?token=[^"]+)"', r.text)

            if not m:
                logger.error("無法從首頁取得跳轉 Token URL")
                return False

            self.token_url = m.group(1)
            self.base_host = self.token_url.split("/main.aspx")[0]
            logger.info(f"鎖定檢索系統節點: {self.base_host}")

            # 存取 main.aspx 以設定 Session Cookie (如 ASP.NET_SessionId, FCU_WAF)
            r_main = self.session.get(self.token_url, timeout=15, verify=False)
            if r_main.status_code != 200:
                logger.warning(f"存取 main.aspx 狀態碼異常: {r_main.status_code}")

            # 呼叫 /Service/Search.asmx/init 獲取目前最新學期
            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Referer": self.token_url,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": self.base_host,
            }
            r_init = self.session.post(
                f"{self.base_host}/Service/Search.asmx/init",
                json={"lang": "cht"},
                headers=headers,
                timeout=15,
                verify=False,
            )
            if r_init.status_code == 200:
                data = r_init.json().get("d", r_init.json())
                default_year_sms = data.get("defaultYearSms", {})
                self.year = str(default_year_sms.get("year", self.year))
                self.sms = str(default_year_sms.get("sms", self.sms))
                self.last_init_time = now
                logger.info(f"檢索系統初始化成功！當前學年: {self.year} 學期: {self.sms}")
                return True
            else:
                logger.error(f"Search.asmx/init 失敗: {r_init.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"初始化連線拋出異常: {e}")
            return False

    def get_course_detail(self, course_code: str, retry: int = 2) -> dict | None:
        """依據 4 位數選課代碼查詢課程即時資訊與名額。
        
        :param course_code: 選課代號 (例如 '3073')
        :return: 包含課名、老師、目前人數、名額上限、是否有人退選等資訊的 dict，查無課程則回傳 None。
        """
        course_code = str(course_code).strip()
        if not course_code.isdigit():
            return None

        for attempt in range(retry):
            if not self.base_host:
                if not self.init_session():
                    continue

            headers = {
                "Content-Type": "application/json; charset=utf-8",
                "Referer": self.token_url or f"{self.base_host}/main.aspx",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": self.base_host,
            }
            query_payload = {
                "baseOptions": {
                    "lang": "cht",
                    "year": self.year,
                    "sms": self.sms,
                },
                "typeOptions": {
                    "code": {"enabled": True, "value": course_code},
                    "weekPeriod": {"enabled": False, "week": "*", "period": "*"},
                    "course": {"enabled": False, "value": ""},
                    "teacher": {"enabled": False, "value": ""},
                    "useEnglish": {"enabled": False},
                    "useLanguage": {"enabled": False, "value": "01"},
                    "specificSubject": {"enabled": False, "value": "1"},
                    "courseDescription": {"enabled": False, "value": ""},
                },
            }

            try:
                url = f"{self.base_host}/Service/Search.asmx/GetType2Result"
                resp = self.session.post(url, json=query_payload, headers=headers, timeout=12, verify=False)
                resp.encoding = "utf-8"

                if resp.status_code != 200:
                    logger.warning(f"查詢代碼 {course_code} 失敗 (HTTP {resp.status_code})，嘗試重新整理 Session...")
                    self.init_session(force=True)
                    continue

                res_json = resp.json().get("d", resp.json())
                items = res_json.get("items", [])
                if not items:
                    return None

                item = items[0]
                current_cnt = float(item.get("scr_precnt") or 0.0)  # 實收人數
                max_cnt = float(item.get("scr_acptcnt") or 0.0)      # 開放名額上限
                remaining = max(0.0, max_cnt - current_cnt)

                return {
                    "course_code": item.get("scr_selcode", course_code),
                    "course_name": item.get("sub_name", "").strip(),
                    "credits": item.get("scr_credit", 0.0),
                    "class_name": item.get("cls_name", "").strip(),
                    "teacher": (item.get("scr_teacher") or "").strip(),
                    "period": (item.get("scr_period") or "").strip(),
                    "current_count": current_cnt,
                    "max_count": max_cnt,
                    "remaining": remaining,
                    "has_vacancy": current_cnt < max_cnt,  # 只要實收人數小於上限，代表有名額或有人退選
                    "remarks": (item.get("scr_remarks") or "").strip(),
                    "year": self.year,
                    "sms": self.sms,
                }
            except Exception as e:
                logger.error(f"查詢代號 {course_code} 第 {attempt + 1} 次失敗: {e}")
                self.init_session(force=True)

        return None


if __name__ == "__main__":
    client = FCUClient()
    print("測試查詢 3073:")
    res = client.get_course_detail("3073")
    if res:
        print("查詢成功:", res)
    else:
        print("查無此課程")
