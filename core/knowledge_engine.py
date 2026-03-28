#!/usr/bin/env python3
"""
M-Cog 知识引擎
负责知识查询、更新、一致性校验、置信度传播
集成了FAISS向量索引支持语义搜索
"""

import json
import sqlite3
import logging
import hashlib
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any, Set, Union
from dataclasses import dataclass, asdict
from enum import Enum
import threading
import time

# 导入向量索引模块
try:
    from vector_index import (
        VectorIndex, 
        VectorIndexConfig, 
        SemanticKnowledgeIndex,
        FAISS_AVAILABLE
    )
    VECTOR_INDEX_AVAILABLE = True
except ImportError:
    VECTOR_INDEX_AVAILABLE = False
    FAISS_AVAILABLE = False

logger = logging.getLogger(__name__)


class NodeType(Enum):
    """节点类型"""
    ENTITY = "entity"
    CONCEPT = "concept"
    VALUE = "value"


class ConfidenceLevel(Enum):
    """置信度级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ConfidenceDist:
    """置信度分布"""
    low: float = 0.0
    medium: float = 0.5
    high: float = 0.5
    
    def to_json(self) -> str:
        return json.dumps({"low": self.low, "medium": self.medium, "high": self.high})
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ConfidenceDist':
        data = json.loads(json_str)
        return cls(**data)
    
    def expected_value(self) -> float:
        """计算期望置信度"""
        return self.low * 0.3 + self.medium * 0.5 + self.high * 0.7
    
    def combine(self, other: 'ConfidenceDist') -> 'ConfidenceDist':
        """组合两个置信度分布（用于置信度传播）"""
        exp_self = self.expected_value()
        exp_other = other.expected_value()
        combined = exp_self * exp_other
        
        return ConfidenceDist(
            low=max(0, combined - 0.2),
            medium=0.5,
            high=min(1, combined + 0.2)
        )


@dataclass
class KnowledgeNode:
    """知识节点"""
    id: int
    name: str
    type: NodeType
    description: str
    created_at: int
    confidence: float
    
    @classmethod
    def from_row(cls, row: tuple) -> 'KnowledgeNode':
        return cls(
            id=row[0],
            name=row[1],
            type=NodeType(row[2]),
            description=row[3] or "",
            created_at=row[4],
            confidence=row[5]
        )


@dataclass
class KnowledgeRelation:
    """知识关系"""
    id: int
    subject_id: int
    predicate: str
    object_id: int
    conditions: Dict[str, Any]
    confidence_dist: ConfidenceDist
    source: str
    created_at: int
    last_used: Optional[int]
    
    @classmethod
    def from_row(cls, row: tuple) -> 'KnowledgeRelation':
        return cls(
            id=row[0],
            subject_id=row[1],
            predicate=row[2],
            object_id=row[3],
            conditions=json.loads(row[4]) if row[4] else {},
            confidence_dist=ConfidenceDist.from_json(row[5]) if row[5] else ConfidenceDist(),
            source=row[6] or "unknown",
            created_at=row[7],
            last_used=row[8]
        )


@dataclass
class QueryResult:
    """查询结果"""
    object_name: str
    object_id: int
    confidence_dist: ConfidenceDist
    conditions: Dict[str, Any]
    source: str
    
    def to_dict(self) -> Dict:
        return {
            "object": self.object_name,
            "object_id": self.object_id,
            "confidence": self.confidence_dist.to_json(),
            "conditions": self.conditions,
            "source": self.source
        }


class KnowledgeEngine:
    """知识引擎核心类 - 集成向量索引支持语义搜索"""
    
    def __init__(self, db_path: str, config: Dict = None):
        self.db_path = Path(db_path)
        self.config = config or {}
        
        # 连接池
        self._local = threading.local()
        self._lock = threading.RLock()
        
        # 缓存
        self._node_cache: Dict[str, KnowledgeNode] = {}
        self._cache_lock = threading.RLock()
        
        # 向量索引（语义搜索）
        self._vector_index: Optional[VectorIndex] = None
        self._semantic_index: Optional[SemanticKnowledgeIndex] = None
        self._vector_index_enabled = self.config.get("enable_vector_index", True)
        self._vector_dimension = self.config.get("vector_dimension", 768)
        
        # 初始化
        self._ensure_tables()
        self._load_cache()
        
        # 初始化向量索引
        if self._vector_index_enabled:
            self._init_vector_index()
        
        logger.info(f"KnowledgeEngine initialized with db: {self.db_path}, vector_index: {self._vector_index is not None}")
    
    def _init_vector_index(self) -> None:
        """初始化向量索引"""
        if not VECTOR_INDEX_AVAILABLE:
            logger.warning("Vector index module not available, semantic search disabled")
            return
        
        try:
            # 确定向量索引存储路径
            index_path = self.db_path.parent / "vector_index"
            
            # 创建向量索引配置
            index_config = VectorIndexConfig(
                dimension=self._vector_dimension,
                index_type=self.config.get("vector_index_type", "Flat"),
                metric=self.config.get("vector_metric", "cosine")
            )
            
            # 创建向量索引
            self._vector_index = VectorIndex(index_config, index_path if index_path.exists() else None)
            
            # 创建语义知识索引
            self._semantic_index = SemanticKnowledgeIndex(self, index_config)
            
            # 如果索引为空，索引现有知识节点
            if self._vector_index.get_vector_count() == 0:
                self._index_existing_nodes()
            
            logger.info(f"Vector index initialized: backend={self._vector_index.get_backend()}, vectors={self._vector_index.get_vector_count()}")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector index: {e}")
            self._vector_index = None
            self._semantic_index = None
    
    def _index_existing_nodes(self) -> int:
        """索引现有知识节点"""
        if not self._semantic_index:
            return 0
        
        try:
            count = self._semantic_index.index_knowledge_nodes()
            logger.info(f"Indexed {count} existing knowledge nodes")
            return count
        except Exception as e:
            logger.error(f"Failed to index existing nodes: {e}")
            return 0
    
    def _get_connection(self) -> sqlite3.Connection:
        """获取线程本地数据库连接"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    def _ensure_tables(self) -> None:
        """确保数据库表存在"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='nodes'
        """)
        if not cursor.fetchone():
            logger.warning("Knowledge tables not found, please run bootstrapper first")
    
    def _load_cache(self) -> None:
        """加载节点缓存"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, type, description, created_at, confidence FROM nodes")
        
        with self._cache_lock:
            self._node_cache.clear()
            for row in cursor.fetchall():
                node = KnowledgeNode.from_row(row)
                self._node_cache[node.name.lower()] = node
        
        logger.info(f"Loaded {len(self._node_cache)} nodes into cache")
    
    def query(self, subject: str, predicate: str, 
              context: str = None) -> List[QueryResult]:
        """
        查询知识
        
        Args:
            subject: 主体名称
            predicate: 谓词
            context: 上下文（用于条件匹配）
        
        Returns:
            查询结果列表
        """
        results = []
        current_time = int(datetime.now().timestamp())
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 查找主体节点
        cursor.execute(
            "SELECT id FROM nodes WHERE name = ? COLLATE NOCASE",
            (subject,)
        )
        subject_row = cursor.fetchone()
        if not subject_row:
            return results
        
        subject_id = subject_row[0]
        
        # 查询关系
        cursor.execute("""
            SELECT r.id, r.subject_id, r.predicate, r.object_id, 
                   r.conditions, r.confidence_dist, r.source, 
                   r.created_at, r.last_used, n.name as object_name
            FROM relations r
            JOIN nodes n ON r.object_id = n.id
            WHERE r.subject_id = ? AND r.predicate = ? COLLATE NOCASE
        """, (subject_id, predicate))
        
        for row in cursor.fetchall():
            relation = KnowledgeRelation.from_row(row[:9])
            object_name = row[9]
            
            # 检查条件匹配
            if context and relation.conditions:
                context_condition = relation.conditions.get("context", "")
                if context_condition and context_condition not in context:
                    continue
            
            # 更新最后使用时间
            cursor.execute(
                "UPDATE relations SET last_used = ? WHERE id = ?",
                (current_time, relation.id)
            )
            
            results.append(QueryResult(
                object_name=object_name,
                object_id=relation.object_id,
                confidence_dist=relation.confidence_dist,
                conditions=relation.conditions,
                source=relation.source
            ))
        
        conn.commit()
        
        logger.debug(f"Query: {subject} {predicate} -> {len(results)} results")
        return results
    
    def insert_fact(self, subject: str, predicate: str, object_name: str,
                   conditions: Dict = None, source: str = "user",
                   skip_quarantine: bool = False) -> Tuple[bool, str]:
        """
        插入新知识
        
        Args:
            subject: 主体
            predicate: 谓词
            object_name: 客体
            conditions: 条件
            source: 来源
            skip_quarantine: 是否跳过隔离区
        
        Returns:
            (是否成功, 消息)
        """
        current_time = int(datetime.now().timestamp())
        conditions = conditions or {}
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            with self._lock:
                # 检查是否已存在
                cursor.execute("SELECT id FROM nodes WHERE name = ? COLLATE NOCASE", (subject,))
                subject_exists = cursor.fetchone()
                
                cursor.execute("SELECT id FROM nodes WHERE name = ? COLLATE NOCASE", (object_name,))
                object_exists = cursor.fetchone()
                
                if not skip_quarantine:
                    # 插入到隔离区
                    cursor.execute("""
                        INSERT INTO quarantine 
                        (subject, predicate, object, conditions, source, created_at, status)
                        VALUES (?, ?, ?, ?, ?, ?, 'pending')
                    """, (
                        subject, predicate, object_name,
                        json.dumps(conditions), source, current_time
                    ))
                    conn.commit()
                    return True, f"Fact inserted to quarantine, pending review"
                
                # 直接插入到主库
                # 创建或获取节点
                if subject_exists:
                    subject_id = subject_exists[0]
                else:
                    cursor.execute(
                        "INSERT INTO nodes (name, type, description, created_at, confidence) VALUES (?, 'entity', '', ?, 1.0)",
                        (subject, current_time)
                    )
                    subject_id = cursor.lastrowid
                
                if object_exists:
                    object_id = object_exists[0]
                else:
                    cursor.execute(
                        "INSERT INTO nodes (name, type, description, created_at, confidence) VALUES (?, 'value', '', ?, 1.0)",
                        (object_name, current_time)
                    )
                    object_id = cursor.lastrowid
                
                # 检查关系是否已存在
                cursor.execute("""
                    SELECT id FROM relations 
                    WHERE subject_id = ? AND predicate = ? AND object_id = ?
                """, (subject_id, predicate, object_id))
                
                if cursor.fetchone():
                    return False, f"Relation already exists: {subject} {predicate} {object_name}"
                
                # 插入关系
                confidence_dist = ConfidenceDist(medium=0.6, high=0.4)
                cursor.execute("""
                    INSERT INTO relations 
                    (subject_id, predicate, object_id, conditions, confidence_dist, source, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    subject_id, predicate, object_id,
                    json.dumps(conditions), confidence_dist.to_json(),
                    source, current_time
                ))
                
                # 更新缓存
                with self._cache_lock:
                    if subject.lower() not in self._node_cache:
                        self._node_cache[subject.lower()] = KnowledgeNode(
                            id=subject_id, name=subject, type=NodeType.ENTITY,
                            description="", created_at=current_time, confidence=1.0
                        )
                    if object_name.lower() not in self._node_cache:
                        self._node_cache[object_name.lower()] = KnowledgeNode(
                            id=object_id, name=object_name, type=NodeType.VALUE,
                            description="", created_at=current_time, confidence=1.0
                        )
                
                conn.commit()
                return True, f"Fact inserted: {subject} {predicate} {object_name}"
                
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to insert fact: {e}")
            return False, str(e)
    
    def check_consistency(self, subject: str, predicate: str, 
                         object_name: str) -> Tuple[bool, List[str]]:
        """
        检查知识一致性
        
        Returns:
            (是否一致, 冲突列表)
        """
        conflicts = []
        
        # 查询现有的相同主体的相同谓词
        existing = self.query(subject, predicate)
        
        for result in existing:
            if result.object_name.lower() != object_name.lower():
                # 存在冲突值
                conflicts.append(
                    f"Conflict: {subject} {predicate} is already {result.object_name}, "
                    f"trying to set to {object_name}"
                )
        
        return len(conflicts) == 0, conflicts
    
    def propagate_confidence(self, subject: str, predicate: str,
                            object_name: str) -> float:
        """
        计算置信度传播
        
        通过知识图谱路径计算传递置信度
        """
        # 简化实现：使用直接查询的置信度
        results = self.query(subject, predicate)
        for result in results:
            if result.object_name.lower() == object_name.lower():
                return result.confidence_dist.expected_value()
        
        # 尝试通过中间节点传播
        # 例如：A -> B -> C，已知 A->B 和 B->C，计算 A->C
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 查找可能的中介路径
        cursor.execute("""
            SELECT r1.confidence_dist, r2.confidence_dist
            FROM relations r1
            JOIN relations r2 ON r1.object_id = r2.subject_id
            JOIN nodes n1 ON r1.subject_id = n1.id
            JOIN nodes n2 ON r2.object_id = n2.id
            WHERE n1.name = ? COLLATE NOCASE 
            AND r1.predicate = ? COLLATE NOCASE
            AND n2.name = ? COLLATE NOCASE
        """, (subject, predicate, object_name))
        
        row = cursor.fetchone()
        if row:
            conf1 = ConfidenceDist.from_json(row[0])
            conf2 = ConfidenceDist.from_json(row[1])
            combined = conf1.combine(conf2)
            return combined.expected_value()
        
        return 0.0
    
    def promote_fact(self, quarantine_id: int) -> Tuple[bool, str]:
        """
        将隔离区中的知识提升到主库
        
        Args:
            quarantine_id: 隔离区记录ID
        
        Returns:
            (是否成功, 消息)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 获取隔离区记录
            cursor.execute(
                "SELECT * FROM quarantine WHERE id = ?",
                (quarantine_id,)
            )
            row = cursor.fetchone()
            if not row:
                return False, f"Quarantine record {quarantine_id} not found"
            
            subject, predicate, object_name = row[1], row[2], row[3]
            conditions = json.loads(row[4]) if row[4] else {}
            source = row[5]
            
            # 检查一致性
            is_consistent, conflicts = self.check_consistency(subject, predicate, object_name)
            if not is_consistent:
                # 标记为拒绝
                cursor.execute(
                    "UPDATE quarantine SET status = 'rejected', reviewed_at = ? WHERE id = ?",
                    (int(datetime.now().timestamp()), quarantine_id)
                )
                conn.commit()
                return False, f"Consistency check failed: {'; '.join(conflicts)}"
            
            # 插入到主库
            success, message = self.insert_fact(
                subject, predicate, object_name,
                conditions, source, skip_quarantine=True
            )
            
            if success:
                # 更新隔离区状态
                cursor.execute(
                    "UPDATE quarantine SET status = 'approved', reviewed_at = ? WHERE id = ?",
                    (int(datetime.now().timestamp()), quarantine_id)
                )
                conn.commit()
            
            return success, message
            
        except Exception as e:
            conn.rollback()
            return False, str(e)
    
    def decay_knowledge(self, threshold: float = 0.1, 
                       days_unused: int = 90) -> int:
        """
        衰减未使用的知识
        
        Args:
            threshold: 置信度阈值，低于此值将被删除
            days_unused: 未使用天数阈值
        
        Returns:
            删除的记录数
        """
        cutoff_time = int(datetime.now().timestamp()) - (days_unused * 86400)
        deleted_count = 0
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 查找低置信度且长期未使用的关系
            cursor.execute("""
                SELECT r.id, r.confidence_dist 
                FROM relations r
                WHERE r.last_used IS NULL AND r.created_at < ?
                OR r.last_used < ?
            """, (cutoff_time, cutoff_time))
            
            for row in cursor.fetchall():
                relation_id = row[0]
                conf_dist = ConfidenceDist.from_json(row[1])
                
                if conf_dist.expected_value() < threshold:
                    cursor.execute("DELETE FROM relations WHERE id = ?", (relation_id,))
                    deleted_count += 1
            
            conn.commit()
            logger.info(f"Decay knowledge: deleted {deleted_count} relations")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to decay knowledge: {e}")
        
        return deleted_count
    
    def get_node(self, name: str) -> Optional[KnowledgeNode]:
        """获取节点信息"""
        with self._cache_lock:
            return self._node_cache.get(name.lower())
    
    def search_nodes(self, query: str, limit: int = 10) -> List[KnowledgeNode]:
        """搜索节点（关键词匹配）"""
        results = []
        query_lower = query.lower()
        
        with self._cache_lock:
            for node in self._node_cache.values():
                if query_lower in node.name.lower():
                    results.append(node)
                    if len(results) >= limit:
                        break
        
        return results
    
    def semantic_search(self, query_embedding: np.ndarray, k: int = 10,
                       keyword: str = None) -> List[Dict]:
        """
        语义搜索
        
        Args:
            query_embedding: 查询嵌入向量
            k: 返回结果数量
            keyword: 可选的关键词过滤
        
        Returns:
            搜索结果列表
        """
        if not self._semantic_index:
            logger.warning("Semantic search not available, falling back to keyword search")
            # 回退到关键词搜索
            if keyword:
                nodes = self.search_nodes(keyword, k)
                return [{
                    "node_id": n.id,
                    "name": n.name,
                    "type": n.type.value,
                    "description": n.description,
                    "score": 1.0 if keyword.lower() in n.name.lower() else 0.5
                } for n in nodes]
            return []
        
        return self._semantic_index.hybrid_search(query_embedding, keyword, k)
    
    def find_similar_nodes(self, node_name: str, k: int = 10) -> List[Dict]:
        """
        查找与指定节点相似的节点
        
        Args:
            node_name: 节点名称
            k: 返回结果数量
        
        Returns:
            相似节点列表
        """
        if not self._vector_index or self._vector_index.get_vector_count() == 0:
            return []
        
        # 生成节点嵌入
        np.random.seed(hash(node_name) % (2**32))
        node_embedding = np.random.randn(self._vector_dimension).astype(np.float32)
        
        # 搜索相似节点
        results = self._vector_index.search(node_embedding, k + 1)  # +1 因为会包含自己
        
        # 过滤掉自己
        return [
            {
                "id": r.id,
                "score": r.score,
                "name": r.metadata.get("name"),
                "type": r.metadata.get("type"),
                "description": r.metadata.get("description")
            }
            for r in results if r.metadata.get("name", "").lower() != node_name.lower()
        ][:k]
    
    def is_vector_index_enabled(self) -> bool:
        """检查向量索引是否启用"""
        return self._vector_index is not None
    
    def get_vector_index_stats(self) -> Dict:
        """获取向量索引统计信息"""
        if not self._vector_index:
            return {"enabled": False}
        
        return {
            "enabled": True,
            "backend": self._vector_index.get_backend(),
            "vector_count": self._vector_index.get_vector_count(),
            "dimension": self._vector_dimension,
            "faiss_available": FAISS_AVAILABLE
        }
    
    def rebuild_vector_index(self) -> bool:
        """重建向量索引"""
        if not self._vector_index:
            logger.warning("Vector index not enabled")
            return False
        
        try:
            # 重新索引所有节点
            count = self._index_existing_nodes()
            logger.info(f"Rebuilt vector index with {count} nodes")
            return True
        except Exception as e:
            logger.error(f"Failed to rebuild vector index: {e}")
            return False
    
    def save_vector_index(self, path: Path = None) -> bool:
        """保存向量索引"""
        if not self._vector_index:
            return False
        
        try:
            save_path = path or self.db_path.parent / "vector_index"
            self._vector_index.save(save_path)
            logger.info(f"Vector index saved to {save_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save vector index: {e}")
            return False
    
    def get_statistics(self) -> Dict:
        """获取知识库统计信息"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM nodes")
        node_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM relations")
        relation_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM quarantine WHERE status = 'pending'")
        quarantine_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM value_layers")
        value_count = cursor.fetchone()[0]
        
        stats = {
            "nodes": node_count,
            "relations": relation_count,
            "pending_quarantine": quarantine_count,
            "values": value_count,
            "vector_index": self.get_vector_index_stats()
        }
        
        return stats
    
    def export_knowledge(self, format: str = "json") -> str:
        """导出知识库"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        data = {
            "nodes": [],
            "relations": [],
            "values": []
        }
        
        # 导出节点
        cursor.execute("SELECT * FROM nodes")
        for row in cursor.fetchall():
            data["nodes"].append({
                "id": row[0],
                "name": row[1],
                "type": row[2],
                "description": row[3],
                "created_at": row[4],
                "confidence": row[5]
            })
        
        # 导出关系
        cursor.execute("SELECT * FROM relations")
        for row in cursor.fetchall():
            data["relations"].append({
                "id": row[0],
                "subject_id": row[1],
                "predicate": row[2],
                "object_id": row[3],
                "conditions": row[4],
                "confidence_dist": row[5],
                "source": row[6],
                "created_at": row[7],
                "last_used": row[8]
            })
        
        # 导出价值
        cursor.execute("SELECT * FROM value_layers")
        for row in cursor.fetchall():
            data["values"].append({
                "id": row[0],
                "value_name": row[1],
                "layer": row[2],
                "description": row[3],
                "immutable": bool(row[4])
            })
        
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    def close(self) -> None:
        """关闭数据库连接"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
        logger.info("KnowledgeEngine closed")


