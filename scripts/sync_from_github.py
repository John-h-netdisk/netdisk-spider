"""
本地同步脚本：从GitHub仓库拉取云端采集的新数据并入本地SQLite数据库
修复要点：
1. 使用share_url（不是url）
2. 提取pan.baidu.com的pwd参数存入share_password
3. pan_type自动识别baidu/quark
4. source字段必填（固定值github_actions）
5. FTS重建使用虚拟表INSERT语法（避免触发器冲突）
6. 同步前自动备份数据库
"""
import os
import sys
import json
import re
import sqlite3
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# 配置
PROJECT_DIR = Path("F:/DuMate工作区/搜索引擎")
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "search_engine.db"
BACKUP_DIR = DATA_DIR / "backup"


def backup_db():
    """同步前备份数据库"""
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"search_engine_{timestamp}.db"
    shutil.copy2(DB_PATH, backup_path)
    print(f"[备份] 数据库已备份到 {backup_path}")


def pull_latest():
    """从GitHub拉取最新代码"""
    os.chdir(PROJECT_DIR)
    result = subprocess.run(
        ["git", "pull", "origin", "main"],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.returncode != 0:
        print(f"[错误] Git pull失败: {result.stderr}")
        return False
    return True


def rebuild_fts(conn):
    """重建FTS5索引（使用虚拟表INSERT语法，兼容触发器）"""
    c = conn.cursor()
    try:
        c.execute("DELETE FROM resources_fts")
        c.execute("""
            INSERT INTO resources_fts(rowid, title, resource_type, source)
            SELECT id, title, resource_type, source FROM resources
        """)
        conn.commit()
        print("[FTS] 索引重建完成")
    except Exception as e:
        print(f"[警告] FTS重建失败: {e}")
        conn.rollback()


def import_json_to_db(conn, json_file):
    """将单个JSON文件导入数据库"""
    c = conn.cursor()
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    imported = 0
    skipped = 0
    failed = 0
    
    for item in data.get("results", []):
        try:
            # 提取分享链接和提取码
            raw_url = item.get("share_url", "")
            password = item.get("share_password", "")
            pan_type = item.get("pan_type", "quark")
            
            # 再次解析百度链接的pwd参数（双重保险）
            if "pan.baidu.com" in raw_url and "?pwd=" in raw_url:
                pwd_match = re.search(r'pwd=([a-zA-Z0-9]+)', raw_url)
                if pwd_match:
                    password = pwd_match.group(1)
                    raw_url = raw_url.split("?pwd=")[0]
            
            # 检查是否已存在（share_url为唯一键）
            c.execute('SELECT id FROM resources WHERE share_url = ?', (raw_url,))
            if c.fetchone():
                skipped += 1
                continue
            
            # 插入数据（严格匹配数据库列名）
            c.execute('''
                INSERT INTO resources 
                (title, share_url, share_password, pan_type, resource_type, source, valid, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, datetime('now'))
            ''', (
                item.get("title", "未知资源"),
                raw_url,
                password,
                pan_type,
                item.get("resource_type", "other"),
                item.get("source", "github_actions")
            ))
            imported += 1
            
        except Exception as e:
            print(f"[跳过] 导入失败: {e}")
            failed += 1
    
    return imported, skipped, failed


def import_all_batches():
    """导入所有新的GitHub批次文件"""
    conn = sqlite3.connect(DB_PATH)
    
    imported_total = 0
    skipped_total = 0
    failed_total = 0
    
    # 扫描所有 batch_github_*.json 文件
    json_files = sorted(DATA_DIR.glob("batch_github_*.json"))
    
    if not json_files:
        print("[信息] 没有新的GitHub批次文件需要导入")
        conn.close()
        return 0
    
    print(f"[发现] {len(json_files)} 个批次文件")
    
    for json_file in json_files:
        print(f"[导入] {json_file.name} ...")
        imported, skipped, failed = import_json_to_db(conn, json_file)
        imported_total += imported
        skipped_total += skipped
        failed_total += failed
        print(f"       +{imported} 新数据，{skipped} 重复，{failed} 失败")
    
    # 重建FTS索引
    if imported_total > 0:
        rebuild_fts(conn)
    
    conn.close()
    return imported_total


def main():
    print("=" * 60)
    print(" GitHub → 本地数据库同步工具 (修复版)")
    print("=" * 60)
    
    # 检查数据库存在
    if not DB_PATH.exists():
        print(f"[错误] 数据库不存在: {DB_PATH}")
        sys.exit(1)
    
    # 步骤0：备份数据库
    print("\n[步骤0] 备份数据库...")
    backup_db()
    
    # 步骤1：拉取GitHub最新代码
    print("\n[步骤1] 从GitHub拉取最新数据...")
    if not pull_latest():
        print("[终止] Git pull失败，请检查网络或仓库配置")
        sys.exit(1)
    
    # 步骤2：导入新批次
    print("\n[步骤2] 导入新批次数据...")
    imported = import_all_batches()
    
    # 步骤3：报告结果
    print("\n" + "=" * 60)
    if imported > 0:
        print(f"[完成] 成功导入 {imported} 条新资源")
        print("[提示] 索引已自动重建，无需手动运行 setup_fts5.py")
    else:
        print("[完成] 没有新数据需要导入")
    print("=" * 60)


if __name__ == "__main__":
    main()
