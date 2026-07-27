# NetDisk Spider

网盘搜索引擎 - GitHub Actions 自动爬虫采集系统

## 自动采集流程

1. GitHub Actions 每6小时自动运行爬虫（UTC 00:00/06:00/12:00/18:00）
2. 爬虫扫描全网提取百度网盘和夸克网盘链接
3. 结果以 JSON 格式自动提交到本仓库
4. 本地电脑开机后运行同步脚本，将新数据拉取到 SQLite 数据库

## 仓库结构

| 文件 | 说明 |
|------|------|
| `github_crawler.py` | 云端爬虫脚本 |
| `.github/workflows/crawler.yml` | GitHub Actions 定时任务配置 |
| `scripts/sync_from_github.py` | 本地同步入库脚本 |
| `data/batch_github_*.json` | 云端采集的数据文件（自动生成） |

## 本地同步

```bash
cd F:\DuMate工作区\搜索引擎
python scripts/sync_from_github.py
```

## 技术栈

- Python 3.11 (GitHub Actions)
- Python 3.13 (本地环境)
- SQLite + FTS5 全文检索
- Flask 搜索后端

## 当前数据量

总计 4080+ 条网盘资源（截至2026-07-27）
