#!/usr/bin/env python3
"""
M-Cog 三层记忆系统
包含工作记忆、情景记忆和睡眠重放机制
"""

import json
import sqlite3
import logging
import hashlib
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
import threading
import uuid
import time

logger = logging.getLogger(__name__)


class FeedbackType(Enum):
    """反馈类型"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    CORRECTION = "correction"
    NEUTRAL = "neutral"


@dataclass
class WorkingContext:
    """工作记忆上下文"""
    entities: List[str] = field(default_factory=list)
    goals: List[str] = field(default_factory=list)
    temporary_facts: List[Dict] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkingContext':
        return cls(
            entities=data.get("entities", []),
            goals=data.get("goals", []),
            temporary_facts=data.get("temporary_facts", [])
        )


@dataclass
class WorkingMemory:
    """工作记忆"""
    session_id: str
    active_context: WorkingContext
    turn_count: int
    last_action: Optional[str]
    created_at: str
    last_updated: str
    
    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "active_context": self.active_context.to_dict(),
            "turn_count": self.turn_count,
            "last_action": self.last_action,
            "created_at": self.created_at,
            "last_updated": self.last_updated
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'WorkingMemory':
        return cls(
            session_id=data.get("session_id", ""),
            active_context=WorkingContext.from_dict(data.get("active_context", {})),
            turn_count=data.get("turn_count", 0),
            last_action=data.get("last_action"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_updated=data.get("last_updated", datetime.now().isoformat())
        )


@dataclass
class Episode:
    """情景记忆条目"""
    id: Optional[int] = None
    timestamp: int = 0
    user_input: str = ""
    system_output: str = ""
    user_feedback: Optional[str] = None
    satisfaction_score: float = 0.5
    error_type: Optional[str] = None
    context_hash: str = ""
    importance: float = 0.5
    session_id: str = ""
    metadata: Dict = field(default_factory=dict)
    
    @classmethod
    def from_row(cls, row: tuple) -> 'Episode':
        return cls(
            id=row[0],
            timestamp=row[1],
            user_input=row[2] or "",
            system_output=row[3] or "",
            user_feedback=row[4],
            satisfaction_score=row[5] or 0.5,
            error_type=row[6],
            context_hash=row[7] or "",
            importance=row[8] or 0.5,
            session_id=row[9] or "",
            metadata=json.loads(row[10]) if row[10] else {}
        )
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "user_input": self.user_input,
            "system_output": self.system_output,
            "user_feedback": self.user_feedback,
            "satisfaction_score": self.satisfaction_score,
            "error_type": self.error_type,
            "context_hash": self.context_hash,
            "importance": self.importance,
            "session_id": self.session_id,
            "metadata": self.metadata
        }


class WorkingMemoryManager:
    """工作记忆管理器"""
    
    def __init__(self, memory_path: Path, config: Dict = None):
        self.memory_path = memory_path
        self.config = config or {}
        self.max_facts = self.config.get("max_working_facts", 100)
        
        self._memory: Optional[WorkingMemory] = None
        self._lock = threading.RLock()
        
        self._load()
    
    def _load(self) -> None:
        """加载工作记忆"""
        if self.memory_path.exists():
            try:
                with open(self.memory_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._memory = WorkingMemory.from_dict(data)
                logger.debug("Working memory loaded")
            except Exception as e:
                logger.warning(f"Failed to load working memory: {e}")
                self._create_new()
        else:
            self._create_new()
    
    def _create_new(self) -> None:
        """创建新的工作记忆"""
        now = datetime.now().isoformat()
        self._memory = WorkingMemory(
            session_id=str(uuid.uuid4()),
            active_context=WorkingContext(),
            turn_count=0,
            last_action=None,
            created_at=now,
            last_updated=now
        )
        self._save()
    
    def _save(self) -> None:
        """保存工作记忆"""
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.memory_path, 'w', encoding='utf-8') as f:
            json.dump(self._memory.to_dict(), f, indent=2, ensure_ascii=False)
    
    def start_new_session(self) -> str:
        """开始新会话"""
        with self._lock:
            now = datetime.now().isoformat()
            self._memory = WorkingMemory(
                session_id=str(uuid.uuid4()),
                active_context=WorkingContext(),
                turn_count=0,
                last_action=None,
                created_at=now,
                last_updated=now
            )
            self._save()
            return self._memory.session_id
    
    def get_session_id(self) -> str:
        """获取当前会话ID"""
        with self._lock:
            return self._memory.session_id
    
    def add_entity(self, entity: str) -> None:
        """添加活动实体"""
        with self._lock:
            if entity not in self._memory.active_context.entities:
                self._memory.active_context.entities.append(entity)
                # 保持最多 10 个活动实体
                if len(self._memory.active_context.entities) > 10:
                    self._memory.active_context.entities.pop(0)
                self._save()
    
    def add_goal(self, goal: str) -> None:
        """添加目标"""
        with self._lock:
            if goal not in self._memory.active_context.goals:
                self._memory.active_context.goals.append(goal)
                # 保持最多 4 个目标
                if len(self._memory.active_context.goals) > 4:
                    self._memory.active_context.goals.pop(0)
                self._save()
    
    def add_temporary_fact(self, fact: Dict) -> None:
        """添加临时事实"""
        with self._lock:
            self._memory.active_context.temporary_facts.append(fact)
            # 保持最多 N 个临时事实
            if len(self._memory.active_context.temporary_facts) > self.max_facts:
                self._memory.active_context.temporary_facts.pop(0)
            self._save()
    
    def increment_turn(self, action: str = None) -> int:
        """增加对话轮次"""
        with self._lock:
            self._memory.turn_count += 1
            self._memory.last_action = action
            self._memory.last_updated = datetime.now().isoformat()
            self._save()
            return self._memory.turn_count
    
    def get_context(self) -> WorkingContext:
        """获取当前上下文"""
        with self._lock:
            return self._memory.active_context
    
    def clear_temporary(self) -> None:
        """清除临时记忆"""
        with self._lock:
            self._memory.active_context.temporary_facts = []
            self._save()
    
    def get_full_memory(self) -> Dict:
        """获取完整工作记忆"""
        with self._lock:
            return self._memory.to_dict()


class EpisodicMemoryManager:
    """情景记忆管理器"""
    
    def __init__(self, db_path: Path, config: Dict = None):
        self.db_path = db_path
        self.config = config or {}
        self.importance_threshold = self.config.get("episode_importance_threshold", 0.5)
        
        self._local = threading.local()
        self._write_lock = threading.Lock()
        
        self._ensure_tables()
        logger.info(f"EpisodicMemoryManager initialized: {self.db_path}")
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(str(self.db_path))
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    def _ensure_tables(self) -> None:
        """确保表存在"""
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                user_input TEXT NOT NULL,
                system_output TEXT,
                user_feedback TEXT,
                satisfaction_score REAL,
                error_type TEXT,
                context_hash TEXT,
                importance REAL DEFAULT 0.5,
                session_id TEXT,
                metadata TEXT DEFAULT '{}'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_timestamp ON episodes(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_importance ON episodes(importance)")
        conn.commit()
    
    def _compute_importance(self, episode: Episode) -> float:
        """计算事件重要性"""
        importance = 0.5  # 基础重要性
        
        # 反馈影响
        if episode.user_feedback == FeedbackType.NEGATIVE.value:
            importance += 0.3
        elif episode.user_feedback == FeedbackType.POSITIVE.value:
            importance += 0.1
        elif episode.user_feedback == FeedbackType.CORRECTION.value:
            importance += 0.4
        
        # 满意度影响
        if episode.satisfaction_score < 0.3:
            importance += 0.2
        elif episode.satisfaction_score > 0.8:
            importance += 0.1
        
        # 错误类型影响
        if episode.error_type:
            importance += 0.2
        
        return min(importance, 1.0)
    
    def _compute_context_hash(self, user_input: str, context: Dict) -> str:
        """计算上下文哈希"""
        content = f"{user_input}|{json.dumps(context, sort_keys=True)}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def store_episode(self, user_input: str, system_output: str,
                     user_feedback: str = None, satisfaction_score: float = 0.5,
                     error_type: str = None, session_id: str = "",
                     context: Dict = None) -> int:
        """
        存储情景记忆
        
        Args:
            user_input: 用户输入
            system_output: 系统输出
            user_feedback: 用户反馈
            satisfaction_score: 满意度分数
            error_type: 错误类型
            session_id: 会话ID
            context: 上下文信息
        
        Returns:
            记录ID
        """
        context = context or {}
        
        episode = Episode(
            timestamp=int(datetime.now().timestamp()),
            user_input=user_input,
            system_output=system_output,
            user_feedback=user_feedback,
            satisfaction_score=satisfaction_score,
            error_type=error_type,
            context_hash=self._compute_context_hash(user_input, context),
            importance=0.5,
            session_id=session_id,
            metadata=context
        )
        
        # 计算重要性
        episode.importance = self._compute_importance(episode)
        
        with self._write_lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO episodes 
                (timestamp, user_input, system_output, user_feedback, 
                 satisfaction_score, error_type, context_hash, importance, 
                 session_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                episode.timestamp, episode.user_input, episode.system_output,
                episode.user_feedback, episode.satisfaction_score, episode.error_type,
                episode.context_hash, episode.importance, episode.session_id,
                json.dumps(episode.metadata)
            ))
            
            episode_id = cursor.lastrowid
            conn.commit()
        
        logger.debug(f"Stored episode {episode_id}, importance={episode.importance:.2f}")
        return episode_id
    
    def get_episode(self, episode_id: int) -> Optional[Episode]:
        """获取单个情景"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,))
        row = cursor.fetchone()
        
        return Episode.from_row(row) if row else None
    
    def get_recent_episodes(self, limit: int = 100) -> List[Episode]:
        """获取最近的情景"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM episodes 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        
        return [Episode.from_row(row) for row in cursor.fetchall()]
    
    def get_important_episodes(self, threshold: float = None,
                               limit: int = 100) -> List[Episode]:
        """获取高重要性情景"""
        threshold = threshold or self.importance_threshold
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM episodes 
            WHERE importance >= ?
            ORDER BY importance DESC, timestamp DESC
            LIMIT ?
        """, (threshold, limit))
        
        return [Episode.from_row(row) for row in cursor.fetchall()]
    
    def get_episodes_by_timerange(self, start_time: int, 
                                   end_time: int) -> List[Episode]:
        """按时间范围获取情景"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM episodes 
            WHERE timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (start_time, end_time))
        
        return [Episode.from_row(row) for row in cursor.fetchall()]
    
    def get_low_satisfaction_episodes(self, threshold: float = 0.6,
                                      days: int = 7,
                                      limit: int = 100) -> List[Episode]:
        """获取低满意度情景（用于反思）"""
        cutoff_time = int(datetime.now().timestamp()) - (days * 86400)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM episodes 
            WHERE satisfaction_score < ? AND timestamp >= ?
            ORDER BY satisfaction_score ASC, timestamp DESC
            LIMIT ?
        """, (threshold, cutoff_time, limit))
        
        return [Episode.from_row(row) for row in cursor.fetchall()]
    
    def sample_for_replay(self, count: int = 1000,
                         importance_threshold: float = 0.5) -> List[Episode]:
        """采样用于睡眠重放"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 获取所有高重要性情景
        cursor.execute("""
            SELECT * FROM episodes 
            WHERE importance >= ?
            ORDER BY RANDOM()
            LIMIT ?
        """, (importance_threshold, count * 2))
        
        episodes = [Episode.from_row(row) for row in cursor.fetchall()]
        
        # 加权采样（重要性高的更可能被选中）
        if len(episodes) > count:
            weights = [ep.importance for ep in episodes]
            total = sum(weights)
            weights = [w / total for w in weights]
            
            sampled_indices = random.choices(
                range(len(episodes)),
                weights=weights,
                k=count
            )
            episodes = [episodes[i] for i in sampled_indices]
        
        return episodes
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM episodes")
        total_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT AVG(importance) FROM episodes")
        avg_importance = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT AVG(satisfaction_score) FROM episodes WHERE satisfaction_score IS NOT NULL")
        avg_satisfaction = cursor.fetchone()[0] or 0
        
        cursor.execute("""
            SELECT user_feedback, COUNT(*) 
            FROM episodes 
            WHERE user_feedback IS NOT NULL 
            GROUP BY user_feedback
        """)
        feedback_dist = {row[0]: row[1] for row in cursor.fetchall()}
        
        return {
            "total_episodes": total_count,
            "avg_importance": avg_importance,
            "avg_satisfaction": avg_satisfaction,
            "feedback_distribution": feedback_dist
        }
    
    def cleanup_old_episodes(self, days: int = 365,
                            keep_important: bool = True) -> int:
        """清理旧记录"""
        cutoff_time = int(datetime.now().timestamp()) - (days * 86400)
        deleted_count = 0
        
        with self._write_lock:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if keep_important:
                cursor.execute("""
                    DELETE FROM episodes 
                    WHERE timestamp < ? AND importance < ?
                """, (cutoff_time, self.importance_threshold))
            else:
                cursor.execute("DELETE FROM episodes WHERE timestamp < ?", (cutoff_time,))
            
            deleted_count = cursor.rowcount
            conn.commit()
        
        logger.info(f"Cleaned up {deleted_count} old episodes")
        return deleted_count


class SleepReplay:
    """睡眠重放机制"""
    
    def __init__(self, episodic_memory: EpisodicMemoryManager,
                 knowledge_engine=None, config: Dict = None):
        self.episodic_memory = episodic_memory
        self.knowledge_engine = knowledge_engine
        self.config = config or {}
        
        self.replay_count = self.config.get("replay_count", 1000)
        self.importance_threshold = self.config.get("importance_threshold", 0.5)
        self.replay_log_dir = None
        
        logger.info("SleepReplay initialized")
    
    def set_log_dir(self, log_dir: Path) -> None:
        """设置重放日志目录"""
        self.replay_log_dir = log_dir
        self.replay_log_dir.mkdir(parents=True, exist_ok=True)
    
    def run_replay(self, callback=None) -> Dict:
        """
        执行睡眠重放
        
        Args:
            callback: 处理每个情景的回调函数
        
        Returns:
            重放统计信息
        """
        logger.info("Starting sleep replay...")
        start_time = time.time()
        
        # 采样情景
        episodes = self.episodic_memory.sample_for_replay(
            count=self.replay_count,
            importance_threshold=self.importance_threshold
        )
        
        stats = {
            "total_episodes": len(episodes),
            "processed": 0,
            "knowledge_extracted": 0,
            "errors": 0,
            "start_time": datetime.now().isoformat(),
            "end_time": None
        }
        
        # 处理每个情景
        for episode in episodes:
            try:
                if callback:
                    result = callback(episode)
                    if result and result.get("knowledge"):
                        stats["knowledge_extracted"] += 1
                
                stats["processed"] += 1
                
            except Exception as e:
                logger.error(f"Error processing episode {episode.id}: {e}")
                stats["errors"] += 1
        
        stats["end_time"] = datetime.now().isoformat()
        stats["duration_seconds"] = time.time() - start_time
        
        # 保存日志
        if self.replay_log_dir:
            self._save_replay_log(stats, episodes)
        
        logger.info(f"Sleep replay completed: {stats['processed']} episodes processed")
        return stats
    
    def _save_replay_log(self, stats: Dict, episodes: List[Episode]) -> None:
        """保存重放日志"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.replay_log_dir / f"replay_{timestamp}.json"
        
        log_data = {
            "statistics": stats,
            "episodes_summary": [
                {
                    "id": ep.id,
                    "importance": ep.importance,
                    "satisfaction_score": ep.satisfaction_score
                }
                for ep in episodes[:100]  # 只保存前100个摘要
            ]
        }
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Replay log saved: {log_file}")


