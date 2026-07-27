# -*- coding: utf-8 -*-
"""
GitHub Actions 云端爬虫 v5
直接访问 t.me/s/ 频道页面 + BeautifulSoup 解析 HTML
弃用 r.jina.ai（GitHub 美国机房可直连 t.me，无需中转）
频道列表来自本地验证有效的 tg_spider_v2.py
"""
import re
import json
import time
import random
import os
import html as html_module
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# ============================================================
# 配置
# ============================================================

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 已验证有效的 TG 频道列表（来自 tg_spider_v2.py）
CHANNELS = [
    "bdyunpan",      # 百度网盘资源（高产）
    "PanjClub",      # 网盘俱乐部
    "Quark_Movies",  # 夸克电影
    "yunpan139",     # 移动云盘（也含百度/夸克）
    "shareAliyun",   # 阿里（含混合链接）
    "yunpanxunlei",  # 迅雷（含混合链接）
    "fuliziyuan",    # 福利资源
    "XiangxiuNBB",   # 香秀
    "yunpanuc",      # UC（含混合链接）
    "leoziyuan",     # 乐资源
    "yunpanx",       # 云盘
    "yunpanbaidu",   # 百度网盘资源分享2
    "yunpanNB",      # 鹏星4K影视综合
    "QuarkShare",    # 夸克云盘资源收集
    "quarkdj",       # 网盘资源分享
    "quarkshare",    # 夸克云盘资源收集2
    "kuakeshare",    # 夸克网盘资源分享
]

# 网盘域名映射
PAN_HOSTS = {
    "pan.baidu.com": "baidu",
    "pan.quark.cn": "quark",
    "drive.quark.cn": "quark",
}

# 提取码正则
PASSCODE_RE = re.compile(
    r"(?:\u63d0\u53d6\u7801|\u5bc6\u7801|pwd|pass|passwd|code|key|\u5bc6\u5319)[:\uff1a\s]*([a-zA-Z0-9]{3,6})",
    re.I,
)

# 通用 URL 正则（从正文文本中抓链接）
URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", re.I)

# ============================================================
# 工具函数
# ============================================================

def classify_pan(url):
    """判断 URL 属于哪个网盘"""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    for domain, ptype in PAN_HOSTS.items():
        if host == domain or host.endswith(f".{domain}"):
            return ptype
    return ""


def clean_title(title):
    """只去除表情符号和多余空白，保留完整可读标题"""
    if not title:
        return ""
    title = html_module.unescape(title)
    # 去除 Unicode 表情
    title = re.sub(
        r'[\U0001F300-\U0001F9FF\U0001F600-\U0001F64F\U0001F680-\U0001F6FF'
        r'\U00002600-\U000027BF\U000024C2-\U0001F251]+',
        '', title
    )
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def classify_type(title):
    """简单的关键词匹配分类"""
    t = title.lower()
    keywords = {
        "movie": ["电影", "剧集", "电视剧", "动漫", "动画", "纪录片", "综艺",
                   "4k", "1080p", "2160p", "蓝光", "bd", "hdr", "remux",
                   "漫威", "dc", "迪士尼", "宫崎骏", "新海诚"],
        "music": ["音乐", "专辑", "歌曲", "mp3", "flac", "wav", "无损",
                  "黑胶", "原声", "ost", "演唱", "歌手", "乐队",
                  "piano", "钢琴", "violin", "小提琴", "guitar", "吉他",
                  "曲谱", "谱", "天空之城", "卡农", "菊次郎",
                  "taylor", "swift", "周杰伦", "林俊杰", "陈奕迅"],
        "ebook": ["电子书", "pdf", "epub", "书籍", "图书", "教材",
                  "小说", "漫画", "杂志", "文学", "名著", "传记",
                  "历史", "哲学", "科学"],
        "software": ["软件", "工具", "app", "应用", "破解", "激活",
                     "adobe", "office", "ps", "photoshop", "cad"],
        "learning": ["教程", "课程", "学习", "教学", "培训", "入门",
                     "进阶", "实战", "网课", "公开课",
                     "编程", "python", "java", "javascript", "c++",
                     "前端", "后端", "ai", "人工智能", "机器学习"],
    }
    for type_name, kws in keywords.items():
        for kw in kws:
            if kw.lower() in t:
                return type_name
    return "other"


# ============================================================
# 核心采集逻辑
# ============================================================

def fetch_page(channel, before=""):
    """直接访问 t.me/s/{channel} 页面，返回 HTML"""
    url = f"https://t.me/s/{channel}"
    if before:
        url += f"?before={before}"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code == 200 and "tgme_widget_message" in r.text:
            return r.text
        else:
            print(f"    [fetch] HTTP {r.status_code}, "
                  f"contains tgme: {'tgme_widget_message' in r.text}, "
                  f"size: {len(r.text)}")
            return ""
    except Exception as e:
        print(f"    [fetch error] {type(e).__name__}: {e}")
        return ""


