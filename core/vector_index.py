#!/usr/bin/env python3
"""
M-Cog 向量索引模块
基于FAISS的高效向量检索系统，用于知识库语义搜索
"""

import json
import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, field
import threading
import time

logger = logging.getLogger(__name__)

# 尝试导入FAISS
try:
    import faiss
    FAISS_AVAILABLE = True
    logger.info("FAISS library loaded successfully")
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS not available, using NumPy fallback for vector search")


@dataclass
class VectorIndexConfig:
    """向量索引配置"""
    dimension: int = 768
    index_type: str = "IVFFlat"  # Flat, IVFFlat, IVFPQ, HNSW
    nlist: int = 100  # IVF聚类中心数量
    nprobe: int = 10  # 搜索时探测的聚类数量
    metric: str = "cosine"  # cosine, l2, ip (inner product)
    use_gpu: bool = False
    
    def to_dict(self) -> Dict:
        return {
            "dimension": self.dimension,
            "index_type": self.index_type,
            "nlist": self.nlist,
            "nprobe": self.nprobe,
            "metric": self.metric,
            "use_gpu": self.use_gpu
        }


@dataclass
class SearchResult:
    """搜索结果"""
    id: int
    score: float
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "score": self.score,
            "metadata": self.metadata
        }


class NumPyVectorIndex:
    """NumPy实现的向量索引（FAISS不可用时的回退方案）"""
    
    def __init__(self, config: VectorIndexConfig):
        self.config = config
        self.dimension = config.dimension
        self.vectors: np.ndarray = np.array([]).reshape(0, self.dimension)
        self.metadata: List[Dict] = []
        self._id_counter = 0
        self._lock = threading.Lock()
    
    def add_vectors(self, vectors: np.ndarray, metadata_list: List[Dict] = None) -> List[int]:
        """添加向量"""
        with self._lock:
            if vectors.ndim == 1:
                vectors = vectors.reshape(1, -1)
            
            n = vectors.shape[0]
            ids = list(range(self._id_counter, self._id_counter + n))
            self._id_counter += n
            
            # 归一化（如果使用余弦相似度）
            if self.config.metric == "cosine":
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                norms[norms == 0] = 1
                vectors = vectors / norms
            
            if len(self.vectors) == 0:
                self.vectors = vectors.astype(np.float32)
            else:
                self.vectors = np.vstack([self.vectors, vectors.astype(np.float32)])
            
            # 添加元数据
            if metadata_list:
                self.metadata.extend(metadata_list)
            else:
                self.metadata.extend([{} for _ in range(n)])
            
            return ids
    
    def search(self, query: np.ndarray, k: int = 10) -> Tuple[np.ndarray, np.ndarray]:
        """搜索最相似的向量"""
        if len(self.vectors) == 0:
            return np.array([]), np.array([])
        
        if query.ndim == 1:
            query = query.reshape(1, -1)
        
        # 归一化查询向量
        if self.config.metric == "cosine":
            norm = np.linalg.norm(query)
            if norm > 0:
                query = query / norm
        
        # 计算相似度
        if self.config.metric == "cosine":
            # 余弦相似度
            scores = np.dot(self.vectors, query.T).flatten()
        elif self.config.metric == "ip":
            # 内积
            scores = np.dot(self.vectors, query.T).flatten()
        else:
            # L2距离（转换为相似度）
            distances = np.linalg.norm(self.vectors - query, axis=1)
            scores = 1 / (1 + distances)
        
        # 获取top-k
        k = min(k, len(scores))
        top_indices = np.argsort(scores)[-k:][::-1]
        top_scores = scores[top_indices]
        
        return top_scores, top_indices
    
    def remove_vectors(self, ids: List[int]) -> bool:
        """删除向量"""
        with self._lock:
            mask = np.ones(len(self.vectors), dtype=bool)
            for id in ids:
                if 0 <= id < len(self.vectors):
                    mask[id] = False
            
            self.vectors = self.vectors[mask]
            self.metadata = [m for i, m in enumerate(self.metadata) if mask[i]]
            return True
    
    def get_vector_count(self) -> int:
        """获取向量数量"""
        return len(self.vectors)
    
    def save(self, path: Path) -> None:
        """保存索引"""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        np.save(path / "vectors.npy", self.vectors)
        with open(path / "metadata.json", 'w') as f:
            json.dump({
                "metadata": self.metadata,
                "id_counter": self._id_counter,
                "config": self.config.to_dict()
            }, f)
    
    def load(self, path: Path) -> None:
        """加载索引"""
        path = Path(path)
        
        vectors_path = path / "vectors.npy"
        if vectors_path.exists():
            self.vectors = np.load(vectors_path)
        
        metadata_path = path / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                data = json.load(f)
                self.metadata = data.get("metadata", [])
                self._id_counter = data.get("id_counter", 0)


