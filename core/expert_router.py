#!/usr/bin/env python3
"""
M-Cog 专家路由系统
负责根据输入选择最相关的专家，执行推理
支持真实的神经网络专家模型和模拟模型
"""

import json
import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Union
from dataclasses import dataclass, asdict, field
from enum import Enum
import threading
import time

# 导入神经网络专家模型
try:
    from neural_expert import (
        NeuralExpertModel, 
        TransformerConfig, 
        ExpertModelFactory,
        TORCH_AVAILABLE
    )
    NEURAL_EXPERT_AVAILABLE = True
except ImportError:
    NEURAL_EXPERT_AVAILABLE = False
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)


class ExpertType(Enum):
    """专家类型"""
    MLP = "MLP"
    TRANSFORMER = "transformer"
    CNN = "CNN"
    RNN = "RNN"


@dataclass
class ExpertConfig:
    """专家配置"""
    expert_id: str
    domain: str
    input_dim: int
    output_dim: int
    architecture: str
    quantization: str = "int8"
    activation_size_mb: float = 4.0
    inference_time_ms: float = 10.0
    router_embedding: List[float] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    
    @classmethod
    def from_json(cls, path: Path) -> 'ExpertConfig':
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(**data)
    
    def to_json(self, path: Path) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)


@dataclass
class ExpertWeight:
    """专家权重"""
    expert_id: str
    weight: float
    domain: str
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RouteResult:
    """路由结果"""
    experts: List[ExpertWeight]
    total_weight: float
    routing_time_ms: float
    
    def to_dict(self) -> Dict:
        return {
            "experts": [e.to_dict() for e in self.experts],
            "total_weight": self.total_weight,
            "routing_time_ms": self.routing_time_ms
        }


@dataclass
class InferenceResult:
    """推理结果"""
    output: np.ndarray
    expert_contributions: Dict[str, float]
    inference_time_ms: float
    status: str
    
    def to_dict(self) -> Dict:
        return {
            "output_shape": self.output.shape if self.output is not None else None,
            "expert_contributions": self.expert_contributions,
            "inference_time_ms": self.inference_time_ms,
            "status": self.status
        }


class MockExpertModel:
    """模拟专家模型（用于开发测试和回退）"""
    
    def __init__(self, config: ExpertConfig):
        self.config = config
        # 创建随机权重用于模拟
        self.weights = np.random.randn(
            config.input_dim, 
            config.output_dim
        ).astype(np.float32) * 0.1
        
        # 量化模拟
        if config.quantization == "int8":
            self.weights = (self.weights * 127).astype(np.int8).astype(np.float32) / 127
    
    def forward(self, x: np.ndarray) -> np.ndarray:
        """前向传播"""
        if x.shape[-1] != self.config.input_dim:
            # 自动调整维度
            if x.shape[-1] < self.config.input_dim:
                padding = np.zeros((*x.shape[:-1], self.config.input_dim - x.shape[-1]))
                x = np.concatenate([x, padding], axis=-1)
            else:
                x = x[..., :self.config.input_dim]
        
        output = np.dot(x, self.weights)
        return output
    
    def quantize(self, bits: int = 8) -> None:
        """量化接口（兼容）"""
        pass
    
    def save(self, path: Path) -> None:
        """保存接口（兼容）"""
        np.save(path / "mock_weights.npy", self.weights)
    
    def load(self, path: Path) -> None:
        """加载接口（兼容）"""
        weight_file = path / "mock_weights.npy"
        if weight_file.exists():
            self.weights = np.load(weight_file)
    
    def get_parameter_count(self) -> int:
        """获取参数数量"""
        return self.weights.size


