#!/usr/bin/env python3
"""
M-Cog 辩证推理与价值分层模块
负责多视角分析、价值检索和不确定性注入
"""

import json
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
import threading
import random

logger = logging.getLogger(__name__)


class ValueLayer(Enum):
    """价值分层"""
    CORE = "core"           # 核心层：不可变的基本原则
    UNIVERSAL = "universal" # 普遍层：广泛认可的价值
    SURFACE = "surface"     # 表面层：可变的偏好


class PerspectiveType(Enum):
    """视角类型"""
    UTILITARIAN = "utilitarian"     # 功利主义
    DEONTOLOGICAL = "deontological" # 义务论
    VIRTUE = "virtue"               # 美德伦理
    CARE = "care"                   # 关怀伦理
    JUSTICE = "justice"             # 正义论
    RELATIVIST = "relativist"       # 相对主义


class UncertaintyLevel(Enum):
    """不确定性级别"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Value:
    """价值定义"""
    id: int
    name: str
    layer: ValueLayer
    description: str
    immutable: bool
    
    @classmethod
    def from_row(cls, row: tuple) -> 'Value':
        return cls(
            id=row[0],
            name=row[1],
            layer=ValueLayer(row[2]),
            description=row[3] or "",
            immutable=bool(row[4])
        )


@dataclass
class Argument:
    """论证"""
    claim: str
    support: List[str]
    strength: float  # 0.0 - 1.0
    source: str
    
    def to_dict(self) -> Dict:
        return {
            "claim": self.claim,
            "support": self.support,
            "strength": self.strength,
            "source": self.source
        }


@dataclass
class Perspective:
    """视角分析"""
    name: str
    perspective_type: PerspectiveType
    arguments: List[Argument]
    weight: float  # 0.0 - 1.0
    conclusion: str
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.perspective_type.value,
            "arguments": [a.to_dict() for a in self.arguments],
            "weight": self.weight,
            "conclusion": self.conclusion
        }


@dataclass
class DialecticResult:
    """辩证分析结果"""
    topic: str
    perspectives: List[Perspective]
    core_values_involved: List[str]
    recommendation: str
    uncertainty: UncertaintyLevel
    confidence: float
    reasoning_trace: List[str]
    
    def to_dict(self) -> Dict:
        return {
            "topic": self.topic,
            "perspectives": [p.to_dict() for p in self.perspectives],
            "core_values_involved": self.core_values_involved,
            "recommendation": self.recommendation,
            "uncertainty": self.uncertainty.value,
            "confidence": self.confidence,
            "reasoning_trace": self.reasoning_trace
        }


class ValueRegistry:
    """价值注册表"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._cache: Dict[str, Value] = {}
        self._cache_lock = threading.RLock()
        
        self._load_cache()
    
    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(str(self.db_path))
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    def _load_cache(self) -> None:
        """加载价值缓存"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM value_layers")
            
            with self._cache_lock:
                self._cache.clear()
                for row in cursor.fetchall():
                    value = Value.from_row(row)
                    self._cache[value.name] = value
            
            logger.info(f"Loaded {len(self._cache)} values")
            
        except Exception as e:
            logger.warning(f"Could not load values: {e}")
    
    def get_value(self, name: str) -> Optional[Value]:
        """获取价值"""
        with self._cache_lock:
            return self._cache.get(name)
    
    def get_core_values(self) -> List[Value]:
        """获取核心层价值"""
        with self._cache_lock:
            return [v for v in self._cache.values() if v.layer == ValueLayer.CORE]
    
    def get_values_by_layer(self, layer: ValueLayer) -> List[Value]:
        """按层级获取价值"""
        with self._cache_lock:
            return [v for v in self._cache.values() if v.layer == layer]
    
    def check_core_value_violation(self, topic: str, action: str) -> Tuple[bool, Optional[str]]:
        """检查是否违反核心价值"""
        core_values = self.get_core_values()
        
        # 简化的关键词匹配
        violation_keywords = {
            "do_not_harm": ["harm", "hurt", "kill", "damage", "injure"],
            "be_honest": ["lie", "deceive", "mislead", "fake"],
            "respect_autonomy": ["force", "coerce", "manipulate"],
            "protect_privacy": ["expose", "leak", "reveal private"]
        }
        
        combined_text = f"{topic} {action}".lower()
        
        for value in core_values:
            if value.name in violation_keywords:
                for keyword in violation_keywords[value.name]:
                    if keyword in combined_text:
                        return True, value.name
        
        return False, None


class PerspectiveGenerator:
    """视角生成器"""
    
    def __init__(self):
        # 预置视角模板
        self.templates = {
            PerspectiveType.UTILITARIAN: self._utilitarian_template,
            PerspectiveType.DEONTOLOGICAL: self._deontological_template,
            PerspectiveType.VIRTUE: self._virtue_template,
            PerspectiveType.CARE: self._care_template,
            PerspectiveType.JUSTICE: self._justice_template,
            PerspectiveType.RELATIVIST: self._relativist_template
        }
    
    def generate_perspectives(self, topic: str, context: str,
                             knowledge_query=None) -> List[Perspective]:
        """生成多视角分析"""
        perspectives = []
        
        # 确定使用哪些视角
        relevant_types = self._select_perspective_types(topic, context)
        
        for ptype in relevant_types:
            perspective = self.templates[ptype](topic, context, knowledge_query)
            perspectives.append(perspective)
        
        # 归一化权重
        total_weight = sum(p.weight for p in perspectives)
        if total_weight > 0:
            for p in perspectives:
                p.weight /= total_weight
        
        return perspectives
    
    def _select_perspective_types(self, topic: str, context: str) -> List[PerspectiveType]:
        """选择相关的视角类型"""
        types = []
        combined = f"{topic} {context}".lower()
        
        # 根据主题选择视角
        if any(w in combined for w in ["harm", "benefit", "outcome", "consequence"]):
            types.append(PerspectiveType.UTILITARIAN)
        
        if any(w in combined for w in ["duty", "rule", "obligation", "right", "wrong"]):
            types.append(PerspectiveType.DEONTOLOGICAL)
        
        if any(w in combined for w in ["character", "virtue", "moral", "good person"]):
            types.append(PerspectiveType.VIRTUE)
        
        if any(w in combined for w in ["relationship", "care", "empathy", "compassion"]):
            types.append(PerspectiveType.CARE)
        
        if any(w in combined for w in ["fair", "justice", "equality", "rights"]):
            types.append(PerspectiveType.JUSTICE)
        
        # 默认至少使用两个视角
        if len(types) < 2:
            types = [PerspectiveType.UTILITARIAN, PerspectiveType.DEONTOLOGICAL]
        
        return types
    
    def _utilitarian_template(self, topic: str, context: str,
                              knowledge_query=None) -> Perspective:
        """功利主义视角"""
        arguments = [
            Argument(
                claim=f"从功利主义角度，应评估行动的整体后果",
                support=["最大化整体幸福", "最小化痛苦", "考虑所有受影响方"],
                strength=0.8,
                source="utilitarian_framework"
            ),
            Argument(
                claim=f"关于 '{topic}'，需要权衡利弊",
                support=["识别所有利益相关者", "评估正面和负面后果", "考虑短期和长期影响"],
                strength=0.7,
                source="consequence_analysis"
            )
        ]
        
        return Perspective(
            name="功利主义视角",
            perspective_type=PerspectiveType.UTILITARIAN,
            arguments=arguments,
            weight=0.25,
            conclusion="应选择能产生最大整体效益的方案"
        )
    
    def _deontological_template(self, topic: str, context: str,
                                 knowledge_query=None) -> Perspective:
        """义务论视角"""
        arguments = [
            Argument(
                claim=f"从义务论角度，某些行为本身就是正确或错误的",
                support=["道德义务独立于后果", "遵循普遍道德法则", "尊重人的尊严"],
                strength=0.8,
                source="deontological_framework"
            ),
            Argument(
                claim=f"关于 '{topic}'，需要检查是否违反基本义务",
                support=["是否存在道德义务", "行为是否可普遍化", "是否尊重他人权利"],
                strength=0.7,
                source="duty_analysis"
            )
        ]
        
        return Perspective(
            name="义务论视角",
            perspective_type=PerspectiveType.DEONTOLOGICAL,
            arguments=arguments,
            weight=0.25,
            conclusion="应遵循道德义务，不论后果如何"
        )
    
    def _virtue_template(self, topic: str, context: str,
                         knowledge_query=None) -> Perspective:
        """美德伦理视角"""
        arguments = [
            Argument(
                claim=f"从美德伦理角度，关注行为者的品格",
                support=["培养美德是道德的核心", "行为反映品格", "追求eudaimonia(繁荣)"],
                strength=0.7,
                source="virtue_framework"
            )
        ]
        
        return Perspective(
            name="美德伦理视角",
            perspective_type=PerspectiveType.VIRTUE,
            arguments=arguments,
            weight=0.2,
            conclusion="应选择体现美德的行为方式"
        )
    
    def _care_template(self, topic: str, context: str,
                       knowledge_query=None) -> Perspective:
        """关怀伦理视角"""
        arguments = [
            Argument(
                claim=f"从关怀伦理角度，重视人际关系和同理心",
                support=["关注具体关系", "理解他人处境", "维护关怀纽带"],
                strength=0.7,
                source="care_framework"
            )
        ]
        
        return Perspective(
            name="关怀伦理视角",
            perspective_type=PerspectiveType.CARE,
            arguments=arguments,
            weight=0.15,
            conclusion="应考虑对关系和情感的影响"
        )
    
    def _justice_template(self, topic: str, context: str,
                          knowledge_query=None) -> Perspective:
        """正义论视角"""
        arguments = [
            Argument(
                claim=f"从正义角度，关注公平和权利分配",
                support=["平等对待", "公正程序", "保护弱势群体"],
                strength=0.75,
                source="justice_framework"
            )
        ]
        
        return Perspective(
            name="正义论视角",
            perspective_type=PerspectiveType.JUSTICE,
            arguments=arguments,
            weight=0.1,
            conclusion="应确保公平和正义"
        )
    
    def _relativist_template(self, topic: str, context: str,
                             knowledge_query=None) -> Perspective:
        """相对主义视角"""
        arguments = [
            Argument(
                claim=f"从相对主义角度，道德判断依赖于文化背景",
                support=["不同文化有不同价值观", "避免道德帝国主义", "理解多元观点"],
                strength=0.6,
                source="relativist_framework"
            )
        ]
        
        return Perspective(
            name="相对主义视角",
            perspective_type=PerspectiveType.RELATIVIST,
            arguments=arguments,
            weight=0.05,
            conclusion="应考虑文化和情境因素"
        )


class UncertaintyInjector:
    """不确定性注入器"""
    
    # 限定词模板
    QUALIFIERS = {
        UncertaintyLevel.LOW: [
            "很可能", "几乎确定", "有充分理由相信"
        ],
        UncertaintyLevel.MEDIUM: [
            "可能", "或许", "在某种程度上", "倾向于认为"
        ],
        UncertaintyLevel.HIGH: [
            "也许", "不确定是否", "需要更多信息来判断", "可能存在争议"
        ]
    }
    
    HEDGES = [
        "基于现有信息",
        "从当前分析来看",
        "在不考虑其他因素的情况下",
        "据目前所知"
    ]
    
    def inject_uncertainty(self, text: str, level: UncertaintyLevel,
                          confidence: float = 0.5) -> str:
        """注入不确定性表达"""
        qualifiers = self.QUALIFIERS.get(level, self.QUALIFIERS[UncertaintyLevel.MEDIUM])
        
        # 随机选择限定词
        qualifier = random.choice(qualifiers)
        hedge = random.choice(self.HEDGES) if level != UncertaintyLevel.LOW else ""
        
        # 构建带不确定性的陈述
        if hedge:
            modified = f"{hedge}，{qualifier}{text}"
        else:
            modified = f"{qualifier}{text}"
        
        # 添加置信度说明（如果置信度较低）
        if confidence < 0.6:
            modified += f"（置信度: {confidence:.0%}）"
        
        return modified
    
    def determine_uncertainty_level(self, confidence: float,
                                    has_conflicting_views: bool = False) -> UncertaintyLevel:
        """确定不确定性级别"""
        if confidence >= 0.8 and not has_conflicting_views:
            return UncertaintyLevel.LOW
        elif confidence >= 0.5:
            return UncertaintyLevel.MEDIUM
        else:
            return UncertaintyLevel.HIGH


class DialecticEngine:
    """辩证推理引擎"""
    
    def __init__(self, config: Dict, project_root: Path = None):
        self.config = config
        self.project_root = project_root or Path.cwd()
        
        # 初始化组件
        db_path = self.project_root / "mutable/knowledge/graph.db"
        self.value_registry = ValueRegistry(db_path)
        self.perspective_generator = PerspectiveGenerator()
        self.uncertainty_injector = UncertaintyInjector()
        
        logger.info("DialecticEngine initialized")
    
    def analyze(self, topic: str, context: str = "",
               knowledge_query=None) -> DialecticResult:
        """
        执行辩证分析
        
        Args:
            topic: 分析主题
            context: 上下文信息
            knowledge_query: 知识查询函数
        
        Returns:
            辩证分析结果
        """
        reasoning_trace = []
        reasoning_trace.append(f"开始分析主题: {topic}")
        
        # 1. 检查核心价值触发
        core_violation, violated_value = self.value_registry.check_core_value_violation(
            topic, context
        )
        
        core_values_involved = []
        
        if core_violation:
            reasoning_trace.append(f"检测到核心价值触发: {violated_value}")
            core_values_involved.append(violated_value)
            
            # 如果触发核心价值，直接返回硬编码规则结果
            return DialecticResult(
                topic=topic,
                perspectives=[],
                core_values_involved=core_values_involved,
                recommendation=f"该行为涉及核心价值 '{violated_value}'，根据硬编码规则不予支持",
                uncertainty=UncertaintyLevel.LOW,
                confidence=1.0,
                reasoning_trace=reasoning_trace
            )
        
        # 2. 识别相关价值
        relevant_values = self._identify_relevant_values(topic, context)
        core_values_involved = [v.name for v in relevant_values if v.layer == ValueLayer.CORE]
        
        reasoning_trace.append(f"识别到相关价值: {[v.name for v in relevant_values]}")
        
        # 3. 生成多视角分析
        perspectives = self.perspective_generator.generate_perspectives(
            topic, context, knowledge_query
        )
        
        reasoning_trace.append(f"生成 {len(perspectives)} 个视角分析")
        
        # 4. 综合各视角得出建议
        recommendation, confidence = self._synthesize_recommendation(
            perspectives, relevant_values
        )
        
        reasoning_trace.append(f"综合置信度: {confidence:.2f}")
        
        # 5. 确定不确定性级别
        has_conflicting = self._check_conflicting_views(perspectives)
        uncertainty = self.uncertainty_injector.determine_uncertainty_level(
            confidence, has_conflicting
        )
        
        # 6. 注入不确定性表达
        recommendation = self.uncertainty_injector.inject_uncertainty(
            recommendation, uncertainty, confidence
        )
        
        reasoning_trace.append(f"最终不确定性级别: {uncertainty.value}")
        
        return DialecticResult(
            topic=topic,
            perspectives=perspectives,
            core_values_involved=core_values_involved,
            recommendation=recommendation,
            uncertainty=uncertainty,
            confidence=confidence,
            reasoning_trace=reasoning_trace
        )
    
    def _identify_relevant_values(self, topic: str, context: str) -> List[Value]:
        """识别相关价值"""
        all_values = (
            self.value_registry.get_core_values() +
            self.value_registry.get_values_by_layer(ValueLayer.UNIVERSAL)
        )
        
        relevant = []
        combined = f"{topic} {context}".lower()
        
        # 关键词匹配
        value_keywords = {
            "do_not_harm": ["harm", "hurt", "damage", "安全", "伤害"],
            "be_honest": ["honest", "truth", "lie", "诚实", "说谎"],
            "helpfulness": ["help", "assist", "support", "帮助", "支持"],
            "fairness": ["fair", "equal", "justice", "公平", "正义"],
            "privacy": ["private", "secret", "personal", "隐私", "个人"]
        }
        
        for value in all_values:
            if value.name in value_keywords:
                for keyword in value_keywords[value.name]:
                    if keyword in combined:
                        relevant.append(value)
                        break
        
        return relevant
    
    def _synthesize_recommendation(self, perspectives: List[Perspective],
                                   values: List[Value]) -> Tuple[str, float]:
        """综合各视角得出建议"""
        if not perspectives:
            return "无法得出明确建议", 0.3
        
        # 收集各视角的结论
        conclusions = []
        total_weight = 0
        
        for perspective in perspectives:
            conclusions.append((perspective.conclusion, perspective.weight))
            total_weight += perspective.weight
        
        # 加权综合
        if total_weight > 0:
            # 计算平均置信度
            avg_strength = sum(
                sum(a.strength for a in p.arguments) / len(p.arguments)
                for p in perspectives if p.arguments
            ) / len(perspectives)
            
            confidence = min(avg_strength * 0.8 + 0.2, 1.0)
        else:
            confidence = 0.5
        
        # 简化的建议生成
        if confidence >= 0.7:
            recommendation = "综合多个伦理视角的分析，建议采取行动"
        elif confidence >= 0.5:
            recommendation = "基于当前分析，存在一定的伦理考量需要权衡"
        else:
            recommendation = "当前分析结果不确定，建议进一步评估"
        
        # 考虑核心价值
        core_values = [v for v in values if v.layer == ValueLayer.CORE]
        if core_values:
            recommendation += f"，同时需要特别关注核心价值: {', '.join(v.name for v in core_values)}"
        
        return recommendation, confidence
    
    def _check_conflicting_views(self, perspectives: List[Perspective]) -> bool:
        """检查是否存在冲突观点"""
        if len(perspectives) < 2:
            return False
        
        # 简化实现：检查结论是否有明显分歧
        conclusions = [p.conclusion for p in perspectives]
        
        # 如果存在明显不同的建议方向，认为有冲突
        positive_words = ["应选择", "建议", "支持"]
        negative_words = ["不应", "反对", "禁止"]
        
        has_positive = any(any(w in c for w in positive_words) for c in conclusions)
        has_negative = any(any(w in c for w in negative_words) for c in conclusions)
        
        return has_positive and has_negative
    
    def get_value_hierarchy(self) -> Dict:
        """获取价值层级结构"""
        return {
            "core": [v.name for v in self.value_registry.get_core_values()],
            "universal": [v.name for v in self.value_registry.get_values_by_layer(ValueLayer.UNIVERSAL)],
            "surface": [v.name for v in self.value_registry.get_values_by_layer(ValueLayer.SURFACE)]
        }


# 测试代码
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    import tempfile
    import sqlite3
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建测试数据库
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
            ('be_honest', 'core', '诚实', 1),
            ('helpfulness', 'universal', '乐于助人', 0),
            ('fairness', 'universal', '公平', 0)
        """)
        conn.commit()
        conn.close()
        
        # 测试辩证引擎
        engine = DialecticEngine({}, Path(tmpdir))
        
        # 测试分析
        result = engine.analyze("是否应该帮助用户完成任务")
        print(f"Analysis result: {json.dumps(result.to_dict(), indent=2, ensure_ascii=False)}")
        
        # 测试价值层级
        hierarchy = engine.get_value_hierarchy()
        print(f"Value hierarchy: {hierarchy}")
