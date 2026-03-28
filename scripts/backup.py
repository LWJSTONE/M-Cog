#!/usr/bin/env python3
"""
M-Cog 备份脚本
"""

import os
import sys
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
import argparse

logging.basicConfig(level=logging.INFO, format='%(asctime)s [BACKUP] %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent


def create_backup(backup_dir: Path = None, include_models: bool = False) -> Path:
    """创建系统备份"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = backup_dir or PROJECT_ROOT / "backups"
    backup_path = backup_dir / f"backup_{timestamp}"
    
    backup_path.mkdir(parents=True, exist_ok=True)
    
    # 备份配置
    config_src = PROJECT_ROOT / "config.json"
    if config_src.exists():
        shutil.copy(config_src, backup_path / "config.json")
        logger.info("Backed up config.json")
    
    # 备份知识库
    knowledge_src = PROJECT_ROOT / "mutable" / "knowledge"
    if knowledge_src.exists():
        knowledge_dst = backup_path / "knowledge"
        shutil.copytree(knowledge_src, knowledge_dst)
        logger.info("Backed up knowledge database")
    
    # 备份记忆
    memory_src = PROJECT_ROOT / "mutable" / "memory"
    if memory_src.exists():
        memory_dst = backup_path / "memory"
        shutil.copytree(memory_src, memory_dst)
        logger.info("Backed up memory")
    
    # 备份工具
    tools_src = PROJECT_ROOT / "mutable" / "tools"
    if tools_src.exists():
        tools_dst = backup_path / "tools"
        shutil.copytree(tools_src, tools_dst)
        logger.info("Backed up tools")
    
    # 备份进化日志
    logs_src = PROJECT_ROOT / "mutable" / "evolution_logs"
    if logs_src.exists():
        logs_dst = backup_path / "evolution_logs"
        shutil.copytree(logs_src, logs_dst)
        logger.info("Backed up evolution logs")
    
    # 可选：备份模型
    if include_models:
        models_src = PROJECT_ROOT / "mutable" / "models"
        if models_src.exists():
            models_dst = backup_path / "models"
            shutil.copytree(models_src, models_dst)
            logger.info("Backed up models")
    
    # 创建备份元数据
    metadata = {
        "timestamp": timestamp,
        "created_at": datetime.now().isoformat(),
        "include_models": include_models,
        "files": list(str(p.relative_to(backup_path)) for p in backup_path.rglob("*") if p.is_file())
    }
    
    with open(backup_path / "metadata.json", 'w') as f:
        json.dump(metadata, f, indent=2)
    
    logger.info(f"Backup created at: {backup_path}")
    return backup_path


def restore_backup(backup_path: Path) -> None:
    """从备份恢复"""
    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")
    
    # 读取元数据
    metadata_file = backup_path / "metadata.json"
    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        logger.info(f"Restoring backup from: {metadata['created_at']}")
    
    # 恢复知识库
    knowledge_backup = backup_path / "knowledge"
    if knowledge_backup.exists():
        knowledge_dst = PROJECT_ROOT / "mutable" / "knowledge"
        if knowledge_dst.exists():
            shutil.rmtree(knowledge_dst)
        shutil.copytree(knowledge_backup, knowledge_dst)
        logger.info("Restored knowledge database")
    
    # 恢复记忆
    memory_backup = backup_path / "memory"
    if memory_backup.exists():
        memory_dst = PROJECT_ROOT / "mutable" / "memory"
        if memory_dst.exists():
            shutil.rmtree(memory_dst)
        shutil.copytree(memory_backup, memory_dst)
        logger.info("Restored memory")
    
    # 恢复工具
    tools_backup = backup_path / "tools"
    if tools_backup.exists():
        tools_dst = PROJECT_ROOT / "mutable" / "tools"
        if tools_dst.exists():
            shutil.rmtree(tools_dst)
        shutil.copytree(tools_backup, tools_dst)
        logger.info("Restored tools")
    
    # 恢复进化日志
    logs_backup = backup_path / "evolution_logs"
    if logs_backup.exists():
        logs_dst = PROJECT_ROOT / "mutable" / "evolution_logs"
        if logs_dst.exists():
            shutil.rmtree(logs_dst)
        shutil.copytree(logs_backup, logs_dst)
        logger.info("Restored evolution logs")
    
    logger.info("Restore completed")


def list_backups(backup_dir: Path = None) -> list:
    """列出所有备份"""
    backup_dir = backup_dir or PROJECT_ROOT / "backups"
    
    if not backup_dir.exists():
        return []
    
    backups = []
    for backup_path in sorted(backup_dir.iterdir(), reverse=True):
        if backup_path.is_dir() and backup_path.name.startswith("backup_"):
            metadata_file = backup_path / "metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                backups.append({
                    "path": str(backup_path),
                    "timestamp": metadata.get("timestamp", "unknown"),
                    "created_at": metadata.get("created_at", "unknown"),
                    "file_count": len(metadata.get("files", []))
                })
            else:
                backups.append({
                    "path": str(backup_path),
                    "timestamp": backup_path.name.replace("backup_", ""),
                    "created_at": "unknown",
                    "file_count": "unknown"
                })
    
    return backups


def cleanup_old_backups(backup_dir: Path = None, keep_count: int = 10) -> int:
    """清理旧备份"""
    backup_dir = backup_dir or PROJECT_ROOT / "backups"
    
    if not backup_dir.exists():
        return 0
    
    backups = sorted(
        [p for p in backup_dir.iterdir() if p.is_dir() and p.name.startswith("backup_")],
        reverse=True
    )
    
    deleted = 0
    for backup_path in backups[keep_count:]:
        shutil.rmtree(backup_path)
        logger.info(f"Deleted old backup: {backup_path}")
        deleted += 1
    
    return deleted


def main():
    parser = argparse.ArgumentParser(description='M-Cog Backup Utility')
    parser.add_argument('command', choices=['create', 'restore', 'list', 'cleanup'],
                       help='Command to execute')
    parser.add_argument('--backup-path', type=str, help='Backup path (for restore)')
    parser.add_argument('--include-models', action='store_true', help='Include models in backup')
    parser.add_argument('--keep', type=int, default=10, help='Number of backups to keep')
    
    args = parser.parse_args()
    
    if args.command == 'create':
        create_backup(include_models=args.include_models)
    
    elif args.command == 'restore':
        if not args.backup_path:
            print("Error: --backup-path required for restore")
            sys.exit(1)
        restore_backup(Path(args.backup_path))
    
    elif args.command == 'list':
        backups = list_backups()
        if backups:
            print(f"Found {len(backups)} backups:")
            for b in backups:
                print(f"  - {b['timestamp']}: {b['path']} ({b['file_count']} files)")
        else:
            print("No backups found")
    
    elif args.command == 'cleanup':
        deleted = cleanup_old_backups(keep_count=args.keep)
        print(f"Deleted {deleted} old backups")


if __name__ == '__main__':
    main()
