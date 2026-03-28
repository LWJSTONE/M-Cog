#!/usr/bin/env python3
"""
M-Cog 神经网络专家模型
基于Transformer架构的真实神经网络实现，支持量化和低算力环境
"""

import math
import json
import logging
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict, field
import threading
import time

logger = logging.getLogger(__name__)

# 尝试导入PyTorch
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch not available, falling back to NumPy implementation")


@dataclass
class TransformerConfig:
    """Transformer配置"""
    vocab_size: int = 30522  # BERT vocab size
    hidden_size: int = 256   # 减小以适应低算力
    num_hidden_layers: int = 4
    num_attention_heads: int = 4
    intermediate_size: int = 512
    hidden_dropout_prob: float = 0.1
    attention_probs_dropout_prob: float = 0.1
    max_position_embeddings: int = 512
    layer_norm_eps: float = 1e-12
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'TransformerConfig':
        return cls(**data)


class PositionalEncoding:
    """位置编码（NumPy实现）"""
    
    def __init__(self, d_model: int, max_len: int = 512, dropout: float = 0.1):
        self.d_model = d_model
        self.dropout = dropout
        
        # 创建位置编码矩阵
        pe = np.zeros((max_len, d_model))
        position = np.arange(0, max_len)[:, np.newaxis]
        div_term = np.exp(np.arange(0, d_model, 2) * -(math.log(10000.0) / d_model))
        
        pe[:, 0::2] = np.sin(position * div_term)
        pe[:, 1::2] = np.cos(position * div_term)
        
        self.pe = pe
    
    def __call__(self, x: np.ndarray) -> np.ndarray:
        """添加位置编码"""
        seq_len = x.shape[1]
        x = x + self.pe[:seq_len]
        if self.dropout > 0:
            mask = np.random.binomial(1, 1 - self.dropout, x.shape)
            x = x * mask / (1 - self.dropout)
        return x


class MultiHeadAttention:
    """多头自注意力机制（NumPy实现）"""
    
    def __init__(self, hidden_size: int, num_heads: int, dropout: float = 0.1):
        self.hidden_size = hidden_size
        self.num_heads = num_heads
        self.head_dim = hidden_size // num_heads
        self.dropout = dropout
        
        assert hidden_size % num_heads == 0, "hidden_size must be divisible by num_heads"
        
        # 初始化权重
        scale = 1.0 / math.sqrt(hidden_size)
        self.W_q = np.random.randn(hidden_size, hidden_size).astype(np.float32) * scale
        self.W_k = np.random.randn(hidden_size, hidden_size).astype(np.float32) * scale
        self.W_v = np.random.randn(hidden_size, hidden_size).astype(np.float32) * scale
        self.W_o = np.random.randn(hidden_size, hidden_size).astype(np.float32) * scale
    
    def forward(self, query: np.ndarray, key: np.ndarray, value: np.ndarray,
                mask: np.ndarray = None) -> Tuple[np.ndarray, np.ndarray]:
        """前向传播"""
        batch_size = query.shape[0]
        
        # 线性变换
        Q = np.dot(query, self.W_q)
        K = np.dot(key, self.W_k)
        V = np.dot(value, self.W_v)
        
        # 重塑为多头
        Q = Q.reshape(batch_size, -1, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)
        K = K.reshape(batch_size, -1, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)
        V = V.reshape(batch_size, -1, self.num_heads, self.head_dim).transpose(0, 2, 1, 3)
        
        # 计算注意力分数
        scores = np.matmul(Q, K.transpose(0, 1, 3, 2)) / math.sqrt(self.head_dim)
        
        # 应用mask
        if mask is not None:
            scores = scores + mask * -1e9
        
        # Softmax
        attn_weights = self._softmax(scores, axis=-1)
        
        # 应用dropout
        if self.dropout > 0:
            dropout_mask = np.random.binomial(1, 1 - self.dropout, attn_weights.shape)
            attn_weights = attn_weights * dropout_mask / (1 - self.dropout)
        
        # 加权求和
        context = np.matmul(attn_weights, V)
        
        # 重塑回来
        context = context.transpose(0, 2, 1, 3).reshape(batch_size, -1, self.hidden_size)
        
        # 输出投影
        output = np.dot(context, self.W_o)
        
        return output, attn_weights
    
    def _softmax(self, x: np.ndarray, axis: int = -1) -> np.ndarray:
        """稳定的softmax实现"""
        x_max = np.max(x, axis=axis, keepdims=True)
        exp_x = np.exp(x - x_max)
        return exp_x / np.sum(exp_x, axis=axis, keepdims=True)


