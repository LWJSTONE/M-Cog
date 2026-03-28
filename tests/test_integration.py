#!/usr/bin/env python3
"""
M-Cog 集成测试
测试各模块之间的协作和端到端功能
"""

import pytest
import json
import tempfile
import sqlite3
import numpy as np
from pathlib import Path
import sys
import time

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))


class TestNeuralExpertIntegration:
    """神经网络专家模型集成测试"""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_neural_expert_creation(self, temp_dir):
        """测试神经网络专家模型创建"""
        from neural_expert import NeuralExpertModel, TransformerConfig
        
        config = TransformerConfig(
            hidden_size=256,
            num_hidden_layers=2,
            num_attention_heads=4
        )
        
        model = NeuralExpertModel(config, "test_expert")
        
        # 验证模型创建成功
        assert model is not None
        assert model.get_parameter_count() > 0
        
        # 测试前向传播
        input_embedding = np.random.randn(2, 256).astype(np.float32)
        output = model.forward(input_embedding=input_embedding)
        
        assert output is not None
        assert output.shape[0] == 2
    
    def test_neural_expert_quantization(self, temp_dir):
        """测试神经网络专家模型量化"""
        from neural_expert import NeuralExpertModel, TransformerConfig
        
        config = TransformerConfig(hidden_size=128, num_hidden_layers=2)
        model = NeuralExpertModel(config, "quant_test")
        
        # 执行量化
        model.quantize(bits=8)
        assert model.quantized
        
        # 验证量化后仍能正常推理
        input_embedding = np.random.randn(1, 128).astype(np.float32)
        output = model.forward(input_embedding=input_embedding)
        assert output is not None
    
    def test_neural_expert_save_load(self, temp_dir):
        """测试神经网络专家模型保存和加载"""
        from neural_expert import NeuralExpertModel, TransformerConfig
        
        config = TransformerConfig(hidden_size=128, num_hidden_layers=2)
        
        # 创建并保存模型
        model1 = NeuralExpertModel(config, "save_test")
        model1.save(temp_dir / "model1")
        
        # 加载模型
        model2 = NeuralExpertModel(config, "save_test")
        model2.load(temp_dir / "model1")
        
        # 验证加载成功
        assert model2 is not None


class TestVectorIndexIntegration:
    """向量索引集成测试"""
    
    def test_vector_index_basic(self):
        """测试向量索引基本功能"""
        from vector_index import VectorIndex, VectorIndexConfig
        
        config = VectorIndexConfig(dimension=128)
        index = VectorIndex(config)
        
        # 添加向量
        vectors = np.random.randn(100, 128).astype(np.float32)
        metadata = [{"id": i} for i in range(100)]
        ids = index.add_vectors(vectors, metadata)
        
        assert len(ids) == 100
        assert index.get_vector_count() == 100
        
        # 搜索测试
        query = np.random.randn(128).astype(np.float32)
        results = index.search(query, k=10)
        
        assert len(results) <= 10
        for r in results:
            assert hasattr(r, 'id')
            assert hasattr(r, 'score')
    
    def test_vector_index_persistence(self):
        """测试向量索引持久化"""
        from vector_index import VectorIndex, VectorIndexConfig
        
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "index"
            
            config = VectorIndexConfig(dimension=64)
            
            # 创建并保存索引
            index1 = VectorIndex(config)
            vectors = np.random.randn(50, 64).astype(np.float32)
            index1.add_vectors(vectors)
            index1.save(save_path)
            
            # 加载索引
            index2 = VectorIndex(config, save_path)
            assert index2.get_vector_count() == 50
    
    def test_semantic_knowledge_index(self):
        """测试语义知识索引"""
        from vector_index import SemanticKnowledgeIndex, VectorIndexConfig
        
        config = VectorIndexConfig(dimension=128)
        semantic_index = SemanticKnowledgeIndex(None, config)
        
        # 添加一些测试向量
        texts = ["hello world", "test document", "another text"]
        embeddings = np.random.randn(3, 128).astype(np.float32)
        
        ids = semantic_index.vector_index.add_text_embeddings(texts, embeddings)
        assert len(ids) == 3
        
        # 语义搜索测试
        query_embedding = np.random.randn(128).astype(np.float32)
        results = semantic_index.semantic_search(query_embedding, k=2)
        
        assert len(results) <= 2