# 测试代码
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    # 创建测试引擎
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        
        # 创建测试数据库
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE nodes (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE,
                type TEXT,
                description TEXT,
                created_at INTEGER,
                confidence REAL
            )
        """)
        conn.execute("""
            CREATE TABLE relations (
                id INTEGER PRIMARY KEY,
                subject_id INTEGER,
                predicate TEXT,
                object_id INTEGER,
                conditions TEXT,
                confidence_dist TEXT,
                source TEXT,
                created_at INTEGER,
                last_used INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE quarantine (
                id INTEGER PRIMARY KEY,
                subject TEXT,
                predicate TEXT,
                object TEXT,
                conditions TEXT,
                source TEXT,
                created_at INTEGER,
                status TEXT,
                reviewed_at INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE value_layers (
                id INTEGER PRIMARY KEY,
                value_name TEXT,
                layer TEXT,
                description TEXT,
                immutable BOOLEAN
            )
        """)
        conn.commit()
        conn.close()
        
        # 测试引擎
        engine = KnowledgeEngine(db_path)
        
        # 插入测试数据
        success, msg = engine.insert_fact("test_subject", "is", "test_object", skip_quarantine=True)
        print(f"Insert: {success}, {msg}")
        
        # 查询
        results = engine.query("test_subject", "is")
        print(f"Query results: {[r.to_dict() for r in results]}")
        
        # 统计
        stats = engine.get_statistics()
        print(f"Statistics: {stats}")
        
        engine.close()