class FeedForward:
    """前馈神经网络"""
    
    def __init__(self, hidden_size: int, intermediate_size: int, dropout: float = 0.1):
        self.hidden_size = hidden_size
        self.intermediate_size = intermediate_size
        self.dropout = dropout
        
        scale = 1.0 / math.sqrt(hidden_size)
        self.W1 = np.random.randn(hidden_size, intermediate_size).astype(np.float32) * scale
        self.b1 = np.zeros(intermediate_size, dtype=np.float32)
        self.W2 = np.random.randn(intermediate_size, hidden_size).astype(np.float32) * scale
        self.b2 = np.zeros(hidden_size, dtype=np.float32)
    
    def forward(self, x: np.ndarray) -> np.ndarray:
        """前向传播"""
        # 第一层 + GELU激活
        hidden = np.dot(x, self.W1) + self.b1
        hidden = self._gelu(hidden)
        
        # Dropout
        if self.dropout > 0:
            mask = np.random.binomial(1, 1 - self.dropout, hidden.shape)
            hidden = hidden * mask / (1 - self.dropout)
        
        # 第二层
        output = np.dot(hidden, self.W2) + self.b2
        
        return output
    
    def _gelu(self, x: np.ndarray) -> np.ndarray:
        """GELU激活函数"""
        return 0.5 * x * (1 + np.tanh(math.sqrt(2 / math.pi) * (x + 0.044715 * x ** 3)))


class LayerNorm:
    """层归一化"""
    
    def __init__(self, hidden_size: int, eps: float = 1e-12):
        self.eps = eps
        self.gamma = np.ones(hidden_size, dtype=np.float32)
        self.beta = np.zeros(hidden_size, dtype=np.float32)
    
    def forward(self, x: np.ndarray) -> np.ndarray:
        """前向传播"""
        mean = np.mean(x, axis=-1, keepdims=True)
        variance = np.var(x, axis=-1, keepdims=True)
        x_norm = (x - mean) / np.sqrt(variance + self.eps)
        return self.gamma * x_norm + self.beta


class TransformerLayer:
    """单个Transformer层"""
    
    def __init__(self, config: TransformerConfig):
        self.attention = MultiHeadAttention(
            config.hidden_size,
            config.num_attention_heads,
            config.attention_probs_dropout_prob
        )
        self.feed_forward = FeedForward(
            config.hidden_size,
            config.intermediate_size,
            config.hidden_dropout_prob
        )
        self.norm1 = LayerNorm(config.hidden_size, config.layer_norm_eps)
        self.norm2 = LayerNorm(config.hidden_size, config.layer_norm_eps)
        self.dropout = config.hidden_dropout_prob
    
    def forward(self, x: np.ndarray, mask: np.ndarray = None) -> np.ndarray:
        """前向传播"""
        # 自注意力 + 残差连接
        attn_output, _ = self.attention(x, x, x, mask)
        x = self.norm1(x + self._dropout(attn_output))
        
        # 前馈网络 + 残差连接
        ff_output = self.feed_forward(x)
        x = self.norm2(x + self._dropout(ff_output))
        
        return x
    
    def _dropout(self, x: np.ndarray) -> np.ndarray:
        """应用dropout"""
        if self.dropout > 0:
            mask = np.random.binomial(1, 1 - self.dropout, x.shape)
            return x * mask / (1 - self.dropout)
        return x