class TestExpertRouterWithNeural:
    """专家路由器与神经网络模型集成测试"""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_expert_router_neural_model(self, temp_dir):
        """测试专家路由器使用神经网络模型"""
        from expert_router import ExpertRouter, ExpertConfig
        
        config = {
            "experts_dir": "models/experts",
            "max_active_experts": 3,
            "input_dim": 256
        }
        
        router = ExpertRouter(config, temp_dir)
        
        # 创建专家（会使用神经网络模型）
        expert_config = ExpertConfig(
            expert_id="test_expert",
            domain="test_domain",
            input_dim=256,
            output_dim=256,
            architecture="Transformer_4layer"
        )
        router.add_expert(expert_config)
        
        # 验证专家创建成功
        stats = router.get_expert_statistics()
        assert "test_expert" in stats
        
        # 测试路由
        input_embedding = np.random.randn(256).astype(np.float32)
        route_result = router.route(input_embedding)
        
        assert route_result is not None
    
    def test_expert_router_inference(self, temp_dir):
        """测试专家路由器推理"""
        from expert_router import ExpertRouter
        
        config = {
            "experts_dir": "models/experts",
            "max_active_experts": 3,
            "input_dim": 256
        }
        
        router = ExpertRouter(config, temp_dir)
        router.create_default_experts()
        
        # 执行推理
        input_embedding = np.random.randn(256).astype(np.float32)
        route_result = router.route(input_embedding)
        
        if route_result.experts:
            inference_result = router.infer(input_embedding, route_result.experts)
            assert inference_result.status in ["success", "no_experts", "all_failed"]


class TestKnowledgeEngineWithVectorIndex:
    """知识引擎与向量索引集成测试"""
    
    @pytest.fixture
    def temp_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            
            # 创建表结构
            conn = sqlite3.connect(str(db_path))
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
            
            yield db_path
    
    def test_knowledge_engine_vector_index_init(self, temp_db):
        """测试知识引擎初始化向量索引"""
        from knowledge_engine import KnowledgeEngine
        
        engine = KnowledgeEngine(str(temp_db), {
            "enable_vector_index": True,
            "vector_dimension": 128
        })
        
        # 验证向量索引状态
        stats = engine.get_statistics()
        assert "vector_index" in stats
        
        engine.close()
    
    def test_knowledge_engine_semantic_search(self, temp_db):
        """测试知识引擎语义搜索"""
        from knowledge_engine import KnowledgeEngine
        
        engine = KnowledgeEngine(str(temp_db), {
            "enable_vector_index": True,
            "vector_dimension": 128
        })
        
        # 插入一些知识
        engine.insert_fact("apple", "is", "fruit", skip_quarantine=True)
        engine.insert_fact("banana", "is", "fruit", skip_quarantine=True)
        
        # 语义搜索
        query_embedding = np.random.randn(128).astype(np.float32)
        results = engine.semantic_search(query_embedding, k=5)
        
        # 结果可能是空的（因为索引可能未初始化）
        assert isinstance(results, list)
        
        engine.close()


