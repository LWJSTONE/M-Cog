#!/usr/bin/env python3
"""
M-Cog 冷启动引导程序
负责初始化系统、加载种子数据、创建必要的目录结构和数据库
"""

import os
import sys
import json
import sqlite3
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [BOOTSTRAP] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class Bootstrapper:
    """M-Cog 系统引导初始化器"""
    
    def __init__(self, project_root: Path = None):
        self.project_root = project_root or PROJECT_ROOT
        self.mutable_dir = self.project_root / "mutable"
        self.core_dir = self.project_root / "core"
        self.config_path = self.project_root / "config.json"
        
    def check_prerequisites(self) -> bool:
        """检查系统前置条件"""
        logger.info("Checking prerequisites...")
        
        # 检查 Python 版本
        py_version = sys.version_info
        if py_version.major < 3 or (py_version.major == 3 and py_version.minor < 10):
            logger.error(f"Python 3.10+ required, found {py_version.major}.{py_version.minor}")
            return False
        logger.info(f"Python version: {py_version.major}.{py_version.minor}.{py_version.micro}")
        
        # 检查必要的 Python 包
        required_packages = ['sqlite3', 'json', 'threading']
        for pkg in required_packages:
            try:
                __import__(pkg)
                logger.info(f"Package '{pkg}' available")
            except ImportError:
                logger.error(f"Required package '{pkg}' not found")
                return False
        
        # 检查核心目录
        if not self.core_dir.exists():
            logger.error(f"Core directory not found: {self.core_dir}")
            return False
            
        logger.info("Prerequisites check passed")
        return True
    
    def create_directory_structure(self) -> bool:
        """创建目录结构"""
        logger.info("Creating directory structure...")
        
        directories = [
            # mutable 目录
            self.mutable_dir / "knowledge" / "indices",
            self.mutable_dir / "knowledge" / "quarantine",
            self.mutable_dir / "models" / "experts",
            self.mutable_dir / "tools" / "sources",
            self.mutable_dir / "tools" / "compiled",
            self.mutable_dir / "memory" / "replay_logs",
            self.mutable_dir / "evolution_logs" / "snapshots",
            # runtime 目录
            self.project_root / "runtime",
            # webui 目录
            self.project_root / "webui" / "static",
            self.project_root / "webui" / "templates",
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created: {directory}")
        
        # 创建 .gitkeep 文件以保持空目录
        for directory in directories:
            gitkeep = directory / ".gitkeep"
            gitkeep.touch(exist_ok=True)
            
        return True
    
    def init_knowledge_graph(self, seed_data: Dict = None) -> bool:
        """初始化知识图谱数据库"""
        logger.info("Initializing knowledge graph database...")
        
        db_path = self.mutable_dir / "knowledge" / "graph.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        try:
            # 创建节点表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS nodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL CHECK(type IN ('entity', 'concept', 'value')),
                    description TEXT,
                    created_at INTEGER NOT NULL,
                    confidence REAL DEFAULT 1.0 CHECK(confidence >= 0 AND confidence <= 1)
                )
            ''')
            
            # 创建关系表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject_id INTEGER NOT NULL,
                    predicate TEXT NOT NULL,
                    object_id INTEGER NOT NULL,
                    conditions TEXT DEFAULT '{}',
                    confidence_dist TEXT DEFAULT '{"low": 0.0, "medium": 0.5, "high": 0.5}',
                    source TEXT DEFAULT 'bootstrap',
                    created_at INTEGER NOT NULL,
                    last_used INTEGER,
                    FOREIGN KEY(subject_id) REFERENCES nodes(id),
                    FOREIGN KEY(object_id) REFERENCES nodes(id)
                )
            ''')
            
            # 创建价值分层表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS value_layers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    value_name TEXT UNIQUE NOT NULL,
                    layer TEXT NOT NULL CHECK(layer IN ('core', 'universal', 'surface')),
                    description TEXT,
                    immutable BOOLEAN DEFAULT 0
                )
            ''')
            
            # 创建隔离区表（新知识暂存）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quarantine (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    object TEXT NOT NULL,
                    conditions TEXT DEFAULT '{}',
                    source TEXT,
                    created_at INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
                    reviewed_at INTEGER
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_relations_subject ON relations(subject_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_relations_object ON relations(object_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_relations_predicate ON relations(predicate)')
            
            conn.commit()
            logger.info("Knowledge graph tables created")
            
            # 加载种子数据
            if seed_data:
                self._load_seed_data(cursor, seed_data)
            
            # 提交所有更改
            conn.commit()
            logger.info("Knowledge graph initialization complete")
                
        except Exception as e:
            logger.error(f"Failed to initialize knowledge graph: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
            
        return True
    
    def _load_seed_data(self, cursor, seed_data: Dict) -> None:
        """加载种子知识数据"""
        current_time = int(datetime.now().timestamp())
        
        # 加载事实
        facts = seed_data.get('facts', [])
        for fact in facts:
            # 插入或获取 subject
            cursor.execute('''
                INSERT OR IGNORE INTO nodes (name, type, description, created_at, confidence)
                VALUES (?, 'entity', '', ?, 1.0)
            ''', (fact.get('subject'), current_time))
            
            cursor.execute('SELECT id FROM nodes WHERE name = ?', (fact.get('subject'),))
            subject_id = cursor.fetchone()[0]
            
            # 插入或获取 object
            cursor.execute('''
                INSERT OR IGNORE INTO nodes (name, type, description, created_at, confidence)
                VALUES (?, 'value', '', ?, 1.0)
            ''', (fact.get('object'), current_time))
            
            cursor.execute('SELECT id FROM nodes WHERE name = ?', (fact.get('object'),))
            object_id = cursor.fetchone()[0]
            
            # 插入关系
            conditions = json.dumps({"context": fact.get('conditions', '')})
            cursor.execute('''
                INSERT INTO relations (subject_id, predicate, object_id, conditions, source, created_at)
                VALUES (?, ?, ?, ?, 'seed', ?)
            ''', (subject_id, fact.get('predicate'), object_id, conditions, current_time))
        
        logger.info(f"Loaded {len(facts)} seed facts")
        
        # 加载价值
        values = seed_data.get('values', [])
        for value in values:
            immutable = 1 if value.get('immutable', False) else 0
            cursor.execute('''
                INSERT OR IGNORE INTO value_layers (value_name, layer, description, immutable)
                VALUES (?, ?, '', ?)
            ''', (value.get('name'), value.get('layer'), immutable))
        
        logger.info(f"Loaded {len(values)} seed values")
    
    def init_episodic_memory(self) -> bool:
        """初始化情景记忆数据库"""
        logger.info("Initializing episodic memory database...")
        
        db_path = self.mutable_dir / "memory" / "episodic.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    user_input TEXT NOT NULL,
                    system_output TEXT,
                    user_feedback TEXT CHECK(user_feedback IN ('positive', 'negative', 'correction', 'neutral', NULL)),
                    satisfaction_score REAL CHECK(satisfaction_score >= 0 AND satisfaction_score <= 1),
                    error_type TEXT,
                    context_hash TEXT,
                    importance REAL DEFAULT 0.5 CHECK(importance >= 0 AND importance <= 1),
                    session_id TEXT,
                    metadata TEXT DEFAULT '{}'
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_episodes_importance ON episodes(importance)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_episodes_feedback ON episodes(user_feedback)')
            
            conn.commit()
            logger.info("Episodic memory tables created")
            
        except Exception as e:
            logger.error(f"Failed to initialize episodic memory: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
            
        return True
    
    def init_evolution_logs(self) -> bool:
        """初始化进化日志数据库"""
        logger.info("Initializing evolution logs database...")
        
        db_path = self.mutable_dir / "evolution_logs" / "changes.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    change_type TEXT NOT NULL CHECK(change_type IN ('knowledge', 'model', 'tool', 'config', 'self')),
                    description TEXT NOT NULL,
                    before_state TEXT,
                    after_state TEXT,
                    trigger TEXT,
                    success BOOLEAN DEFAULT 1,
                    rollback_info TEXT
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    snapshot_type TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    checksum TEXT,
                    metadata TEXT DEFAULT '{}'
                )
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_changes_timestamp ON changes(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_changes_type ON changes(change_type)')
            
            conn.commit()
            logger.info("Evolution logs tables created")
            
        except Exception as e:
            logger.error(f"Failed to initialize evolution logs: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
            
        return True
    
    def init_tool_registry(self) -> bool:
        """初始化工具注册表"""
        logger.info("Initializing tool registry...")
        
        registry_path = self.mutable_dir / "tools" / "registry.json"
        
        default_registry = {
            "tools": [],
            "combinators": [],
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "version": "1.0.0"
            }
        }
        
        with open(registry_path, 'w', encoding='utf-8') as f:
            json.dump(default_registry, f, indent=2, ensure_ascii=False)
        
        logger.info("Tool registry initialized")
        return True
    
    def init_working_memory(self) -> bool:
        """初始化工作记忆"""
        logger.info("Initializing working memory...")
        
        memory_path = self.mutable_dir / "memory" / "working.json"
        
        default_memory = {
            "session_id": "",
            "active_context": {
                "entities": [],
                "goals": [],
                "temporary_facts": []
            },
            "turn_count": 0,
            "last_action": None,
            "created_at": datetime.now().isoformat()
        }
        
        with open(memory_path, 'w', encoding='utf-8') as f:
            json.dump(default_memory, f, indent=2, ensure_ascii=False)
        
        logger.info("Working memory initialized")
        return True
    
    def create_default_config(self) -> bool:
        """创建默认配置文件"""
        logger.info("Creating default configuration...")
        
        if self.config_path.exists():
            logger.info("Configuration file already exists, skipping")
            return True
        
        default_config = {
            "system": {
                "name": "M-Cog",
                "version": "1.0.0",
                "debug_mode": False
            },
            "scheduler": {
                "max_concurrent_p0": 4,
                "max_concurrent_p1": 2,
                "max_concurrent_p2": 1,
                "max_memory_mb": 4096,
                "monitor_interval_ms": 10
            },
            "knowledge": {
                "graph_db_path": "mutable/knowledge/graph.db",
                "index_path": "mutable/knowledge/indices",
                "quarantine_enabled": True,
                "auto_promote_threshold": 0.8,
                "decay_enabled": True,
                "decay_interval_days": 7
            },
            "memory": {
                "working_memory_path": "mutable/memory/working.json",
                "episodic_db_path": "mutable/memory/episodic.db",
                "max_working_facts": 100,
                "episode_importance_threshold": 0.5
            },
            "models": {
                "experts_dir": "mutable/models/experts",
                "router_path": "mutable/models/router.onnx",
                "max_active_experts": 3,
                "quantization": "int8"
            },
            "tools": {
                "registry_path": "mutable/tools/registry.json",
                "sources_dir": "mutable/tools/sources",
                "compiled_dir": "mutable/tools/compiled",
                "sandbox_enabled": True,
                "max_tool_cpu_ms": 100,
                "max_tool_memory_mb": 50
            },
            "evolution": {
                "enabled": True,
                "logs_db_path": "mutable/evolution_logs/changes.db",
                "snapshots_dir": "mutable/evolution_logs/snapshots",
                "snapshot_interval_hours": 24,
                "max_snapshots": 30
            },
            "reflection": {
                "micro_trigger_threshold": 0.3,
                "macro_trigger_days": 3,
                "deep_trigger_days": 7,
                "min_episodes_for_analysis": 100
            },
            "learning": {
                "user_feedback_weight": 0.8,
                "self_play_weight": 0.3,
                "doc_ingestion_weight": 0.5,
                "sleep_replay_enabled": True,
                "sleep_replay_time": "02:00"
            },
            "safety": {
                "core_module_path": "core/safety_hardcode.so",
                "strict_mode": True,
                "log_all_checks": True
            },
            "webui": {
                "host": "127.0.0.1",
                "port": 5000,
                "debug": False
            }
        }
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Configuration file created: {self.config_path}")
        return True
    
    def get_seed_knowledge(self) -> Dict:
        """获取种子知识数据"""
        return {
            "facts": [
                # 物理常识
                {"subject": "water", "predicate": "boiling_point", "object": "100_C", "conditions": "standard_atmosphere"},
                {"subject": "water", "predicate": "freezing_point", "object": "0_C", "conditions": "standard_atmosphere"},
                {"subject": "earth", "predicate": "shape", "object": "spherical", "conditions": ""},
                {"subject": "earth", "predicate": "gravity", "object": "9.8_m_s2", "conditions": "sea_level"},
                {"subject": "light", "predicate": "speed", "object": "299792458_m_s", "conditions": "vacuum"},
                
                # 逻辑规则
                {"subject": "true", "predicate": "and", "object": "true", "conditions": "yields_true"},
                {"subject": "false", "predicate": "and", "object": "any", "conditions": "yields_false"},
                {"subject": "true", "predicate": "or", "object": "any", "conditions": "yields_true"},
                
                # 时间概念
                {"subject": "day", "predicate": "has_hours", "object": "24", "conditions": ""},
                {"subject": "hour", "predicate": "has_minutes", "object": "60", "conditions": ""},
                {"subject": "minute", "predicate": "has_seconds", "object": "60", "conditions": ""},
                
                # 人类基本需求
                {"subject": "human", "predicate": "needs", "object": "food", "conditions": "survival"},
                {"subject": "human", "predicate": "needs", "object": "water", "conditions": "survival"},
                {"subject": "human", "predicate": "needs", "object": "sleep", "conditions": "health"},
                {"subject": "human", "predicate": "needs", "object": "shelter", "conditions": "protection"},
                
                # 情感
                {"subject": "happiness", "predicate": "is", "object": "positive_emotion", "conditions": ""},
                {"subject": "sadness", "predicate": "is", "object": "negative_emotion", "conditions": ""},
                {"subject": "anger", "predicate": "is", "object": "negative_emotion", "conditions": ""},
                
                # 社会规则
                {"subject": "lying", "predicate": "is", "object": "generally_wrong", "conditions": "most_contexts"},
                {"subject": "helping_others", "predicate": "is", "object": "good", "conditions": "general"},
                {"subject": "stealing", "predicate": "is", "object": "wrong", "conditions": "all_contexts"},
            ],
            "values": [
                # 核心层价值（不可变）
                {"name": "do_not_harm", "layer": "core", "immutable": True},
                {"name": "be_honest", "layer": "core", "immutable": True},
                {"name": "respect_autonomy", "layer": "core", "immutable": True},
                {"name": "protect_privacy", "layer": "core", "immutable": True},
                
                # 普遍层价值
                {"name": "helpfulness", "layer": "universal", "immutable": False},
                {"name": "fairness", "layer": "universal", "immutable": False},
                {"name": "kindness", "layer": "universal", "immutable": False},
                {"name": "responsibility", "layer": "universal", "immutable": False},
                
                # 表面层价值（可变）
                {"name": "efficiency", "layer": "surface", "immutable": False},
                {"name": "politeness", "layer": "surface", "immutable": False},
                {"name": "creativity", "layer": "surface", "immutable": False},
            ]
        }
    
    def bootstrap(self, seed_file: str = None) -> bool:
        """执行完整的引导初始化"""
        logger.info("="*60)
        logger.info("Starting M-Cog Bootstrap Process")
        logger.info("="*60)
        
        # 1. 检查前置条件
        if not self.check_prerequisites():
            return False
        
        # 2. 创建目录结构
        if not self.create_directory_structure():
            return False
        
        # 3. 创建默认配置
        if not self.create_default_config():
            return False
        
        # 4. 加载种子数据
        seed_data = self.get_seed_knowledge()
        if seed_file:
            try:
                with open(seed_file, 'r', encoding='utf-8') as f:
                    custom_seed = json.load(f)
                    seed_data.update(custom_seed)
                    logger.info(f"Loaded custom seed data from: {seed_file}")
            except Exception as e:
                logger.warning(f"Could not load custom seed file: {e}")
        
        # 5. 初始化知识图谱
        if not self.init_knowledge_graph(seed_data):
            return False
        
        # 6. 初始化情景记忆
        if not self.init_episodic_memory():
            return False
        
        # 7. 初始化进化日志
        if not self.init_evolution_logs():
            return False
        
        # 8. 初始化工具注册表
        if not self.init_tool_registry():
            return False
        
        # 9. 初始化工作记忆
        if not self.init_working_memory():
            return False
        
        logger.info("="*60)
        logger.info("M-Cog Bootstrap Complete!")
        logger.info("="*60)
        logger.info("Next steps:")
        logger.info("  1. Review config.json for system configuration")
        logger.info("  2. Compile C modules: make -C core")
        logger.info("  3. Install Python dependencies: pip install -r requirements.txt")
        logger.info("  4. Start system: python main.py")
        
        return True


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='M-Cog Bootstrap')
    parser.add_argument('--seed-data', type=str, help='Path to custom seed data JSON file')
    parser.add_argument('--project-root', type=str, help='Project root directory')
    
    args = parser.parse_args()
    
    project_root = Path(args.project_root) if args.project_root else None
    bootstrapper = Bootstrapper(project_root)
    
    success = bootstrapper.bootstrap(args.seed_data)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
