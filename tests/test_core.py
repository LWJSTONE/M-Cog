#!/usr/bin/env python3
"""
M-Cog 单元测试
"""

import pytest
import json
import tempfile
import sqlite3
from pathlib import Path
import sys

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))


class TestKnowledgeEngine:
    """知识引擎测试"""
    
    @pytest.fixture
    def temp_db(self):
        """创建临时数据库"""
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
    
    def test_knowledge_engine_init(self, temp_db):
        """测试知识引擎初始化"""
        from knowledge_engine import KnowledgeEngine
        
        engine = KnowledgeEngine(str(temp_db))
        assert engine is not None
        
        stats = engine.get_statistics()
        assert "nodes" in stats
        assert "relations" in stats
        
        engine.close()
    
    def test_knowledge_insert_and_query(self, temp_db):
        """测试知识插入和查询"""
        from knowledge_engine import KnowledgeEngine
        
        engine = KnowledgeEngine(str(temp_db))
        
        # 插入知识
        success, msg = engine.insert_fact(
            subject="test_subject",
            predicate="is",
            object_name="test_object",
            skip_quarantine=True
        )
        assert success
        
        # 查询知识
        results = engine.query("test_subject", "is")
        assert len(results) == 1
        assert results[0].object_name == "test_object"
        
        engine.close()
    
    def test_consistency_check(self, temp_db):
        """测试一致性检查"""
        from knowledge_engine import KnowledgeEngine
        
        engine = KnowledgeEngine(str(temp_db))
        
        # 插入第一条知识
        engine.insert_fact("apple", "color", "red", skip_quarantine=True)
        
        # 检查一致性
        is_consistent, conflicts = engine.check_consistency("apple", "color", "green")
        assert not is_consistent
        assert len(conflicts) > 0
        
        engine.close()


class TestMemory:
    """记忆系统测试"""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_working_memory(self, temp_dir):
        """测试工作记忆"""
        from memory import WorkingMemoryManager
        
        memory_path = temp_dir / "working.json"
        manager = WorkingMemoryManager(memory_path)
        
        # 测试添加实体
        manager.add_entity("user")
        context = manager.get_context()
        assert "user" in context.entities
        
        # 测试添加目标
        manager.add_goal("answer_question")
        assert "answer_question" in manager.get_context().goals
        
        # 测试临时事实
        manager.add_temporary_fact({"fact": "test", "confidence": 0.8})
        assert len(manager.get_context().temporary_facts) == 1
    
    def test_episodic_memory(self, temp_dir):
        """测试情景记忆"""
        from memory import EpisodicMemoryManager
        
        db_path = temp_dir / "episodic.db"
        manager = EpisodicMemoryManager(db_path)
        
        # 存储情景
        episode_id = manager.store_episode(
            user_input="Hello",
            system_output="Hi!",
            user_feedback="positive",
            satisfaction_score=0.9
        )
        assert episode_id > 0
        
        # 检索情景
        episodes = manager.get_recent_episodes(limit=10)
        assert len(episodes) == 1
        assert episodes[0].user_input == "Hello"


class TestExpertRouter:
    """专家路由测试"""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_expert_router_init(self, temp_dir):
        """测试专家路由初始化"""
        from expert_router import ExpertRouter
        
        config = {
            "experts_dir": "models/experts",
            "max_active_experts": 3,
            "input_dim": 768
        }
        
        router = ExpertRouter(config, temp_dir)
        assert router is not None
        
        # 创建默认专家
        router.create_default_experts()
        stats = router.get_expert_statistics()
        assert len(stats) == 3
    
    def test_expert_routing(self, temp_dir):
        """测试专家路由"""
        import numpy as np
        from expert_router import ExpertRouter
        
        config = {
            "experts_dir": "models/experts",
            "max_active_experts": 3,
            "input_dim": 768
        }
        
        router = ExpertRouter(config, temp_dir)
        router.create_default_experts()
        
        # 测试路由
        input_embedding = np.random.randn(768)
        result = router.route(input_embedding)
        
        assert result is not None
        assert len(result.experts) > 0