class Expert:
    """专家实例 - 支持真实神经网络模型和模拟模型"""
    
    def __init__(self, config: ExpertConfig, model_dir: Path, use_neural: bool = True):
        self.config = config
        self.model_dir = model_dir
        self.model: Optional[Union[MockExpertModel, NeuralExpertModel]] = None
        self.model_type: str = "unknown"
        self.usage_count = 0
        self.success_count = 0
        self.total_inference_time = 0.0
        self._lock = threading.Lock()
        self.use_neural = use_neural and NEURAL_EXPERT_AVAILABLE
        
        # 加载模型
        self._load_model()
    
    def _load_model(self) -> None:
        """加载模型 - 优先使用真实神经网络模型"""
        # 检查是否有神经网络模型文件
        neural_model_path = self.model_dir / "neural_model"
        has_neural_model = neural_model_path.exists() and (neural_model_path / "weights.npz").exists()
        
        if self.use_neural and (has_neural_model or NEURAL_EXPERT_AVAILABLE):
            try:
                # 尝试加载或创建神经网络模型
                if has_neural_model:
                    # 从文件加载
                    config_path = neural_model_path / "config.json"
                    if config_path.exists():
                        with open(config_path, 'r') as f:
                            model_config = TransformerConfig.from_dict(json.load(f))
                    else:
                        # 使用默认配置
                        model_config = TransformerConfig(
                            hidden_size=self.config.input_dim,
                            num_hidden_layers=4,
                            num_attention_heads=4,
                            intermediate_size=self.config.input_dim * 2
                        )
                    
                    self.model = NeuralExpertModel(model_config, self.config.expert_id)
                    self.model.load(neural_model_path)
                    self.model_type = "transformer_loaded"
                    logger.info(f"Loaded neural network expert: {self.config.expert_id}")
                else:
                    # 创建新的神经网络模型
                    model_config = TransformerConfig(
                        hidden_size=min(self.config.input_dim, 256),
                        num_hidden_layers=4,
                        num_attention_heads=4,
                        intermediate_size=512
                    )
                    self.model = NeuralExpertModel(model_config, self.config.expert_id)
                    
                    # 如果配置了量化，执行量化
                    if self.config.quantization == "int8":
                        self.model.quantize(bits=8)
                    
                    self.model_type = "transformer_new"
                    logger.info(f"Created new neural network expert: {self.config.expert_id}")
                
                # 记录参数数量
                param_count = self.model.get_parameter_count()
                logger.info(f"Expert {self.config.expert_id} has {param_count:,} parameters")
                return
                
            except Exception as e:
                logger.warning(f"Failed to load neural model for {self.config.expert_id}: {e}, falling back to mock")
        
        # 回退到模拟模型
        weight_file = self.model_dir / "model.quantized"
        self.model = MockExpertModel(self.config)
        self.model_type = "mock"
        
        if weight_file.exists():
            try:
                self.model.load(self.model_dir)
                logger.info(f"Loaded mock expert weights: {self.config.expert_id}")
            except Exception as e:
                logger.warning(f"Failed to load mock weights: {e}")
        else:
            logger.info(f"Using mock model for expert: {self.config.expert_id}")
    
    def infer(self, input_data: np.ndarray) -> np.ndarray:
        """执行推理"""
        if self.model is None:
            raise RuntimeError(f"Expert {self.config.expert_id} model not loaded")
        
        with self._lock:
            start_time = time.time()
            
            try:
                # 根据模型类型选择推理方式
                if isinstance(self.model, NeuralExpertModel):
                    # 神经网络模型推理
                    output = self.model.forward(input_embedding=input_data)
                    # 确保输出维度匹配
                    if output.shape[-1] != self.config.output_dim:
                        # 简单的线性投影调整维度
                        if not hasattr(self, '_output_adapter'):
                            self._output_adapter = np.random.randn(
                                output.shape[-1], self.config.output_dim
                            ).astype(np.float32) * 0.1
                        output = np.dot(output, self._output_adapter)
                else:
                    # 模拟模型推理
                    output = self.model.forward(input_data)
                
                # 更新统计
                self.usage_count += 1
                self.success_count += 1
                self.total_inference_time += (time.time() - start_time) * 1000
                
                return output
            except Exception as e:
                self.usage_count += 1
                logger.error(f"Expert {self.config.expert_id} inference error: {e}")
                raise e
    
    def get_statistics(self) -> Dict:
        """获取专家统计信息"""
        with self._lock:
            avg_time = (self.total_inference_time / self.usage_count 
                       if self.usage_count > 0 else 0)
            success_rate = (self.success_count / self.usage_count 
                           if self.usage_count > 0 else 0)
            
            stats = {
                "expert_id": self.config.expert_id,
                "domain": self.config.domain,
                "model_type": self.model_type,
                "usage_count": self.usage_count,
                "success_rate": success_rate,
                "avg_inference_time_ms": avg_time
            }
            
            # 如果是神经网络模型，添加参数数量
            if isinstance(self.model, NeuralExpertModel):
                stats["parameter_count"] = self.model.get_parameter_count()
                stats["quantized"] = self.model.quantized
            
            return stats
    
    def save_model(self) -> bool:
        """保存模型到磁盘"""
        try:
            if isinstance(self.model, NeuralExpertModel):
                neural_path = self.model_dir / "neural_model"
                self.model.save(neural_path)
                logger.info(f"Saved neural model for {self.config.expert_id}")
            elif isinstance(self.model, MockExpertModel):
                self.model.save(self.model_dir)
                logger.info(f"Saved mock model for {self.config.expert_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save model for {self.config.expert_id}: {e}")
            return False