class FAISSVectorIndex:
    """FAISS向量索引"""
    
    def __init__(self, config: VectorIndexConfig):
        self.config = config
        self.dimension = config.dimension
        self.index: Optional[faiss.Index] = None
        self.metadata: List[Dict] = []
        self._id_counter = 0
        self._lock = threading.Lock()
        self._trained = False
        
        # 创建索引
        self._create_index()
    
    def _create_index(self) -> None:
        """创建FAISS索引"""
        if not FAISS_AVAILABLE:
            raise RuntimeError("FAISS is not available")
        
        d = self.dimension
        metric = faiss.METRIC_INNER_PRODUCT if self.config.metric in ["cosine", "ip"] else faiss.METRIC_L2
        
        if self.config.index_type == "Flat":
            # 精确搜索索引
            self.index = faiss.IndexFlat(d, metric)
            self._trained = True
        
        elif self.config.index_type == "IVFFlat":
            # 倒排索引
            quantizer = faiss.IndexFlat(d, metric)
            self.index = faiss.IndexIVFFlat(quantizer, d, self.config.nlist, metric)
            self._trained = False
        
        elif self.config.index_type == "IVFPQ":
            # 乘积量化索引（更节省内存）
            quantizer = faiss.IndexFlat(d, metric)
            # PQ参数：8位编码，每子向量8维
            nbits = 8
            m = d // 8  # 子向量数量
            self.index = faiss.IndexIVFPQ(quantizer, d, self.config.nlist, m, nbits)
            self._trained = False
        
        elif self.config.index_type == "HNSW":
            # HNSW索引（需要faiss>1.7.0）
            M = 32  # 每个节点的邻居数
            self.index = faiss.IndexHNSWFlat(d, M, metric)
            self._trained = True
        
        else:
            # 默认使用Flat索引
            self.index = faiss.IndexFlat(d, metric)
            self._trained = True
        
        # GPU支持
        if self.config.use_gpu and hasattr(faiss, 'index_cpu_to_gpu'):
            try:
                res = faiss.StandardGpuResources()
                self.index = faiss.index_cpu_to_gpu(res, 0, self.index)
                logger.info("FAISS index moved to GPU")
            except Exception as e:
                logger.warning(f"Failed to move index to GPU: {e}")
        
        logger.info(f"FAISS index created: type={self.config.index_type}, dim={d}")
    
    def _ensure_trained(self, vectors: np.ndarray) -> None:
        """确保索引已训练"""
        if self._trained or self.config.index_type == "Flat":
            return
        
        n = vectors.shape[0]
        if n < self.config.nlist:
            logger.warning(f"Not enough vectors ({n}) for nlist ({self.config.nlist}), reducing nlist")
            # 动态调整nlist
            self.index.nlist = max(1, n // 10)
        
        # 训练索引
        train_size = min(n, 10000)
        train_data = vectors[:train_size].astype(np.float32)
        
        if self.config.metric == "cosine":
            # 归一化训练数据
            norms = np.linalg.norm(train_data, axis=1, keepdims=True)
            norms[norms == 0] = 1
            train_data = train_data / norms
        
        self.index.train(train_data)
        self._trained = True
        logger.info(f"FAISS index trained with {train_size} vectors")
    
    def add_vectors(self, vectors: np.ndarray, metadata_list: List[Dict] = None) -> List[int]:
        """添加向量"""
        with self._lock:
            if vectors.ndim == 1:
                vectors = vectors.reshape(1, -1)
            
            vectors = vectors.astype(np.float32)
            n = vectors.shape[0]
            
            # 归一化（余弦相似度）
            if self.config.metric == "cosine":
                norms = np.linalg.norm(vectors, axis=1, keepdims=True)
                norms[norms == 0] = 1
                vectors = vectors / norms
            
            # 确保索引已训练
            self._ensure_trained(vectors)
            
            # 生成ID
            ids = list(range(self._id_counter, self._id_counter + n))
            self._id_counter += n
            
            # 添加向量
            self.index.add(vectors)
            
            # 添加元数据
            if metadata_list:
                self.metadata.extend(metadata_list)
            else:
                self.metadata.extend([{} for _ in range(n)])
            
            logger.debug(f"Added {n} vectors to FAISS index")
            return ids
    
    def search(self, query: np.ndarray, k: int = 10) -> Tuple[np.ndarray, np.ndarray]:
        """搜索最相似的向量"""
        if self.index.ntotal == 0:
            return np.array([]), np.array([])
        
        if query.ndim == 1:
            query = query.reshape(1, -1)
        
        query = query.astype(np.float32)
        
        # 归一化查询向量
        if self.config.metric == "cosine":
            norms = np.linalg.norm(query, axis=1, keepdims=True)
            norms[norms == 0] = 1
            query = query / norms
        
        # 设置搜索参数
        if hasattr(self.index, 'nprobe'):
            self.index.nprobe = self.config.nprobe
        
        # 执行搜索
        k = min(k, self.index.ntotal)
        scores, indices = self.index.search(query, k)
        
        # 对于L2距离，转换为相似度
        if self.config.metric == "l2":
            scores = 1 / (1 + scores)
        
        return scores.flatten(), indices.flatten()
    
    def remove_vectors(self, ids: List[int]) -> bool:
        """删除向量（FAISS的删除操作较复杂，这里简化处理）"""
        # FAISS的索引删除操作有限制，这里我们标记删除
        # 实际实现中可能需要重建索引
        logger.warning("FAISS vector removal requires index rebuild")
        return False
    
    def get_vector_count(self) -> int:
        """获取向量数量"""
        return self.index.ntotal if self.index else 0
    
    def save(self, path: Path) -> None:
        """保存索引"""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        # 保存FAISS索引
        faiss.write_index(self.index, str(path / "faiss_index.bin"))
        
        # 保存元数据
        with open(path / "metadata.json", 'w') as f:
            json.dump({
                "metadata": self.metadata,
                "id_counter": self._id_counter,
                "config": self.config.to_dict()
            }, f)
        
        logger.info(f"FAISS index saved to {path}")
    
    def load(self, path: Path) -> None:
        """加载索引"""
        path = Path(path)
        
        # 加载FAISS索引
        index_path = path / "faiss_index.bin"
        if index_path.exists():
            self.index = faiss.read_index(str(index_path))
            self._trained = True
        
        # 加载元数据
        metadata_path = path / "metadata.json"
        if metadata_path.exists():
            with open(metadata_path, 'r') as f:
                data = json.load(f)
                self.metadata = data.get("metadata", [])
                self._id_counter = data.get("id_counter", 0)
        
        logger.info(f"FAISS index loaded from {path}")


class VectorIndex:
    """向量索引主类 - 自动选择FAISS或NumPy实现"""
    
    def __init__(self, config: VectorIndexConfig = None, index_path: Path = None):
        self.config = config or VectorIndexConfig()
        self.index: Union[FAISSVectorIndex, NumPyVectorIndex] = None
        self._lock = threading.Lock()
        
        # 创建索引
        if FAISS_AVAILABLE:
            self.index = FAISSVectorIndex(self.config)
            self._backend = "faiss"
        else:
            self.index = NumPyVectorIndex(self.config)
            self._backend = "numpy"
        
        # 加载已有索引
        if index_path:
            self.load(index_path)
        
        logger.info(f"VectorIndex initialized with {self._backend} backend")
    
    def add_vectors(self, vectors: np.ndarray, metadata_list: List[Dict] = None) -> List[int]:
        """添加向量"""
        return self.index.add_vectors(vectors, metadata_list)
    
    def add_text_embeddings(self, texts: List[str], embeddings: np.ndarray, 
                           extra_metadata: Dict = None) -> List[int]:
        """
        添加文本嵌入
        
        Args:
            texts: 文本列表
            embeddings: 嵌入向量
            extra_metadata: 额外的元数据
        
        Returns:
            向量ID列表
        """
        metadata_list = []
        for i, text in enumerate(texts):
            meta = {"text": text}
            if extra_metadata:
                meta.update(extra_metadata)
            metadata_list.append(meta)
        
        return self.add_vectors(embeddings, metadata_list)
    
    def search(self, query: np.ndarray, k: int = 10) -> List[SearchResult]:
        """搜索最相似的向量"""
        scores, indices = self.index.search(query, k)
        
        results = []
        for score, idx in zip(scores, indices):
            if idx < len(self.index.metadata):
                results.append(SearchResult(
                    id=int(idx),
                    score=float(score),
                    metadata=self.index.metadata[idx]
                ))
        
        return results
    
    def search_by_text(self, query_embedding: np.ndarray, k: int = 10,
                      filters: Dict = None) -> List[SearchResult]:
        """
        通过嵌入向量搜索文本
        
        Args:
            query_embedding: 查询嵌入
            k: 返回结果数量
            filters: 过滤条件
        
        Returns:
            搜索结果列表
        """
        results = self.search(query_embedding, k)
        
        # 应用过滤器
        if filters:
            filtered_results = []
            for result in results:
                match = True
                for key, value in filters.items():
                    if result.metadata.get(key) != value:
                        match = False
                        break
                if match:
                    filtered_results.append(result)
            return filtered_results
        
        return results
    
    def get_vector_count(self) -> int:
        """获取向量数量"""
        return self.index.get_vector_count()
    
    def get_backend(self) -> str:
        """获取后端类型"""
        return self._backend
    
    def is_faiss_available(self) -> bool:
        """检查FAISS是否可用"""
        return FAISS_AVAILABLE
    
    def save(self, path: Path) -> None:
        """保存索引"""
        self.index.save(path)
    
    def load(self, path: Path) -> None:
        """加载索引"""
        self.index.load(path)


class SemanticKnowledgeIndex:
    """语义知识索引 - 结合知识库和向量检索"""
    
    def __init__(self, knowledge_engine=None, config: VectorIndexConfig = None):
        self.knowledge_engine = knowledge_engine
        self.config = config or VectorIndexConfig()
        self.vector_index = VectorIndex(self.config)
        self._lock = threading.Lock()
    
    def index_knowledge_nodes(self) -> int:
        """索引知识库中的所有节点"""
        if not self.knowledge_engine:
            logger.warning("No knowledge engine attached")
            return 0
        
        # 获取所有节点
        nodes = list(self.knowledge_engine._node_cache.values())
        if not nodes:
            return 0
        
        # 生成嵌入（这里使用简单的随机嵌入，实际应使用预训练模型）
        embeddings = []
        metadata_list = []
        
        for node in nodes:
            # 使用节点名的哈希生成确定性嵌入
            np.random.seed(hash(node.name) % (2**32))
            emb = np.random.randn(self.config.dimension).astype(np.float32)
            embeddings.append(emb)
            metadata_list.append({
                "node_id": node.id,
                "name": node.name,
                "type": node.type.value,
                "description": node.description
            })
        
        embeddings = np.array(embeddings)
        ids = self.vector_index.add_vectors(embeddings, metadata_list)
        
        logger.info(f"Indexed {len(ids)} knowledge nodes")
        return len(ids)
    
    def semantic_search(self, query_embedding: np.ndarray, k: int = 10) -> List[Dict]:
        """语义搜索"""
        results = self.vector_index.search(query_embedding, k)
        
        return [
            {
                "id": r.id,
                "score": r.score,
                "node_id": r.metadata.get("node_id"),
                "name": r.metadata.get("name"),
                "type": r.metadata.get("type"),
                "description": r.metadata.get("description")
            }
            for r in results
        ]
    
    def hybrid_search(self, query_embedding: np.ndarray, keyword: str = None,
                     k: int = 10) -> List[Dict]:
        """混合搜索（语义+关键词）"""
        # 语义搜索
        semantic_results = self.semantic_search(query_embedding, k * 2)
        
        if keyword:
            # 过滤包含关键词的结果
            keyword_lower = keyword.lower()
            filtered = []
            for r in semantic_results:
                if (keyword_lower in r.get("name", "").lower() or
                    keyword_lower in r.get("description", "").lower()):
                    r["match_type"] = "both"
                    filtered.append(r)
                else:
                    r["match_type"] = "semantic"
                    filtered.append(r)
            return filtered[:k]
        
        return semantic_results[:k]


# 简单的嵌入模型接口
class SimpleEmbeddingModel:
    """简单的嵌入模型（用于测试）"""
    
    def __init__(self, dimension: int = 768):
        self.dimension = dimension
    
    def encode(self, texts: List[str]) -> np.ndarray:
        """编码文本为向量"""
        embeddings = []
        for text in texts:
            # 使用文本哈希生成确定性嵌入
            np.random.seed(hash(text) % (2**32))
            emb = np.random.randn(self.dimension).astype(np.float32)
            # 归一化
            emb = emb / np.linalg.norm(emb)
            embeddings.append(emb)
        return np.array(embeddings)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # 测试向量索引
    config = VectorIndexConfig(
        dimension=256,
        index_type="Flat",
        metric="cosine"
    )
    
    index = VectorIndex(config)
    
    # 添加一些测试向量
    test_vectors = np.random.randn(100, 256).astype(np.float32)
    test_metadata = [{"id": i, "text": f"Document {i}"} for i in range(100)]
    
    ids = index.add_vectors(test_vectors, test_metadata)
    print(f"Added {len(ids)} vectors")
    
    # 搜索测试
    query = np.random.randn(256).astype(np.float32)
    results = index.search(query, k=5)
    
    print(f"\nSearch results (backend: {index.get_backend()}):")
    for r in results:
        print(f"  ID: {r.id}, Score: {r.score:.4f}, Text: {r.metadata.get('text')}")
    
    # 保存和加载测试
    save_path = Path("/tmp/test_vector_index")
    index.save(save_path)
    
    new_index = VectorIndex(config, save_path)
    print(f"\nLoaded index with {new_index.get_vector_count()} vectors")
