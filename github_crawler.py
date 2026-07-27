"""
GitHub Actions 云端爬虫 v2
两步采集：搜索引擎获取页面URL → 访问页面提取网盘链接
"""
import re
import json
import time
import random
import os
import requests
from datetime import datetime
from urllib.parse import quote, urljoin

# 搜索关键词池（每次随机选3个）
KEYWORDS_POOL = [
    "影视资源 夸克网盘", "音乐合集 百度网盘", "电子书 PDF 网盘",
    "编程教程 Python 网盘", "考研资料 网盘分享", "设计素材 PS 网盘",
    "儿童绘本 网盘", "办公软件 模板 网盘", "健身瑜伽 视频 网盘",
    "有声书 网盘", "纪录片 BBC 网盘", "游戏资源 网盘",
    "钢琴谱 网盘", "无损音乐 FLAC 网盘", "考公资料 网盘"
]

# 网盘链接正则
BAIDU_PATTERN = re.compile(r'https?://pan\.baidu\.com/s/[a-zA-Z0-9_-]+(?:\?pwd=[a-zA-Z0-9]+)?')
QUARK_PATTERN = re.compile(r'https?://pan\.quark\.cn/s/[a-zA-Z0-9]+')


def search_ddg(keyword):
    """DuckDuckGo搜索，返回结果页面URL列表"""
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote(keyword)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        # DDG HTML版本的结果链接在 <a class="result__a" href="..."> 中
        # 但实际URL被DDG包裹成 /l/?uddg=ENCODURL 格式
        links = []
        # 提取uddg参数中的真实URL
        uddg_matches = re.findall(r'uddg=([^&"]+)', resp.text)
        for encoded_url in uddg_matches:
            from urllib.parse import unquote
            real_url = unquote(encoded_url)
            if real_url.startswith('http') and 'duckduckgo' not in real_url:
                links.append(real_url)
        print(f"  [DDG] HTTP {resp.status_code}, {len(resp.text)} bytes, {len(links)} result URLs")
        return links
    except Exception as e:
        print(f"[错误] DDG搜索失败: {e}")
        return []


def search_bing(keyword):
    """Bing搜索，返回结果页面URL列表"""
    try:
        url = f"https://www.bing.com/search?q={quote(keyword)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        # Bing结果链接在 <a href="https://..."> 中，通常在 class="b_algo" 的 li 内
        links = []
        # 提取所有外部链接
        all_links = re.findall(r'<a[^>]+href="(https?://[^"]+)"[^>]*>', resp.text)
        for link in all_links:
            # 过滤掉bing自身链接和常见无关链接
            skip_domains = ['bing.com', 'microsoft.com', 'msn.com', 'go.microsoft', 'bing.net',
                           'w3.org', 'schema.org', 'live.com', 'skype.com', 'office.com']
            if not any(s in link.lower() for s in skip_domains):
                links.append(link)
        # 去重
        links = list(dict.fromkeys(links))
        print(f"  [Bing] HTTP {resp.status_code}, {len(resp.text)} bytes, {len(links)} result URLs")
        return links
    except Exception as e:
        print(f"[错误] Bing搜索失败: {e}")
        return []


def search(keyword):
    """先DDG，失败则Bing兜底"""
    links = search_ddg(keyword)
    if not links:
        print(f"  [切换] DDG无结果，尝试Bing...")
        links = search_bing(keyword)
    return links[:8]  # 最多访问前8个结果页面


def fetch_page(url):
    """访问页面，返回HTML内容"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.encoding = resp.apparent_encoding or 'utf-8'
        return resp.text
    except Exception as e:
        print(f"    [页面错误] {url[:60]}... {e}")
        return ""


def extract_links_from_page(html_content, page_url):
    """从页面HTML中提取网盘链接"""
    results = []

    # 百度网盘
    for match in BAIDU_PATTERN.finditer(html_content):
        url = match.group(0)
        password = ""
        pwd_match = re.search(r'pwd=([a-zA-Z0-9]+)', url)
        if pwd_match:
            password = pwd_match.group(1)
            url = url.split('?pwd=')[0]

        # 提取标题：从链接前后200字符
        idx = match.start()
        context = html_content[max(0, idx-200):idx+200]
        title = extract_title(context, url)

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
        title = extract_title(context, url)

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


def extract_title(context, url):
    """从上下文提取标题"""
    title = "未知资源"
    # 尝试匹配中文标题
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

    # 随机选3个关键词
    keywords = random.sample(KEYWORDS_POOL, min(3, len(KEYWORDS_POOL)))
    print(f"[爬虫] 本轮关键词: {keywords}")

    for kw in keywords:
        print(f"\n[搜索] {kw} ...")
        page_urls = search(kw)

        if not page_urls:
            print(f"  [跳过] {kw} 无搜索结果")
            continue

        print(f"  [访问] 准备访问 {len(page_urls)} 个页面")

        for page_url in page_urls:
            print(f"  [抓取] {page_url[:70]}...")
            html = fetch_page(page_url)

            if not html:
                continue

            links = extract_links_from_page(html, page_url)
            if links:
                # 填充关键词
                for l in links:
                    l["keyword"] = kw
                print(f"    [命中] 找到 {len(links)} 个网盘链接")
                all_results.extend(links)

            # 延迟避免封禁
            time.sleep(random.uniform(1, 3))

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
        "keywords": keywords,
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
