"""
GitHub Actions 云端爬虫 v3
直接访问已知资源站点，提取网盘链接
"""
import re
import json
import time
import random
import os
import requests
from datetime import datetime
from urllib.parse import quote

# 网盘链接正则
BAIDU_PATTERN = re.compile(r'https?://pan\.baidu\.com/s/[a-zA-Z0-9_-]+(?:\?pwd=[a-zA-Z0-9]+)?')
QUARK_PATTERN = re.compile(r'https?://pan\.quark\.cn/s/[a-zA-Z0-9]+')

# 种子页面列表（直接访问提取链接）
SEED_PAGES = [
    # Telegram 公开频道（t.me/s/ 不需要登录）
    "https://t.me/s/Aliyun_1",
    "https://t.me/s/Aliyun_2",
    "https://t.me/s/Aliyun_4",
    "https://t.me/s/Aliyun_drive",
    "https://t.me/s/Quark_Movies",
    "https://t.me/s/baidu_share",
    "https://t.me/s/Quark_Share",
    "https://t.me/s/pan_baidu",
    "https://t.me/s/pan_quark",
    "https://t.me/s/Netdisk_Resources",
    "https://t.me/s/Music_Share_Zone",
    "https://t.me/s/Book_Share_Zone",
    "https://t.me/s/Movie_Share_Zone",
    "https://t.me/s/Software_Share_Zone",
    "https://t.me/s/Aliyun_3",
    "https://t.me/s/Aliyun_5",
    "https://t.me/s/Aliyun_6",
    "https://t.me/s/Aliyun_7",
    "https://t.me/s/Aliyun_8",
    # 可以添加更多种子页面
]


def fetch_page(url, timeout=15):
    """访问页面，返回HTML内容"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.encoding = resp.apparent_encoding or 'utf-8'
        return resp.text
    except Exception as e:
        print(f"    [页面错误] {url[:50]}... {type(e).__name__}: {e}")
        return ""


def extract_links_from_html(html_content, page_url):
    """从HTML中提取网盘链接和标题"""
    results = []

    # 百度网盘
    for match in BAIDU_PATTERN.finditer(html_content):
        url = match.group(0)
        password = ""
        pwd_match = re.search(r'pwd=([a-zA-Z0-9]+)', url)
        if pwd_match:
            password = pwd_match.group(1)
            url = url.split('?pwd=')[0]

        # 从上下文提取标题
        idx = match.start()
        context = html_content[max(0, idx-200):idx+200]
        title = extract_title(context)

        results.append({
            "title": title,
            "share_url": url,
            "share_password": password,
            "pan_type": "baidu",
            "resource_type": "other",
            "source": "github_actions",
            "keyword": "",
            "page_url": page_url
        })

    # 夸克网盘
    for match in QUARK_PATTERN.finditer(html_content):
        url = match.group(0)

        idx = match.start()
        context = html_content[max(0, idx-200):idx+200]
        title = extract_title(context)

        results.append({
            "title": title,
            "share_url": url,
            "share_password": "",
            "pan_type": "quark",
            "resource_type": "other",
            "source": "github_actions",
            "keyword": "",
            "page_url": page_url
        })

    return results


def extract_title(context):
    """从上下文提取标题"""
    title = "未知资源"
    # 匹配中文标题
    title_match = re.search(r'[\u4e00-\u9fff\w\s·\-：【】[]{4,50}', context)
    if title_match:
        title = title_match.group(0).strip()
    # 清理HTML标签
    title = re.sub(r'<[^>]+>', '', title)
    title = re.sub(r'https?://\S+', '', title).strip()
    if not title or len(title) < 2:
        title = "未知资源"
    return title[:50]


def run_crawler():
    """主爬虫逻辑"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    all_results = []

    os.makedirs("data", exist_ok=True)

    print(f"[爬虫] 启动云端爬虫 v3 | {timestamp}")
    print(f"[配置] 种子页面: {len(SEED_PAGES)} 个")

    # 随机选3-5个种子页面（避免同时访问太多被封）
    pages_to_visit = random.sample(SEED_PAGES, min(4, len(SEED_PAGES)))
    print(f"[访问] 本轮访问 {len(pages_to_visit)} 个页面")

    for page_url in pages_to_visit:
        print(f"\n[抓取] {page_url}")
        html = fetch_page(page_url)

        if not html:
            print("    [跳过] 页面获取失败")
            continue

        print(f"    [页面] {len(html)} 字节")

        links = extract_links_from_html(html, page_url)
        if links:
            print(f"    [命中] 找到 {len(links)} 个网盘链接")
            for link in links[:3]:  # 只打印前3条预览
                print(f"      - {link['pan_type']} | {link['title'][:30]}... | {link['share_url'][:50]}...")
            all_results.extend(links)
        else:
            # 检查页面是否包含任何 pan 关键词（确认不是被反爬）
            has_pan = 'pan.baidu.com' in html or 'pan.quark.cn' in html
            print(f"    [未命中] 页面中{'包含' if has_pan else '不含'} pan 关键词")

        time.sleep(random.uniform(2, 5))

    # 去重（基于share_url）
    seen = set()
    unique_results = []
    for r in all_results:
        if r["share_url"] not in seen:
            seen.add(r["share_url"])
            unique_results.append(r)

    # 保存
    output = {
        "timestamp": timestamp,
        "keywords": pages_to_visit,
        "total_found": len(all_results),
        "unique_links": len(unique_results),
        "results": unique_results
    }

    output_file = f"data/batch_github_{timestamp}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[完成] 保存 {len(unique_results)} 条链接到 {output_file}")
    print(f"[统计] 总发现 {len(all_results)} 条, 去重后 {len(unique_results)} 条")
    return output_file


if __name__ == "__main__":
    run_crawler()
