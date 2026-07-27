"""
GitHub Actions 云端爬虫
每6小时扫描目标网站，提取网盘链接
"""
import re
import json
import time
import random
import os
import requests
from datetime import datetime
from urllib.parse import quote

# 搜索关键词池（每次随机选3个）
KEYWORDS_POOL = [
    "影视资源 夸克网盘", "音乐合集 百度网盘", "电子书 PDF 网盘",
    "编程教程 Python 网盘", "考研资料 网盘分享", "设计素材 PS 网盘",
    "儿童绘本 网盘", "办公软件 模板 网盘", "健身瑜伽 视频 网盘",
    "有声书 网盘", "纪录片 BBC 网盘", "游戏资源 网盘",
    "钢琴谱 网盘", "无损音乐 FLAC 网盘", "考公资料 网盘"
]


def search_with_ddg(keyword):
    """使用DuckDuckGo搜索获取结果"""
    try:
        url = f"https://html.duckduckgo.com/html/?q={quote(keyword)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        print(f"  [DDG] HTTP {resp.status_code}, {len(resp.text)} bytes")
        return resp.text
    except Exception as e:
        print(f"[错误] DDG搜索失败: {e}")
        return ""


def search_with_bing(keyword):
    """Bing搜索作为备用"""
    try:
        url = f"https://www.bing.com/search?q={quote(keyword)}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        print(f"  [Bing] HTTP {resp.status_code}, {len(resp.text)} bytes")
        return resp.text
    except Exception as e:
        print(f"[错误] Bing搜索失败: {e}")
        return ""


def search(keyword):
    """先DDG，失败则Bing兜底"""
    html = search_with_ddg(keyword)
    if not html or len(html) < 500:
        print(f"  [切换] DDG结果不足，尝试Bing...")
        html = search_with_bing(keyword)
    return html


def extract_links(html_content):
    """从HTML中提取网盘链接，自动识别类型和提取码"""
    results = []

    # 百度网盘链接（支持?pwd=格式）
    baidu_pattern = r'https?://pan\.baidu\.com/s/[a-zA-Z0-9_-]+(?:\?pwd=[a-zA-Z0-9]+)?'
    baidu_matches = re.finditer(baidu_pattern, html_content)

    for match in baidu_matches:
        url = match.group(0)
        # 提取提取码
        password = ""
        pwd_match = re.search(r'pwd=([a-zA-Z0-9]+)', url)
        if pwd_match:
            password = pwd_match.group(1)
            # 清理URL，去掉pwd参数
            url = url.split('?pwd=')[0]

        results.append({
            "url": url,
            "password": password,
            "pan_type": "baidu"
        })

    # 夸克网盘链接（不支持提取码参数）
    quark_pattern = r'https?://pan\.quark\.cn/s/[a-zA-Z0-9]+'
    quark_matches = re.finditer(quark_pattern, html_content)

    for match in quark_matches:
        url = match.group(0)
        results.append({
            "url": url,
            "password": "",
            "pan_type": "quark"
        })

    return results


def extract_title(html_content, url, start_idx):
    """从链接上下文提取标题"""
    # 在链接前后300字符查找标题
    start = max(0, start_idx - 300)
    end = min(len(html_content), start_idx + 300)
    context = html_content[start:end]

    # 尝试提取中文标题（4-50字符）
    title = "未知资源"
    # 匹配链接前或后的中文文本
    title_match = re.search(r'[\u4e00-\u9fff\w\s]{4,50}(?=.*?' + re.escape(url[-20:]) + r')', context)
    if not title_match:
        # 尝试匹配链接后的文本
        title_match = re.search(r'[\u4e00-\u9fff\w\s]{4,50}', context)

    if title_match:
        title = title_match.group(0).strip()

    # 清理标题中的HTML标签残留
    title = re.sub(r'<[^>]+>', '', title)
    title = title[:50]  # 截断到50字符

    return title


def run_crawler():
    """主爬虫逻辑"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    all_results = []

    # 确保data目录存在
    os.makedirs("data", exist_ok=True)

    # 随机选3个关键词
    keywords = random.sample(KEYWORDS_POOL, min(3, len(KEYWORDS_POOL)))
    print(f"[爬虫] 本轮关键词: {keywords}")

    for kw in keywords:
        print(f"[搜索] {kw} ...")
        html = search(kw)

        if not html:
            print(f"  [跳过] {kw} 无搜索结果")
            continue

        # 提取所有链接（带位置信息用于上下文解析）
        links_info = extract_links(html)
        print(f"[提取] 找到 {len(links_info)} 个链接")

        for info in links_info:
            # 查找链接在HTML中的位置
            idx = html.find(info["url"])
            title = extract_title(html, info["url"], idx)

            all_results.append({
                "title": title,
                "share_url": info["url"],
                "share_password": info["password"],
                "pan_type": info["pan_type"],
                "resource_type": "other",
                "source": "github_actions",
                "keyword": kw
            })

        # 随机延迟，避免被封
        time.sleep(random.uniform(3, 8))

    # 去重（基于share_url）
    seen = set()
    unique_results = []
    for r in all_results:
        if r["share_url"] not in seen:
            seen.add(r["share_url"])
            unique_results.append(r)

    # 保存到输出文件
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

    print(f"[完成] 保存 {len(unique_results)} 条链接到 {output_file}")
    return output_file


if __name__ == "__main__":
    run_crawler()
