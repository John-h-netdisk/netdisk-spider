"""
GitHub Actions 云端爬虫 v4
使用 r.jina.ai 文本提取服务访问TG频道，获取纯文本+链接
"""
import re
import json
import time
import random
import os
import requests
from datetime import datetime

# 网盘链接正则
BAIDU_PATTERN = re.compile(r'https?://pan\.baidu\.com/s/[a-zA-Z0-9_-]+(?:\?pwd=[a-zA-Z0-9]+)?')
QUARK_PATTERN = re.compile(r'https?://pan\.quark\.cn/s/[a-zA-Z0-9]+')

# 种子页面列表
SEED_PAGES = [
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
    "https://t.me/s/Quark_1",
    "https://t.me/s/Quark_2",
    "https://t.me/s/Quark_3",
    "https://t.me/s/Baidu_1",
    "https://t.me/s/Baidu_2",
    "https://t.me/s/Baidu_3",
]


def fetch_with_jina(target_url):
    """使用 jina.ai 提取页面纯文本内容"""
    try:
        jina_url = f"https://r.jina.ai/http://{target_url.replace('https://', '').replace('http://', '')}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        print(f"    [jina] {jina_url[:80]}...")
        resp = requests.get(jina_url, headers=headers, timeout=20)
        if resp.status_code == 200:
            text = resp.text
            print(f"    [jina] 成功获取 {len(text)} 字符")
            return text
        else:
            print(f"    [jina] HTTP {resp.status_code}")
            return ""
    except Exception as e:
        print(f"    [jina错误] {type(e).__name__}: {e}")
        return ""


def fetch_direct(target_url):
    """直接访问页面"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        resp = requests.get(target_url, headers=headers, timeout=15, allow_redirects=True)
        resp.encoding = resp.apparent_encoding or 'utf-8'
        print(f"    [direct] HTTP {resp.status_code}, {len(resp.text)} bytes")
        return resp.text
    except Exception as e:
        print(f"    [direct错误] {type(e).__name__}: {e}")
        return ""


def extract_links(text_content, page_url):
    """从文本中提取网盘链接和标题"""
    results = []

    # 百度网盘
    for match in BAIDU_PATTERN.finditer(text_content):
        url = match.group(0)
        password = ""
        pwd_match = re.search(r'pwd=([a-zA-Z0-9]+)', url)
        if pwd_match:
            password = pwd_match.group(1)
            url = url.split('?pwd=')[0]

        # 从上下文提取标题（jina.ai会在链接后放文本描述）
        idx = match.start()
        context = text_content[max(0, idx-300):idx+300]
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
    for match in QUARK_PATTERN.finditer(text_content):
        url = match.group(0)

        idx = match.start()
        context = text_content[max(0, idx-300):idx+300]
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
    # jina.ai 的格式通常是 "Title: [标题]\nURL: [url]\n..."
    # 先尝试匹配 jina.ai 的 Title 行
    title_match = re.search(r'Title:\s*(.+)', context)
    if title_match:
        title = title_match.group(1).strip()
    else:
        # 匹配中文标题
        title_match = re.search(r'[\u4e00-\u9fff\w\s·\-：【】[]{4,50}', context)
        if title_match:
            title = title_match.group(0).strip()

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

    print(f"[爬虫] 启动云端爬虫 v4 | {timestamp}")
    print(f"[配置] 种子页面: {len(SEED_PAGES)} 个")

    # 随机选3-5个种子页面
    pages_to_visit = random.sample(SEED_PAGES, min(5, len(SEED_PAGES)))
    print(f"[访问] 本轮访问 {len(pages_to_visit)} 个页面")

    for page_url in pages_to_visit:
        print(f"\n[抓取] {page_url}")

        # 先尝试 jina.ai 提取
        text = fetch_with_jina(page_url)

        if not text:
            print("    [jina失败] 尝试直接访问...")
            text = fetch_direct(page_url)

        if not text:
            print("    [跳过] 两种方法都失败")
            continue

        links = extract_links(text, page_url)
        if links:
            print(f"    [命中] 找到 {len(links)} 个网盘链接")
            for link in links[:3]:
                print(f"      - {link['pan_type']} | {link['title'][:30]}... | {link['share_url'][:50]}...")
            all_results.extend(links)
        else:
            has_pan = 'pan.baidu.com' in text or 'pan.quark.cn' in text
            print(f"    [未命中] 页面中{'包含' if has_pan else '不含'} pan 关键词")
            if not has_pan and len(text) > 0:
                # 打印前200字符帮助调试
                preview = text[:200].replace('\n', ' ')
                print(f"    [预览] {preview}...")

        time.sleep(random.uniform(2, 5))

    # 去重
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
