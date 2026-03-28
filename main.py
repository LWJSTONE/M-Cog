#!/usr/bin/env python3
"""
M-Cog 自主进化大模型系统
主入口模块

M-Cog (Meta-Cognitive Autonomous Evolutionary System) 是一个低算力环境下
的自主进化大模型架构，具备自我制造工具、多途径学习与自我反思等核心能力。
"""

import os
import sys
import json
import logging
import argparse
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Any, List

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT / "core"))

# 配置日志
def setup_logging(config: Dict) -> logging.Logger:
    """配置日志系统"""
    log_config = config.get("logging", {})
    log_level = getattr(logging, log_config.get("level", "INFO"))
    log_format = log_config.get("format", "%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(),
        ]
    )
    
    return logging.getLogger("M-Cog")


class MCogSystem:
    """M-Cog 系统主类"""
    
    def __init__(self, config_path: str = None):
        self.config_path = config_path or str(PROJECT_ROOT / "config.json")
        self.config = self._load_config()
        
        # 初始化日志
        self.logger = setup_logging(self.config)
        self.logger.info("="*60)
        self.logger.info("M-Cog System Initializing")
        self.logger.info("="*60)
        
        # 系统状态
        self.running = False
        self._shutdown_event = threading.Event()
        
        # 核心模块（延迟加载）
        self._knowledge_engine = None
        self._expert_router = None
        self._memory_system = None
        self._meta_controller = None
        self._tool_factory = None
        self._dialectic_engine = None
        
        # 安全模块（C扩展）
        self._safety_module = None
        self._scheduler_module = None
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        config_file = Path(self.config_path)
        
        if not config_file.exists():
            # 创建默认配置
            default_config = self._get_default_config()
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            return default_config
        
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
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
                "input_dim": 768,
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
            },
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
            }
        }
    
    def _load_c_modules(self) -> bool:
        """加载 C 扩展模块"""
        try:
            import ctypes
            
            # 加载安全模块
            safety_path = PROJECT_ROOT / self.config["safety"]["core_module_path"]
            if safety_path.exists():
                self._safety_module = ctypes.CDLL(str(safety_path))
                self._safety_module.check_safety.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
                self._safety_module.check_safety.restype = ctypes.c_int
                self.logger.info("Safety module loaded")
            else:
                self.logger.warning(f"Safety module not found: {safety_path}")
            
            # 加载调度器模块
            scheduler_path = PROJECT_ROOT / "core/resource_scheduler.so"
            if scheduler_path.exists():
                self._scheduler_module = ctypes.CDLL(str(scheduler_path))
                self.logger.info("Scheduler module loaded")
            else:
                self.logger.warning(f"Scheduler module not found: {scheduler_path}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load C modules: {e}")
            return False
    
    def _init_core_modules(self) -> bool:
        """初始化核心 Python 模块"""
        try:
            # 知识引擎
            from knowledge_engine import KnowledgeEngine
            db_path = PROJECT_ROOT / self.config["knowledge"]["graph_db_path"]
            if db_path.exists():
                self._knowledge_engine = KnowledgeEngine(str(db_path), self.config["knowledge"])
                self.logger.info("Knowledge engine initialized")
            
            # 专家路由
            from expert_router import ExpertRouter
            self._expert_router = ExpertRouter(self.config["models"], PROJECT_ROOT)
            self.logger.info("Expert router initialized")
            
            # 记忆系统
            from memory import MemorySystem
            self._memory_system = MemorySystem(self.config["memory"], PROJECT_ROOT)
            self.logger.info("Memory system initialized")
            
            # 元认知中枢
            from meta_controller import MetaController
            self._meta_controller = MetaController(self.config, PROJECT_ROOT)
            self.logger.info("Meta controller initialized")
            
            # 工具工厂
            from tool_factory import ToolFactory
            self._tool_factory = ToolFactory(self.config["tools"], PROJECT_ROOT)
            self.logger.info("Tool factory initialized")
            
            # 辩证引擎
            from dialectic import DialecticEngine
            self._dialectic_engine = DialecticEngine(self.config, PROJECT_ROOT)
            self.logger.info("Dialectic engine initialized")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize core modules: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def check_safety(self, action: str, target: str) -> bool:
        """安全检查"""
        if self._safety_module:
            action_bytes = action.encode('utf-8')
            target_bytes = target.encode('utf-8')
            return self._safety_module.check_safety(action_bytes, target_bytes) == 1
        
        # Python fallback
        forbidden_keywords = ["harm", "kill", "bomb", "attack", "欺骗", "伤害"]
        combined = f"{action} {target}".lower()
        return not any(kw in combined for kw in forbidden_keywords)
    
    def process_input(self, user_input: str, context: Dict = None) -> Dict:
        """处理用户输入"""
        context = context or {}
        start_time = datetime.now()
        
        # 安全检查
        if not self.check_safety("generate", user_input):
            return {
                "output": "抱歉，您的请求涉及不安全内容，无法处理。",
                "status": "blocked",
                "reason": "safety_violation"
            }
        
        # 记录到工作记忆
        if self._memory_system:
            self._memory_system.working.increment_turn("process_input")
        
        # 查询知识库
        knowledge_results = []
        if self._knowledge_engine:
            entities = self._extract_entities(user_input)
            for entity in entities[:3]:
                results = self._knowledge_engine.query(entity, "is")
                knowledge_results.extend([r.to_dict() for r in results])
        
        # 专家路由推理
        expert_result = None
        if self._expert_router:
            import numpy as np
            input_embedding = np.random.randn(768)
            
            route_result = self._expert_router.route(input_embedding)
            if route_result.experts:
                inference_result = self._expert_router.infer(
                    input_embedding, route_result.experts
                )
                expert_result = inference_result.to_dict()
        
        # 辩证分析（如果涉及伦理问题）
        dialectic_result = None
        if self._should_dialectic_analysis(user_input) and self._dialectic_engine:
            dialectic_result = self._dialectic_engine.analyze(user_input)
            dialectic_result = dialectic_result.to_dict()
        
        # 构建响应
        response = self._build_response(
            user_input=user_input,
            knowledge_results=knowledge_results,
            expert_result=expert_result,
            dialectic_result=dialectic_result
        )
        
        # 记录情景记忆
        if self._memory_system:
            self._memory_system.record_interaction(
                user_input=user_input,
                system_output=response["output"],
                feedback=None,
                satisfaction=0.5
            )
        
        # 更新元认知监控
        if self._meta_controller:
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self._meta_controller.monitor.record_response_time(processing_time)
        
        return response
    
    def _extract_entities(self, text: str) -> List[str]:
        """简单实体提取"""
        words = text.split()
        entities = [w for w in words if len(w) > 2 and w.isalpha()]
        return entities[:5]
    
    def _should_dialectic_analysis(self, text: str) -> bool:
        """判断是否需要辩证分析"""
        ethics_keywords = ["应该", "对错", "道德", "伦理", "should", "right", "wrong", "ethical"]
        return any(kw in text.lower() for kw in ethics_keywords)
    
    def _build_response(self, user_input: str, knowledge_results: List,
                       expert_result: Dict, dialectic_result: Dict) -> Dict:
        """构建响应"""
        output_parts = []
        
        if knowledge_results:
            output_parts.append(f"根据知识库，找到 {len(knowledge_results)} 条相关信息。")
        
        if expert_result and expert_result.get("status") == "success":
            output_parts.append("专家分析完成。")
        
        if dialectic_result:
            output_parts.append(f"伦理分析: {dialectic_result.get('recommendation', '')}")
        
        if not output_parts:
            output_parts.append(f"已收到您的输入。M-Cog 正在学习中，将逐步提升响应质量。")
        
        return {
            "output": " ".join(output_parts),
            "status": "success",
            "knowledge_used": len(knowledge_results),
            "experts_involved": len(expert_result.get("expert_contributions", {})) if expert_result else 0,
            "dialectic_performed": dialectic_result is not None,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_system_status(self) -> Dict:
        """获取系统状态"""
        status = {
            "running": self.running,
            "config": self.config["system"],
            "modules": {
                "knowledge_engine": self._knowledge_engine is not None,
                "expert_router": self._expert_router is not None,
                "memory_system": self._memory_system is not None,
                "meta_controller": self._meta_controller is not None,
                "tool_factory": self._tool_factory is not None,
                "dialectic_engine": self._dialectic_engine is not None
            },
            "c_modules": {
                "safety": self._safety_module is not None,
                "scheduler": self._scheduler_module is not None
            }
        }
        
        if self._knowledge_engine:
            status["knowledge_stats"] = self._knowledge_engine.get_statistics()
        
        if self._memory_system:
            status["memory_stats"] = self._memory_system.get_statistics()
        
        if self._tool_factory:
            status["tool_stats"] = self._tool_factory.get_statistics()
        
        if self._meta_controller:
            status["meta_status"] = self._meta_controller.get_status()
        
        return status
    
    def start(self, enable_webui: bool = False) -> None:
        """启动系统"""
        self.logger.info("Starting M-Cog system...")
        
        # 加载 C 模块
        self._load_c_modules()
        
        # 初始化核心模块
        if not self._init_core_modules():
            self.logger.error("Failed to initialize core modules, running in limited mode")
        
        self.running = True
        
        # 启动元认知后台调度
        if self._meta_controller:
            self._meta_controller.start_background_scheduler(interval_seconds=60)
        
        self.logger.info("M-Cog system started successfully")
    
    def stop(self) -> None:
        """停止系统"""
        self.logger.info("Stopping M-Cog system...")
        
        self.running = False
        self._shutdown_event.set()
        
        if self._meta_controller:
            self._meta_controller.stop_background_scheduler()
        
        if self._knowledge_engine:
            self._knowledge_engine.close()
        
        self.logger.info("M-Cog system stopped")
    
    def run_interactive(self) -> None:
        """运行交互模式"""
        self.start()
        
        print("\n" + "="*60)
        print("M-Cog 交互模式")
        print("输入 'quit' 或 'exit' 退出")
        print("输入 'status' 查看系统状态")
        print("="*60 + "\n")
        
        try:
            while self.running:
                try:
                    user_input = input("M-Cog> ").strip()
                    
                    if not user_input:
                        continue
                    
                    if user_input.lower() in ['quit', 'exit']:
                        break
                    
                    if user_input.lower() == 'status':
                        status = self.get_system_status()
                        print(json.dumps(status, indent=2, default=str))
                        continue
                    
                    # 处理输入
                    result = self.process_input(user_input)
                    print(f"\n{result['output']}\n")
                    
                except KeyboardInterrupt:
                    print("\nUse 'quit' or 'exit' to stop.")
                except Exception as e:
                    self.logger.error(f"Error processing input: {e}")
                    print(f"Error: {e}")
        
        finally:
            self.stop()


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description='M-Cog: Meta-Cognitive Autonomous Evolutionary System'
    )
    parser.add_argument('--config', '-c', type=str, default=None,
                       help='Path to configuration file')
    parser.add_argument('--bootstrap', '-b', action='store_true',
                       help='Run bootstrap initialization')
    parser.add_argument('--seed-data', '-s', type=str, default=None,
                       help='Path to seed data JSON file for bootstrap')
    parser.add_argument('--status', action='store_true',
                       help='Show system status and exit')
    
    args = parser.parse_args()
    
    # 引导模式
    if args.bootstrap:
        from bootstrapper import Bootstrapper
        bootstrapper = Bootstrapper(PROJECT_ROOT)
        success = bootstrapper.bootstrap(args.seed_data)
        sys.exit(0 if success else 1)
    
    # 创建系统实例
    system = MCogSystem(args.config)
    
    # 状态查询
    if args.status:
        system.start()
        status = system.get_system_status()
        print(json.dumps(status, indent=2, default=str))
        system.stop()
        sys.exit(0)
    
    # 交互模式
    system.run_interactive()


if __name__ == '__main__':
    main()