class MemorySystem:
    """三层记忆系统"""
    
    def __init__(self, config: Dict, project_root: Path = None):
        self.config = config
        self.project_root = project_root or Path.cwd()
        
        # 工作记忆
        working_path = self.project_root / config.get(
            "working_memory_path", "mutable/memory/working.json"
        )
        self.working = WorkingMemoryManager(working_path, config)
        
        # 情景记忆
        episodic_path = self.project_root / config.get(
            "episodic_db_path", "mutable/memory/episodic.db"
        )
        self.episodic = EpisodicMemoryManager(episodic_path, config)
        
        # 睡眠重放
        self.sleep_replay = SleepReplay(self.episodic, config=config)
        replay_log_dir = self.project_root / "mutable/memory/replay_logs"
        self.sleep_replay.set_log_dir(replay_log_dir)
        
        logger.info("MemorySystem initialized")
    
    def record_interaction(self, user_input: str, system_output: str,
                          feedback: str = None, satisfaction: float = 0.5,
                          error_type: str = None) -> int:
        """记录交互"""
        session_id = self.working.get_session_id()
        
        episode_id = self.episodic.store_episode(
            user_input=user_input,
            system_output=system_output,
            user_feedback=feedback,
            satisfaction_score=satisfaction,
            error_type=error_type,
            session_id=session_id
        )
        
        self.working.increment_turn()
        
        return episode_id
    
    def get_context_for_inference(self) -> Dict:
        """获取推理所需的上下文"""
        working_context = self.working.get_context()
        recent_episodes = self.episodic.get_recent_episodes(limit=5)
        
        return {
            "active_entities": working_context.entities,
            "goals": working_context.goals,
            "temporary_facts": working_context.temporary_facts,
            "recent_interactions": [ep.to_dict() for ep in recent_episodes]
        }
    
    def run_sleep_cycle(self, callback=None) -> Dict:
        """运行睡眠周期"""
        logger.info("Running sleep cycle...")
        
        # 执行重放
        replay_stats = self.sleep_replay.run_replay(callback)
        
        # 清理工作记忆
        self.working.clear_temporary()
        
        # 开始新会话
        self.working.start_new_session()
        
        return replay_stats
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        return {
            "working_memory": self.working.get_full_memory(),
            "episodic_stats": self.episodic.get_statistics()
        }


# 测试代码
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "working_memory_path": "memory/working.json",
            "episodic_db_path": "memory/episodic.db",
            "max_working_facts": 100,
            "episode_importance_threshold": 0.5
        }
        
        memory = MemorySystem(config, Path(tmpdir))
        
        # 测试工作记忆
        memory.working.add_entity("user")
        memory.working.add_goal("answer_question")
        memory.working.add_temporary_fact({"fact": "test", "confidence": 0.8})
        
        print(f"Working memory: {memory.working.get_full_memory()}")
        
        # 测试情景记忆
        episode_id = memory.record_interaction(
            "Hello", "Hi there!", "positive", 0.9
        )
        print(f"Stored episode: {episode_id}")
        
        # 测试检索
        episodes = memory.episodic.get_recent_episodes()
        print(f"Recent episodes: {len(episodes)}")
        
        # 统计
        stats = memory.get_statistics()
        print(f"Statistics: {json.dumps(stats, indent=2, default=str)}")