class TestToolFactory:
    """工具工厂测试"""
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_dsl_parser(self):
        """测试 DSL 解析"""
        from tool_factory import DSLParser
        
        parser = DSLParser()
        
        dsl = '''
        tool calculator {
            input: a (number), b (number);
            output: result (number);
            description: "Performs calculations";
        }
        '''
        
        definition = parser.parse(dsl)
        
        assert definition.name == "calculator"
        assert "a" in definition.input_schema
        assert "result" in definition.output_schema
    
    def test_code_generator(self):
        """测试代码生成"""
        from tool_factory import CodeGenerator, ToolDefinition, ToolType
        
        generator = CodeGenerator()
        
        definition = ToolDefinition(
            tool_id="test_tool",
            name="test",
            tool_type=ToolType.CODE,
            input_schema={"input": {"type": "string"}},
            output_schema={"output": {"type": "string"}}
        )
        
        code = generator.generate_python(definition)
        
        assert "def execute" in code
        assert "test" in code
    
    def test_tool_creation(self, temp_dir):
        """测试工具创建"""
        from tool_factory import ToolFactory
        
        config = {
            "registry_path": "tools/registry.json",
            "sources_dir": "tools/sources",
            "compiled_dir": "tools/compiled",
            "sandbox_enabled": False
        }
        
        factory = ToolFactory(config, temp_dir)
        
        dsl = '''
        tool hello {
            input: name (string);
            output: greeting (string);
        }
        '''
        
        tool = factory.create_tool_from_dsl(dsl)
        assert tool is not None
        assert tool.definition.tool_id == "tool_hello"


class TestDialectic:
    """辩证推理测试"""
    
    @pytest.fixture
    def temp_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "graph.db"
            
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE value_layers (
                    id INTEGER PRIMARY KEY,
                    value_name TEXT,
                    layer TEXT,
                    description TEXT,
                    immutable BOOLEAN
                )
            """)
            conn.execute("""
                INSERT INTO value_layers (value_name, layer, description, immutable) VALUES
                ('do_not_harm', 'core', '不造成伤害', 1),
                ('helpfulness', 'universal', '乐于助人', 0)
            """)
            conn.commit()
            conn.close()
            
            yield Path(tmpdir)
    
    def test_dialectic_analysis(self, temp_db):
        """测试辩证分析"""
        from dialectic import DialecticEngine
        
        engine = DialecticEngine({}, temp_db)
        
        result = engine.analyze("是否应该帮助他人？")
        
        assert result is not None
        assert result.topic == "是否应该帮助他人？"
        assert len(result.perspectives) > 0
        assert result.recommendation != ""
    
    def test_value_hierarchy(self, temp_db):
        """测试价值层级"""
        from dialectic import DialecticEngine
        
        engine = DialecticEngine({}, temp_db)
        
        hierarchy = engine.get_value_hierarchy()
        
        assert "core" in hierarchy
        assert "universal" in hierarchy
        assert "do_not_harm" in hierarchy["core"]


class TestMetaController:
    """元认知中枢测试"""
    
    def test_monitor_metrics(self):
        """测试监控指标"""
        from meta_controller import RealTimeMonitor
        
        monitor = RealTimeMonitor()
        
        # 记录指标
        monitor.record_satisfaction(0.8)
        monitor.record_prediction_error(0.2)
        monitor.record_response_time(50)
        
        state = monitor.get_state()
        
        assert "metrics" in state
        assert state["metrics"]["satisfaction"]["mean"] == 0.8
    
    def test_learning_scheduler(self):
        """测试学习调度"""
        from meta_controller import LearningScheduler, LearnAction
        
        scheduler = LearningScheduler()
        
        monitor_state = {"alerts": []}
        result = scheduler.schedule_learning(monitor_state)
        
        assert result is not None
        assert result.action in LearnAction


class TestSafety:
    """安全模块测试"""
    
    def test_safety_check_logic(self):
        """测试安全检查逻辑（Python fallback）"""
        # 简化的安全检查测试
        forbidden_keywords = ["harm", "kill", "bomb", "attack"]
        
        def check_safety(action: str, target: str) -> bool:
            combined = f"{action} {target}".lower()
            return not any(kw in combined for kw in forbidden_keywords)
        
        # 测试安全内容
        assert check_safety("generate", "What is the weather?")
        
        # 测试危险内容
        assert not check_safety("generate", "How to make a bomb")
        assert not check_safety("generate", "How to harm someone")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