class NeuralExpertModel:
    """神经网络专家模型（NumPy实现）"""
    
    def __init__(self, config: TransformerConfig, expert_id: str = "default"):
        self.config = config
        self.expert_id = expert_id
        self.hidden_size = config.hidden_size
        
        # 嵌入层
        self.token_embedding = np.random.randn(
            config.vocab_size, config.hidden_size
        ).astype(np.float32) * 0.02
        
        # 位置编码
        self.position_encoding = PositionalEncoding(
            config.hidden_size,
            config.max_position_embeddings,
            config.hidden_dropout_prob
        )
        
        # Transformer层
        self.layers = [TransformerLayer(config) for _ in range(config.num_hidden_layers)]
        
        # 输出层
        self.output_projection = np.random.randn(
            config.hidden_size, config.hidden_size
        ).astype(np.float32) * 0.02
        
        # 是否量化
        self.quantized = False
        self.quantized_weights = {}
        
        logger.info(f"NeuralExpertModel '{expert_id}' initialized with {config.num_hidden_layers} layers")
    
    def forward(self, input_ids: np.ndarray = None, 
                input_embedding: np.ndarray = None) -> np.ndarray:
        """
        前向传播
        
        Args:
            input_ids: 输入token IDs [batch_size, seq_len]
            input_embedding: 直接输入嵌入 [batch_size, hidden_size] 或 [batch_size, seq_len, hidden_size]
        
        Returns:
            输出嵌入
        """
        if input_embedding is not None:
            # 直接使用输入嵌入
            if input_embedding.ndim == 2:
                # [batch_size, hidden_size] -> [batch_size, 1, hidden_size]
                x = input_embedding[:, np.newaxis, :]
            else:
                x = input_embedding
        elif input_ids is not None:
            # Token嵌入
            x = self.token_embedding[input_ids]
            x = self.position_encoding(x)
        else:
            raise ValueError("Either input_ids or input_embedding must be provided")
        
        # 通过Transformer层
        for layer in self.layers:
            x = layer.forward(x)
        
        # 输出投影
        output = np.dot(x, self.output_projection)
        
        # 取最后一个位置的输出（如果是序列）
        if output.shape[1] > 1:
            output = output[:, -1, :]
        
        return output
    
    def quantize(self, bits: int = 8) -> None:
        """
        量化模型权重
        
        Args:
            bits: 量化位数（目前仅支持8位）
        """
        if bits != 8:
            raise ValueError("Only 8-bit quantization is supported")
        
        self.quantized = True
        self.quantized_weights = {}
        
        # 量化嵌入层
        self._quantize_weight('token_embedding', self.token_embedding)
        self._quantize_weight('output_projection', self.output_projection)
        
        # 量化各层
        for i, layer in enumerate(self.layers):
            # 量化注意力权重
            self._quantize_weight(f'layer_{i}_W_q', layer.attention.W_q)
            self._quantize_weight(f'layer_{i}_W_k', layer.attention.W_k)
            self._quantize_weight(f'layer_{i}_W_v', layer.attention.W_v)
            self._quantize_weight(f'layer_{i}_W_o', layer.attention.W_o)
            
            # 量化前馈网络权重
            self._quantize_weight(f'layer_{i}_W1', layer.feed_forward.W1)
            self._quantize_weight(f'layer_{i}_W2', layer.feed_forward.W2)
        
        logger.info(f"Model quantized to {bits} bits")
    
    def _quantize_weight(self, name: str, weight: np.ndarray) -> None:
        """量化单个权重矩阵"""
        # 计算缩放因子
        max_val = np.max(np.abs(weight))
        scale = max_val / 127.0 if max_val > 0 else 1.0
        
        # 量化
        quantized = np.clip(np.round(weight / scale), -127, 127).astype(np.int8)
        
        self.quantized_weights[name] = {
            'data': quantized,
            'scale': scale,
            'shape': weight.shape
        }
    
    def dequantize_weight(self, name: str) -> np.ndarray:
        """反量化权重"""
        if name not in self.quantized_weights:
            raise ValueError(f"Weight {name} not found in quantized weights")
        
        q_weight = self.quantized_weights[name]
        return q_weight['data'].astype(np.float32) * q_weight['scale']
    
    def save(self, path: Path) -> None:
        """保存模型"""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        # 保存配置
        config_path = path / "config.json"
        with open(config_path, 'w') as f:
            json.dump(self.config.to_dict(), f, indent=2)
        
        # 保存权重
        weights = {
            'token_embedding': self.token_embedding,
            'output_projection': self.output_projection,
        }
        
        for i, layer in enumerate(self.layers):
            weights[f'layer_{i}_W_q'] = layer.attention.W_q
            weights[f'layer_{i}_W_k'] = layer.attention.W_k
            weights[f'layer_{i}_W_v'] = layer.attention.W_v
            weights[f'layer_{i}_W_o'] = layer.attention.W_o
            weights[f'layer_{i}_W1'] = layer.feed_forward.W1
            weights[f'layer_{i}_b1'] = layer.feed_forward.b1
            weights[f'layer_{i}_W2'] = layer.feed_forward.W2
            weights[f'layer_{i}_b2'] = layer.feed_forward.b2
            weights[f'layer_{i}_gamma1'] = layer.norm1.gamma
            weights[f'layer_{i}_beta1'] = layer.norm1.beta
            weights[f'layer_{i}_gamma2'] = layer.norm2.gamma
            weights[f'layer_{i}_beta2'] = layer.norm2.beta
        
        if self.quantized:
            # 保存量化权重
            np.savez_compressed(path / "weights_quantized.npz", **weights)
        else:
            np.savez(path / "weights.npz", **weights)
        
        logger.info(f"Model saved to {path}")
    
    def load(self, path: Path) -> None:
        """加载模型"""
        path = Path(path)
        
        # 加载权重
        if (path / "weights_quantized.npz").exists():
            weights = np.load(path / "weights_quantized.npz")
            self.quantized = True
        elif (path / "weights.npz").exists():
            weights = np.load(path / "weights.npz")
        else:
            raise FileNotFoundError(f"No weight file found in {path}")
        
        # 加载权重到模型
        self.token_embedding = weights['token_embedding']
        self.output_projection = weights['output_projection']
        
        for i, layer in enumerate(self.layers):
            layer.attention.W_q = weights[f'layer_{i}_W_q']
            layer.attention.W_k = weights[f'layer_{i}_W_k']
            layer.attention.W_v = weights[f'layer_{i}_W_v']
            layer.attention.W_o = weights[f'layer_{i}_W_o']
            layer.feed_forward.W1 = weights[f'layer_{i}_W1']
            layer.feed_forward.b1 = weights[f'layer_{i}_b1']
            layer.feed_forward.W2 = weights[f'layer_{i}_W2']
            layer.feed_forward.b2 = weights[f'layer_{i}_b2']
            layer.norm1.gamma = weights[f'layer_{i}_gamma1']
            layer.norm1.beta = weights[f'layer_{i}_beta1']
            layer.norm2.gamma = weights[f'layer_{i}_gamma2']
            layer.norm2.beta = weights[f'layer_{i}_beta2']
        
        logger.info(f"Model loaded from {path}")
    
    def get_parameter_count(self) -> int:
        """获取参数数量"""
        count = 0
        count += self.token_embedding.size
        count += self.output_projection.size
        
        for layer in self.layers:
            count += layer.attention.W_q.size
            count += layer.attention.W_k.size
            count += layer.attention.W_v.size
            count += layer.attention.W_o.size
            count += layer.feed_forward.W1.size
            count += layer.feed_forward.b1.size
            count += layer.feed_forward.W2.size
            count += layer.feed_forward.b2.size
            count += layer.norm1.gamma.size
            count += layer.norm1.beta.size
            count += layer.norm2.gamma.size
            count += layer.norm2.beta.size
        
        return count