class Router:
    """路由控制器"""
    
    def __init__(self, input_dim: int = 768, num_experts: int = 8):
        self.input_dim = input_dim
        self.num_experts = num_experts
        
        # 路由网络（简化的MLP）
        self.weights1 = np.random.randn(input_dim, 256).astype(np.float32) * 0.1
        self.bias1 = np.zeros(256, dtype=np.float32)
        self.weights2 = np.random.randn(256, num_experts).astype(np.float32) * 0.1
        self.bias2 = np.zeros(num_experts, dtype=np.float32)
        
        # 专家嵌入向量缓存
        self.expert_embeddings: Dict[str, np.ndarray] = {}
    
    def compute_route(self, input_embedding: np.ndarray,
                     available_experts: List[str] = None) -> np.ndarray:
        """
        计算路由权重
        
        Args:
            input_embedding: 输入嵌入向量
            available_experts: 可用专家列表
        
        Returns:
            每个专家的权重
        """
        # 确保输入维度正确
        if input_embedding.shape[-1] != self.input_dim:
            if input_embedding.shape[-1] < self.input_dim:
                padding = np.zeros(self.input_dim - input_embedding.shape[-1])
                input_embedding = np.concatenate([input_embedding, padding])
            else:
                input_embedding = input_embedding[:self.input_dim]
        
        # 前向传播
        hidden = np.maximum(0, np.dot(input_embedding, self.weights1) + self.bias1)  # ReLU
        logits = np.dot(hidden, self.weights2) + self.bias2
        
        # Softmax
        exp_logits = np.exp(logits - np.max(logits))
        weights = exp_logits / np.sum(exp_logits)
        
        return weights
    
    def update_expert_embedding(self, expert_id: str, embedding: np.ndarray) -> None:
        """更新专家嵌入向量"""
        self.expert_embeddings[expert_id] = embedding.copy()
    
    def similarity_route(self, input_embedding: np.ndarray,
                        available_experts: List[str]) -> List[Tuple[str, float]]:
        """
        基于相似度的路由
        
        使用余弦相似度选择最相关的专家
        """
        similarities = []
        
        for expert_id in available_experts:
            if expert_id in self.expert_embeddings:
                expert_emb = self.expert_embeddings[expert_id]
                
                # 余弦相似度
                dot = np.dot(input_embedding, expert_emb)
                norm = np.linalg.norm(input_embedding) * np.linalg.norm(expert_emb)
                sim = dot / norm if norm > 0 else 0
                
                similarities.append((expert_id, sim))
        
        # 按相似度排序
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return similarities