def parse_messages(html_text, channel):
    """用 BeautifulSoup 解析 TG 频道页面，提取网盘链接"""
    soup = BeautifulSoup(html_text, "html.parser")
    results = []

    for msg_wrap in soup.find_all("div", class_="tgme_widget_message_wrap"):
        msg = msg_wrap.find("div", class_="tgme_widget_message")
        if not msg:
            continue

        post_id = msg.get("data-post", "").replace(f"{channel}/", "")
        text_el = msg_wrap.find("div", class_="tgme_widget_message_text")
        raw_text = text_el.get_text("\n").strip() if text_el else ""
        time_el = msg_wrap.find("time")
        msg_time = time_el.get("datetime", "") if time_el else ""

        # 标题 = 正文第一行
        title = raw_text.split("\n")[0].strip() if raw_text else ""
        title = clean_title(title)
        if len(title) < 3:
            title = raw_text[:80].strip() if raw_text else f"{channel} {post_id}"

        # 提取链接：从正文文本 + <a> href 双通道
        seen = set()
        links = []

        # 通道1: 从纯文本中正则匹配 URL
        for url_match in URL_RE.finditer(raw_text):
            url = url_match.group(0)
            ptype = classify_pan(url)
            if not ptype:
                continue
            key = url.lower()
            if key in seen:
                continue
            seen.add(key)
            links.append({"type": ptype, "url": url})

        # 通道2: 从 <a> 标签 href 属性提取
        if text_el:
            for a in text_el.find_all("a", href=True):
                url = a["href"]
                ptype = classify_pan(url)
                if not ptype:
                    continue
                key = url.lower()
                if key in seen:
                    continue
                seen.add(key)
                links.append({"type": ptype, "url": url})

        if not links:
            continue

        # 匹配提取码
        passcodes = PASSCODE_RE.findall(raw_text)
        for link in links:
            url_pos = raw_text.find(link["url"])
            best_code = ""
            best_dist = float("inf")
            for code in passcodes:
                code_pos = raw_text.find(code)
                dist = abs(code_pos - url_pos) if url_pos >= 0 else 9999
                if dist < best_dist:
                    best_dist = dist
                    best_code = code
            if best_code and best_dist < 200:
                link["passcode"] = best_code
            else:
                # 也从 URL 本身提取 ?pwd= 参数
                pwd_match = re.search(r'[?&]pwd=([a-zA-Z0-9]+)', link["url"])
                if pwd_match:
                    link["passcode"] = pwd_match.group(1)
                    link["url"] = re.sub(r'[?&]pwd=[a-zA-Z0-9]+', '', link["url"])
                else:
                    link["passcode"] = ""

        rtype = classify_type(title)

        for link in links:
            results.append({
                "title": title[:100],
                "share_url": link["url"],
                "share_password": link.get("passcode", ""),
                "pan_type": link["type"],
                "resource_type": rtype,
                "source": f"telegram:{channel}:{post_id}",
                "msg_time": msg_time,
            })

    return results


def get_before_link(html_text):
    """获取下一页的 before 参数"""
    soup = BeautifulSoup(html_text, "html.parser")
    for a in soup.find_all("a", href=True):
        if "before=" in a["href"]:
            match = re.search(r"before=([^&]+)", a["href"])
            if match:
                return match.group(1)
    return None


def crawl_channel(channel, max_pages=3):
    """爬取单个频道，翻 max_pages 页"""
    print(f"\n[{channel}] 开始爬取 (max {max_pages} pages)")
    before = ""
    all_results = []
    page = 0

    while page < max_pages:
        html_text = fetch_page(channel, before)
        if not html_text:
            print(f"  [{channel}] Page {page+1}: fetch failed")
            break

        records = parse_messages(html_text, channel)
        if not records:
            print(f"  [{channel}] Page {page+1}: no pan links found")
            break

        all_results.extend(records)
        print(f"  [{channel}] Page {page+1}: {len(records)} links")

        next_before = get_before_link(html_text)
        if not next_before:
            print(f"  [{channel}] No more pages")
            break

        before = next_before
        page += 1
        time.sleep(0.5)

    print(f"  [{channel}] done: {len(all_results)} links from {page+1} pages")
    return all_results


# ============================================================
# 主入口
# ============================================================

def run_crawler():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    os.makedirs("data", exist_ok=True)

    print(f"[crawler] v5 start | {timestamp}")
    print(f"[config] {len(CHANNELS)} channels")

    # 每次随机选 5 个频道，每个频道翻 3 页
    channels_this_run = random.sample(CHANNELS, min(5, len(CHANNELS)))
    print(f"[run] channels: {channels_this_run}")

    all_results = []
    debug_info = []

    for ch in channels_this_run:
        results = crawl_channel(ch, max_pages=3)
        if results:
            all_results.extend(results)
        else:
            debug_info.append({"channel": ch, "status": "no_links"})
        time.sleep(random.uniform(1, 2))

    # 去重
    seen = set()
    unique_results = []
    for r in all_results:
        key = r["share_url"].lower()
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    # 保存
    output = {
        "version": "v5",
        "timestamp": timestamp,
        "channels_visited": channels_this_run,
        "total_found": len(all_results),
        "unique_links": len(unique_results),
        "results": unique_results,
        "debug": debug_info,
    }

    output_file = f"data/batch_github_{timestamp}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[done] saved {len(unique_results)} links to {output_file}")
    print(f"[stats] total={len(all_results)}, unique={len(unique_results)}")
    return output_file


if __name__ == "__main__":
    run_crawler()