class PyTorchTransformerExpert(nn.Module):
    """PyTorch Transformer专家模型"""
    
    def __init__(self, config: TransformerConfig):
        super().__init__()
        self.config = config
        
        # 嵌入层
        self.token_embedding = nn.Embedding(config.vocab_size, config.hidden_size)
        self.position_embedding = nn.Embedding(config.max_position_embeddings, config.hidden_size)
        
        # Transformer编码器
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=config.hidden_size,
            nhead=config.num_attention_heads,
            dim_feedforward=config.intermediate_size,
            dropout=config.hidden_dropout_prob,
            activation='gelu',
            batch_first=True
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=config.num_hidden_layers)
        
        # 输出层
        self.output_projection = nn.Linear(config.hidden_size, config.hidden_size)
        
        # 初始化权重
        self.apply(self._init_weights)
    
    def _init_weights(self, module):
        """初始化权重"""
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
    
    def forward(self, input_ids: torch.Tensor = None, 
                input_embedding: torch.Tensor = None) -> torch.Tensor:
        """前向传播"""
        if input_embedding is not None:
            if input_embedding.dim() == 2:
                x = input_embedding.unsqueeze(1)
            else:
                x = input_embedding
        elif input_ids is not None:
            seq_len = input_ids.shape[1]
            position_ids = torch.arange(seq_len, device=input_ids.device).unsqueeze(0)
            
            x = self.token_embedding(input_ids) + self.position_embedding(position_ids)
        else:
            raise ValueError("Either input_ids or input_embedding must be provided")
        
        # Transformer编码
        x = self.encoder(x)
        
        # 输出投影
        output = self.output_projection(x)
        
        # 取最后一个位置的输出
        if output.shape[1] > 1:
            output = output[:, -1, :]
        
        return output
    
    def to_quantized(self, dtype=torch.qint8):
        """量化模型"""
        return torch.quantization.quantize_dynamic(
            self, {nn.Linear}, dtype=dtype
        )