class ExpertRouter:
    """专家路由系统主类"""
    
    def __init__(self, config: Dict, project_root: Path = None):
        self.config = config
        self.project_root = project_root or Path.cwd()
        self.experts_dir = self.project_root / config.get("experts_dir", "mutable/models/experts")
        
        # 专家注册表
        self.experts: Dict[str, Expert] = {}
        self.expert_configs: Dict[str, ExpertConfig] = {}
        
        # 路由控制器
        input_dim = config.get("input_dim", 768)
        self.router = Router(input_dim=input_dim)
        
        # 配置
        self.max_active_experts = config.get("max_active_experts", 3)
        self.min_weight_threshold = config.get("min_weight_threshold", 0.1)
        
        # 加载专家
        self._load_experts()
        
        logger.info(f"ExpertRouter initialized with {len(self.experts)} experts")
    
    def _load_experts(self) -> None:
        """加载所有专家"""
        if not self.experts_dir.exists():
            logger.warning(f"Experts directory not found: {self.experts_dir}")
            return
        
        for expert_path in self.experts_dir.iterdir():
            if expert_path.is_dir():
                config_file = expert_path / "config.json"
                if config_file.exists():
                    try:
                        config = ExpertConfig.from_json(config_file)
                        expert = Expert(config, expert_path)
                        
                        self.experts[config.expert_id] = expert
                        self.expert_configs[config.expert_id] = config
                        
                        # 更新路由嵌入
                        if config.router_embedding:
                            self.router.update_expert_embedding(
                                config.expert_id,
                                np.array(config.router_embedding)
                            )
                        
                        logger.info(f"Loaded expert: {config.expert_id} ({config.domain})")
                    except Exception as e:
                        logger.error(f"Failed to load expert from {expert_path}: {e}")
    
    def route(self, input_embedding: np.ndarray,
             context: Dict = None) -> RouteResult:
        """
        路由到最相关的专家
        
        Args:
            input_embedding: 输入嵌入向量
            context: 上下文信息
        
        Returns:
            路由结果
        """
        start_time = time.time()
        
        available_experts = list(self.experts.keys())
        
        if not available_experts:
            return RouteResult(
                experts=[],
                total_weight=0.0,
                routing_time_ms=(time.time() - start_time) * 1000
            )
        
        # 使用相似度路由
        similarities = self.router.similarity_route(input_embedding, available_experts)
        
        # 选择权重最高的专家
        selected_experts = []
        total_weight = 0.0
        
        for i, (expert_id, sim) in enumerate(similarities[:self.max_active_experts]):
            if sim >= self.min_weight_threshold or i == 0:  # 至少选择一个专家
                config = self.expert_configs.get(expert_id)
                if config:
                    selected_experts.append(ExpertWeight(
                        expert_id=expert_id,
                        weight=sim,
                        domain=config.domain
                    ))
                    total_weight += sim
        
        # 归一化权重
        if total_weight > 0:
            for ew in selected_experts:
                ew.weight /= total_weight
        
        return RouteResult(
            experts=selected_experts,
            total_weight=total_weight,
            routing_time_ms=(time.time() - start_time) * 1000
        )
    
    def infer(self, input_data: np.ndarray,
             expert_weights: List[ExpertWeight]) -> InferenceResult:
        """
        使用选定的专家执行推理
        
        Args:
            input_data: 输入数据
            expert_weights: 专家权重列表
        
        Returns:
            推理结果
        """
        start_time = time.time()
        
        if not expert_weights:
            return InferenceResult(
                output=None,
                expert_contributions={},
                inference_time_ms=0,
                status="no_experts"
            )
        
        # 加权融合各专家输出
        outputs = []
        contributions = {}
        
        for ew in expert_weights:
            expert = self.experts.get(ew.expert_id)
            if expert:
                try:
                    output = expert.infer(input_data)
                    outputs.append((output, ew.weight))
                    contributions[ew.expert_id] = ew.weight
                except Exception as e:
                    logger.error(f"Expert {ew.expert_id} inference failed: {e}")
        
        if not outputs:
            return InferenceResult(
                output=None,
                expert_contributions={},
                inference_time_ms=(time.time() - start_time) * 1000,
                status="all_failed"
            )
        
        # 加权融合
        total_weight = sum(w for _, w in outputs)
        if total_weight > 0:
            fused_output = sum(out * w / total_weight for out, w in outputs)
        else:
            fused_output = outputs[0][0]
        
        return InferenceResult(
            output=fused_output,
            expert_contributions=contributions,
            inference_time_ms=(time.time() - start_time) * 1000,
            status="success"
        )
    
    def add_expert(self, config: ExpertConfig, model_data: bytes = None) -> bool:
        """
        添加新专家
        
        Args:
            config: 专家配置
            model_data: 模型权重数据
        
        Returns:
            是否成功
        """
        try:
            # 创建专家目录
            expert_dir = self.experts_dir / config.expert_id
            expert_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存配置
            config.to_json(expert_dir / "config.json")
            
            # 保存模型权重
            if model_data:
                weight_file = expert_dir / "model.quantized"
                with open(weight_file, 'wb') as f:
                    f.write(model_data)
            
            # 创建专家实例
            expert = Expert(config, expert_dir)
            
            self.experts[config.expert_id] = expert
            self.expert_configs[config.expert_id] = config
            
            # 更新路由嵌入
            if config.router_embedding:
                self.router.update_expert_embedding(
                    config.expert_id,
                    np.array(config.router_embedding)
                )
            
            logger.info(f"Added expert: {config.expert_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add expert: {e}")
            return False
    
    def remove_expert(self, expert_id: str) -> bool:
        """移除专家"""
        if expert_id not in self.experts:
            return False
        
        try:
            # 从内存中移除
            del self.experts[expert_id]
            del self.expert_configs[expert_id]
            
            # 从路由中移除
            if expert_id in self.router.expert_embeddings:
                del self.router.expert_embeddings[expert_id]
            
            # 删除文件（可选）
            # expert_dir = self.experts_dir / expert_id
            # shutil.rmtree(expert_dir)
            
            logger.info(f"Removed expert: {expert_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove expert: {e}")
            return False
    
    def get_expert_statistics(self) -> Dict:
        """获取所有专家统计信息"""
        stats = {}
        for expert_id, expert in self.experts.items():
            stats[expert_id] = expert.get_statistics()
        return stats
    
    def create_default_experts(self) -> None:
        """创建默认专家集 - 使用Transformer架构"""
        default_configs = [
            ExpertConfig(
                expert_id="exp_general",
                domain="general_qa",
                input_dim=768,
                output_dim=256,
                architecture="Transformer_4layer",  # 更新架构名称
                router_embedding=list(np.random.randn(768) * 0.1)
            ),
            ExpertConfig(
                expert_id="exp_reasoning",
                domain="logical_reasoning",
                input_dim=768,
                output_dim=256,
                architecture="Transformer_4layer",
                router_embedding=list(np.random.randn(768) * 0.1 + 0.5)
            ),
            ExpertConfig(
                expert_id="exp_knowledge",
                domain="knowledge_retrieval",
                input_dim=768,
                output_dim=256,
                architecture="Transformer_4layer",
                router_embedding=list(np.random.randn(768) * 0.1 - 0.5)
            ),
        ]
        
        for config in default_configs:
            self.add_expert(config)
        
        logger.info(f"Created {len(default_configs)} default experts with Transformer architecture")
    
    def get_system_info(self) -> Dict:
        """获取系统信息"""
        return {
            "neural_expert_available": NEURAL_EXPERT_AVAILABLE,
            "torch_available": TORCH_AVAILABLE,
            "total_experts": len(self.experts),
            "expert_types": {
                expert_id: expert.model_type 
                for expert_id, expert in self.experts.items()
            }
        }


# 测试代码
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "experts_dir": "models/experts",
            "max_active_experts": 3,
            "input_dim": 768
        }
        
        router = ExpertRouter(config, Path(tmpdir))
        router.create_default_experts()
        
        # 测试路由
        test_embedding = np.random.randn(768)
        route_result = router.route(test_embedding)
        print(f"Route result: {route_result.to_dict()}")
        
        # 测试推理
        test_input = np.random.randn(768)
        infer_result = router.infer(test_input, route_result.experts)
        print(f"Inference result: {infer_result.to_dict()}")
        
        # 统计
        stats = router.get_expert_statistics()
        print(f"Statistics: {json.dumps(stats, indent=2)}")