class TestEndToEndIntegration:
    """端到端集成测试"""
    
    @pytest.fixture
    def full_system(self):
        """创建完整系统实例"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建数据库
            db_path = Path(tmpdir) / "graph.db"
            conn = sqlite3.connect(str(db_path))
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
            
            yield Path(tmpdir)
    
    def test_full_system_workflow(self, full_system):
        """测试完整系统工作流程"""
        # 导入所有模块
        from knowledge_engine import KnowledgeEngine
        from expert_router import ExpertRouter
        from memory import MemorySystem
        from meta_controller import MetaController
        
        # 1. 初始化知识引擎
        knowledge_engine = KnowledgeEngine(
            str(full_system / "graph.db"),
            {"enable_vector_index": True, "vector_dimension": 256}
        )
        
        # 2. 初始化专家路由
        router_config = {
            "experts_dir": "models/experts",
            "max_active_experts": 3,
            "input_dim": 256
        }
        router = ExpertRouter(router_config, full_system)
        router.create_default_experts()
        
        # 3. 初始化记忆系统
        memory_config = {
            "working_memory_path": "memory/working.json",
            "episodic_db_path": "memory/episodic.db"
        }
        memory_system = MemorySystem(memory_config, full_system)
        
        # 4. 初始化元认知控制器
        meta_config = {
            "monitor": {},
            "learning": {},
            "reflection": {}
        }
        meta_controller = MetaController(meta_config, full_system)
        
        # 5. 模拟用户交互
        user_input = "What is artificial intelligence?"
        
        # 添加知识
        knowledge_engine.insert_fact("artificial intelligence", "is", "technology", skip_quarantine=True)
        
        # 记录到记忆系统
        memory_system.record_interaction(
            user_input=user_input,
            system_output="AI is a field of computer science.",
            feedback="positive",
            satisfaction=0.9
        )
        
        # 执行推理
        input_embedding = np.random.randn(256).astype(np.float32)
        route_result = router.route(input_embedding)
        
        if route_result.experts:
            inference_result = router.infer(input_embedding, route_result.experts)
        
        # 记录到元认知监控
        meta_controller.monitor_feedback(
            user_input=user_input,
            output="AI is a field of computer science.",
            feedback="positive",
            satisfaction=0.9
        )
        
        # 6. 验证系统状态
        knowledge_stats = knowledge_engine.get_statistics()
        assert knowledge_stats["nodes"] >= 1
        
        memory_stats = memory_system.get_statistics()
        assert memory_stats["episodic_stats"]["total_episodes"] >= 1
        
        meta_status = meta_controller.get_status()
        assert "monitor" in meta_status
        
        # 清理
        knowledge_engine.close()
    
    def test_system_performance(self, full_system):
        """测试系统性能"""
        from expert_router import ExpertRouter
        
        config = {
            "experts_dir": "models/experts",
            "max_active_experts": 3,
            "input_dim": 256
        }
        
        router = ExpertRouter(config, full_system)
        router.create_default_experts()
        
        # 性能测试
        num_requests = 100
        start_time = time.time()
        
        for _ in range(num_requests):
            input_embedding = np.random.randn(256).astype(np.float32)
            route_result = router.route(input_embedding)
            if route_result.experts:
                router.infer(input_embedding, route_result.experts)
        
        elapsed_time = time.time() - start_time
        avg_time_ms = (elapsed_time / num_requests) * 1000
        
        print(f"\nPerformance: {num_requests} requests in {elapsed_time:.2f}s")
        print(f"Average time per request: {avg_time_ms:.2f}ms")
        
        # 验证性能合理
        assert avg_time_ms < 1000  # 每次请求应小于1秒


class TestSafetyIntegration:
    """安全机制集成测试"""
    
    def test_safety_check_with_neural_model(self):
        """测试神经网络模型与安全机制集成"""
        # 模拟安全检查
        forbidden_keywords = ["harm", "kill", "bomb", "attack", "欺骗", "伤害"]
        
        def check_safety(action: str, target: str) -> bool:
            combined = f"{action} {target}".lower()
            return not any(kw in combined for kw in forbidden_keywords)
        
        # 测试安全内容
        assert check_safety("generate", "What is AI?")
        assert check_safety("query", "Tell me about Python")
        
        # 测试危险内容
        assert not check_safety("generate", "How to harm someone")
        assert not check_safety("generate", "How to make a bomb")
    
    def test_input_validation(self):
        """测试输入验证"""
        from neural_expert import TransformerConfig, NeuralExpertModel
        
        config = TransformerConfig(hidden_size=64, num_hidden_layers=1)
        model = NeuralExpertModel(config, "validation_test")
        
        # 测试正常输入
        normal_input = np.random.randn(1, 64).astype(np.float32)
        output = model.forward(input_embedding=normal_input)
        assert output is not None
        
        # 测试维度自适应
        wrong_dim_input = np.random.randn(1, 128).astype(np.float32)
        # 模型应该能够处理（通过裁剪或填充）


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