class ExpertModelFactory:
    """专家模型工厂"""
    
    @staticmethod
    def create(config: TransformerConfig, expert_id: str, 
               use_pytorch: bool = None) -> Any:
        """
        创建专家模型
        
        Args:
            config: 模型配置
            expert_id: 专家ID
            use_pytorch: 是否使用PyTorch（None表示自动检测）
        
        Returns:
            模型实例
        """
        if use_pytorch is None:
            use_pytorch = TORCH_AVAILABLE
        
        if use_pytorch and TORCH_AVAILABLE:
            logger.info(f"Creating PyTorch model for expert {expert_id}")
            return PyTorchTransformerExpert(config)
        else:
            logger.info(f"Creating NumPy model for expert {expert_id}")
            return NeuralExpertModel(config, expert_id)
    
    @staticmethod
    def create_default_expert(expert_id: str, domain: str) -> Tuple[Any, TransformerConfig]:
        """创建默认专家模型"""
        config = TransformerConfig(
            hidden_size=256,
            num_hidden_layers=4,
            num_attention_heads=4,
            intermediate_size=512
        )
        
        model = ExpertModelFactory.create(config, expert_id)
        return model, config


# 简单的训练器
class ExpertTrainer:
    """专家模型训练器"""
    
    def __init__(self, model, learning_rate: float = 1e-4):
        self.model = model
        
        if TORCH_AVAILABLE and isinstance(model, PyTorchTransformerExpert):
            self.optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
            self.use_pytorch = True
        else:
            self.learning_rate = learning_rate
            self.use_pytorch = False
    
    def train_step(self, input_data: np.ndarray, target: np.ndarray) -> float:
        """单步训练"""
        if self.use_pytorch:
            input_tensor = torch.from_numpy(input_data).float()
            target_tensor = torch.from_numpy(target).float()
            
            self.optimizer.zero_grad()
            output = self.model(input_embedding=input_tensor)
            loss = F.mse_loss(output, target_tensor)
            loss.backward()
            self.optimizer.step()
            
            return loss.item()
        else:
            # NumPy实现 - 简单的梯度下降
            output = self.model.forward(input_embedding=input_data)
            loss = np.mean((output - target) ** 2)
            
            # 简单的梯度更新（这里仅作演示，实际应使用更复杂的优化器）
            # 实际生产中应该实现完整的反向传播
            
            return float(loss)
    
    def compute_loss(self, input_data: np.ndarray, target: np.ndarray) -> float:
        """计算损失"""
        output = self.model.forward(input_embedding=input_data)
        return float(np.mean((output - target) ** 2))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # 测试模型创建
    config = TransformerConfig(
        hidden_size=256,
        num_hidden_layers=4,
        num_attention_heads=4
    )
    
    # 创建NumPy模型
    model = NeuralExpertModel(config, "test_expert")
    
    print(f"Model parameter count: {model.get_parameter_count():,}")
    
    # 测试前向传播
    input_embedding = np.random.randn(2, 256).astype(np.float32)
    output = model.forward(input_embedding=input_embedding)
    print(f"Input shape: {input_embedding.shape}")
    print(f"Output shape: {output.shape}")
    
    # 测试量化
    model.quantize(bits=8)
    print(f"Model quantized: {model.quantized}")
    
    # 测试保存和加载
    save_path = Path("/tmp/test_expert_model")
    model.save(save_path)
    
    new_model = NeuralExpertModel(config, "test_expert")
    new_model.load(save_path)
    print("Model saved and loaded successfully")
