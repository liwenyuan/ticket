#!/usr/bin/env python3
"""
海淀文旅@海淀 活动抢票状态监控
接口: GET https://hdwlszpt.bjhddsj.cn/hdggwh-os/content/activity/activityInfo/_PUB?contentId=137230
状态字段: result.buttonStatus / result.button_txt
  - signup / not_started 等均为非"已满"状态 (button_txt 各异)
  - full / 报名已满 -> 报名已满 (当前状态)
触发规则: 按钮文案只要不是"报名已满"(buttonStatus != full 且文案不含"满"),
  即从已满状态变为任何其他文案 -> 通过 Server酱 发送微信提醒。
"""
import json
import sys
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

API = "https://hdwlszpt.bjhddsj.cn/hdggwh-os/content/activity/activityInfo/_PUB?contentId=137230"
STATE_FILE = Path(__file__).parent / "last_state.json"
CONFIG_FILE = Path(__file__).parent / "config.json"

BTN_TXT = {
    "signup": "立即报名(可报名)",
    "not_started": "立即报名(未开始)",
    "full": "报名已满",
}


def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def load_config():
    # 优先读环境变量 SENDKEY (GitHub Actions 等云端环境), 其次读本地 config.json
    import os
    sendkey = os.environ.get("SENDKEY")
    if sendkey:
        return sendkey
    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return cfg["sendkey"]


def fetch_status():
    req = urllib.request.Request(API, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    result = data.get("result") or {}
    return result.get("buttonStatus", "unknown"), result.get("button_txt", "")


def load_last_state():
    """返回 (buttonStatus, button_txt)，首次返回 (None, None)"""
    if STATE_FILE.exists():
        try:
            d = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return d.get("buttonStatus"), d.get("button_txt")
        except Exception:
            return None, None
    return None, None


def save_state(status, txt):
    STATE_FILE.write_text(
        json.dumps(
            {"buttonStatus": status, "button_txt": txt, "checkedAt": datetime.now().isoformat()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def send_wechat(sendkey, title, desp):
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    payload = urllib.parse.urlencode({"title": title, "desp": desp}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    ok = body.get("code") == 0
    log(f"Server酱推送{'成功' if ok else '失败: ' + json.dumps(body, ensure_ascii=False)}")
    return ok


def main():
    sendkey = load_config()
    status, txt = fetch_status()
    last_status, last_txt = load_last_state()
    log(f"当前状态: buttonStatus={status} button_txt={txt} (上次: {last_status}/{last_txt})")

    # 首次运行只记录状态
    if last_status is None:
        save_state(status, txt)
        log("首次运行, 记录初始状态, 不推送")
        return

    # 判断逻辑: 按钮文案只要不是"报名已满"即视为状态变化(开放抢票)
    # 上次是否处于"已满"状态 (以字段值或文案任一判断, 兼容未知字段值)
    was_full = (last_status == "full") or (last_txt and "满" in last_txt)
    # 当前是否不是"已满" (status 非 full 且文案不含"满"; unknown 视为接口异常不触发)
    is_open = (status not in ("full", "unknown")) and ("满" not in (txt or ""))

    if was_full and is_open:
        title = f"🎫 抢票提醒: 按钮变为「{txt or status}」"
        desp = (
            f"**活动**: 2026年中关村舞剧展演季·舞蹈家专场\n\n"
            f"**状态变化**: 报名已满 -> **{txt or status}**\n\n"
            f"**字段**: buttonStatus={status}, button_txt={txt}\n\n"
            f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"[点此抢票](https://hdwlszpt.bjhddsj.cn/new-zkdn-vue/actDetail.html?id=137230)"
        )
        send_wechat(sendkey, title, desp)
    elif not was_full and is_open:
        log(f"状态仍为非已满({status}/{txt}), 之前已提醒过, 不重复推送")

    save_state(status, txt)


if __name__ == "__main__":
    main()
