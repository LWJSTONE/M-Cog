#!/usr/bin/env python3
"""
M-Cog 元认知中枢
负责实时监控、学习调度、反思触发和改进验证
"""

import json
import logging
import threading
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum
from collections import deque
import statistics

logger = logging.getLogger(__name__)


class ReflectionLevel(Enum):
    """反思级别"""
    MICRO = "micro"
    MACRO = "macro"
    DEEP = "deep"


class LearnAction(Enum):
    """学习动作类型"""
    USER_INTERACTION = "user_interaction"
    DOC_INGESTION = "doc_ingestion"
    SELF_PLAY = "self_play"
    SIMULATION = "simulation"
    REFLECTION = "reflection"


@dataclass
class MetricsWindow:
    """指标滑动窗口"""
    prediction_errors: deque = field(default_factory=lambda: deque(maxlen=1000))
    satisfaction_scores: deque = field(default_factory=lambda: deque(maxlen=1000))
    response_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    
    def add_prediction_error(self, error: float) -> None:
        self.prediction_errors.append(error)
    
    def add_satisfaction(self, score: float) -> None:
        self.satisfaction_scores.append(score)
    
    def add_response_time(self, time_ms: float) -> None:
        self.response_times.append(time_ms)
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        stats = {}
        
        if self.prediction_errors:
            stats["prediction_error"] = {
                "mean": statistics.mean(self.prediction_errors),
                "std": statistics.stdev(self.prediction_errors) if len(self.prediction_errors) > 1 else 0,
                "count": len(self.prediction_errors)
            }
        
        if self.satisfaction_scores:
            stats["satisfaction"] = {
                "mean": statistics.mean(self.satisfaction_scores),
                "std": statistics.stdev(self.satisfaction_scores) if len(self.satisfaction_scores) > 1 else 0,
                "count": len(self.satisfaction_scores)
            }
        
        if self.response_times:
            stats["response_time"] = {
                "mean": statistics.mean(self.response_times),
                "p99": sorted(self.response_times)[int(len(self.response_times) * 0.99)] if self.response_times else 0,
                "count": len(self.response_times)
            }
        
        return stats


@dataclass
class MonitorState:
    """监控状态"""
    prediction_error_trend: float = 0.0
    satisfaction_trend: float = 0.0
    knowledge_growth_rate: float = 0.0
    resource_efficiency: float = 1.0
    last_update: str = ""
    alerts: List[str] = field(default_factory=list)


@dataclass
class ScheduleResult:
    """调度结果"""
    action: LearnAction
    priority: int
    params: Dict
    estimated_duration_ms: int
    reason: str
    
    def to_dict(self) -> Dict:
        return {
            "action": self.action.value,
            "priority": self.priority,
            "params": self.params,
            "estimated_duration_ms": self.estimated_duration_ms,
            "reason": self.reason
        }


@dataclass
class ImprovementProposal:
    """改进提案"""
    proposal_id: str
    issue: str
    root_cause: str
    solution: str
    expected_improvement: float
    risk_level: str
    affected_modules: List[str]
    
    def to_dict(self) -> Dict:
        return asdict(self)


class RealTimeMonitor:
    """实时监控器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.metrics = MetricsWindow()
        self.state = MonitorState()
        self._lock = threading.RLock()
        
        # 历史数据点
        self._error_history: deque = deque(maxlen=10000)
        self._satisfaction_history: deque = deque(maxlen=10000)
        
        # 阈值
        self.error_increase_threshold = self.config.get("error_increase_threshold", 0.1)
        self.satisfaction_drop_threshold = self.config.get("satisfaction_drop_threshold", 0.2)
    
    def record_prediction_error(self, error: float) -> None:
        """记录预测误差"""
        with self._lock:
            self.metrics.add_prediction_error(error)
            self._error_history.append({
                "timestamp": datetime.now().isoformat(),
                "value": error
            })
    
    def record_satisfaction(self, score: float) -> None:
        """记录满意度"""
        with self._lock:
            self.metrics.add_satisfaction(score)
            self._satisfaction_history.append({
                "timestamp": datetime.now().isoformat(),
                "value": score
            })
    
    def record_response_time(self, time_ms: float) -> None:
        """记录响应时间"""
        with self._lock:
            self.metrics.add_response_time(time_ms)
    
    def compute_trends(self) -> Dict:
        """计算趋势"""
        with self._lock:
            # 计算预测误差趋势
            if len(self.metrics.prediction_errors) >= 10:
                recent = list(self.metrics.prediction_errors)[-10:]
                older = list(self.metrics.prediction_errors)[-20:-10] if len(self.metrics.prediction_errors) >= 20 else recent
                
                recent_mean = statistics.mean(recent)
                older_mean = statistics.mean(older)
                
                if older_mean > 0:
                    self.state.prediction_error_trend = (recent_mean - older_mean) / older_mean
                else:
                    self.state.prediction_error_trend = 0
            else:
                self.state.prediction_error_trend = 0
            
            # 计算满意度趋势
            if len(self.metrics.satisfaction_scores) >= 10:
                recent = list(self.metrics.satisfaction_scores)[-10:]
                older = list(self.metrics.satisfaction_scores)[-20:-10] if len(self.metrics.satisfaction_scores) >= 20 else recent
                
                recent_mean = statistics.mean(recent)
                older_mean = statistics.mean(older)
                
                if older_mean > 0:
                    self.state.satisfaction_trend = (older_mean - recent_mean) / older_mean  # 下降为正
                else:
                    self.state.satisfaction_trend = 0
            else:
                self.state.satisfaction_trend = 0
            
            self.state.last_update = datetime.now().isoformat()
            
            return {
                "prediction_error_trend": self.state.prediction_error_trend,
                "satisfaction_trend": self.state.satisfaction_trend,
                "alerts": self._check_alerts()
            }
    
    def _check_alerts(self) -> List[str]:
        """检查告警"""
        alerts = []
        
        if self.state.prediction_error_trend > self.error_increase_threshold:
            alerts.append(f"预测误差上升趋势: +{self.state.prediction_error_trend:.1%}")
        
        if self.state.satisfaction_trend > self.satisfaction_drop_threshold:
            alerts.append(f"满意度下降趋势: -{self.state.satisfaction_trend:.1%}")
        
        self.state.alerts = alerts
        return alerts
    
    def get_state(self) -> Dict:
        """获取当前状态"""
        with self._lock:
            return {
                "metrics": self.metrics.get_stats(),
                "trends": {
                    "prediction_error": self.state.prediction_error_trend,
                    "satisfaction": self.state.satisfaction_trend
                },
                "alerts": self.state.alerts,
                "last_update": self.state.last_update
            }


class LearningScheduler:
    """学习调度器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
        # 权重
        self.user_feedback_weight = self.config.get("user_feedback_weight", 0.8)
        self.self_play_weight = self.config.get("self_play_weight", 0.3)
        self.doc_ingestion_weight = self.config.get("doc_ingestion_weight", 0.5)
        
        # 调度历史
        self._schedule_history: deque = deque(maxlen=1000)
        self._last_schedule_time: Dict[LearnAction, datetime] = {}
        
        # 最小间隔（秒）
        self.min_intervals = {
            LearnAction.USER_INTERACTION: 0,  # 立即
            LearnAction.DOC_INGESTION: 300,   # 5分钟
            LearnAction.SELF_PLAY: 3600,      # 1小时
            LearnAction.SIMULATION: 1800,     # 30分钟
            LearnAction.REFLECTION: 3600      # 1小时
        }
    
    def schedule_learning(self, monitor_state: Dict) -> Optional[ScheduleResult]:
        """决定学习动作"""
        now = datetime.now()
        
        # 检查是否需要反思
        alerts = monitor_state.get("alerts", [])
        if alerts:
            if self._can_schedule(LearnAction.REFLECTION, now):
                return ScheduleResult(
                    action=LearnAction.REFLECTION,
                    priority=1,
                    params={"level": "micro", "triggers": alerts},
                    estimated_duration_ms=5000,
                    reason="Triggered by alerts: " + "; ".join(alerts)
                )
        
        # 根据优先级选择学习动作
        candidates = [
            (LearnAction.USER_INTERACTION, 0, self.user_feedback_weight),
            (LearnAction.DOC_INGESTION, 2, self.doc_ingestion_weight),
            (LearnAction.SELF_PLAY, 1, self.self_play_weight),
        ]
        
        # 过滤可调度的动作
        available = [
            (action, priority, weight)
            for action, priority, weight in candidates
            if self._can_schedule(action, now)
        ]
        
        if not available:
            return None
        
        # 选择权重最高的
        selected = max(available, key=lambda x: x[2])
        action = selected[0]
        
        # 记录调度时间
        self._last_schedule_time[action] = now
        
        return ScheduleResult(
            action=action,
            priority=selected[1],
            params={},
            estimated_duration_ms=self._estimate_duration(action),
            reason=f"Scheduled based on priority and availability"
        )
    
    def _can_schedule(self, action: LearnAction, now: datetime) -> bool:
        """检查是否可以调度"""
        if action not in self._last_schedule_time:
            return True
        
        last_time = self._last_schedule_time[action]
        min_interval = self.min_intervals.get(action, 0)
        
        return (now - last_time).total_seconds() >= min_interval
    
    def _estimate_duration(self, action: LearnAction) -> int:
        """估算持续时间"""
        durations = {
            LearnAction.USER_INTERACTION: 100,
            LearnAction.DOC_INGESTION: 5000,
            LearnAction.SELF_PLAY: 10000,
            LearnAction.SIMULATION: 3000,
            LearnAction.REFLECTION: 5000
        }
        return durations.get(action, 1000)


class ReflectionTrigger:
    """反思触发器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        
        # 触发阈值
        self.micro_threshold = self.config.get("micro_trigger_threshold", 0.3)
        self.macro_days = self.config.get("macro_trigger_days", 3)
        self.deep_days = self.config.get("deep_trigger_days", 7)
        self.min_episodes = self.config.get("min_episodes_for_analysis", 100)
        
        # 记录
        self._last_micro = None
        self._last_macro = None
        self._last_deep = None
    
    def check_triggers(self, monitor_state: Dict) -> List[Tuple[ReflectionLevel, str]]:
        """检查触发条件"""
        triggers = []
        now = datetime.now()
        
        # 微反思：预测误差超过阈值
        error_trend = monitor_state.get("trends", {}).get("prediction_error", 0)
        if error_trend > self.micro_threshold:
            if self._should_trigger(ReflectionLevel.MICRO, now):
                triggers.append((
                    ReflectionLevel.MICRO,
                    f"预测误差趋势超过阈值: {error_trend:.1%}"
                ))
                self._last_micro = now
        
        # 中反思：定期触发
        if self._should_trigger(ReflectionLevel.MACRO, now):
            triggers.append((
                ReflectionLevel.MACRO,
                f"定期宏观反思（每 {self.macro_days} 天）"
            ))
            self._last_macro = now
        
        # 深度反思：长期问题
        if self._should_trigger(ReflectionLevel.DEEP, now):
            triggers.append((
                ReflectionLevel.DEEP,
                f"定期深度反思（每 {self.deep_days} 天）"
            ))
            self._last_deep = now
        
        return triggers
    
    def _should_trigger(self, level: ReflectionLevel, now: datetime) -> bool:
        """检查是否应该触发"""
        days_map = {
            ReflectionLevel.MICRO: 0,  # 不限时
            ReflectionLevel.MACRO: self.macro_days,
            ReflectionLevel.DEEP: self.deep_days
        }
        
        last_map = {
            ReflectionLevel.MICRO: self._last_micro,
            ReflectionLevel.MACRO: self._last_macro,
            ReflectionLevel.DEEP: self._last_deep
        }
        
        last_time = last_map[level]
        required_days = days_map[level]
        
        if last_time is None:
            return True
        
        if required_days == 0:
            return True
        
        return (now - last_time).days >= required_days
    
    def trigger_reflection(self, level: ReflectionLevel,
                          context: Dict = None) -> Dict:
        """触发反思"""
        context = context or {}
        
        logger.info(f"Triggering {level.value} reflection")
        
        return {
            "level": level.value,
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "status": "initiated"
        }


class ImprovementValidator:
    """改进验证器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self._proposals: Dict[str, ImprovementProposal] = {}
        self._validation_results: Dict[str, Dict] = {}
    
    def create_proposal(self, issue: str, root_cause: str,
                       solution: str, affected_modules: List[str],
                       expected_improvement: float = 0.1,
                       risk_level: str = "low") -> ImprovementProposal:
        """创建改进提案"""
        import uuid
        
        proposal = ImprovementProposal(
            proposal_id=str(uuid.uuid4())[:8],
            issue=issue,
            root_cause=root_cause,
            solution=solution,
            expected_improvement=expected_improvement,
            risk_level=risk_level,
            affected_modules=affected_modules
        )
        
        self._proposals[proposal.proposal_id] = proposal
        return proposal
    
    def validate_improvement(self, proposal_id: str,
                            before_metrics: Dict,
                            after_metrics: Dict) -> Dict:
        """验证改进效果"""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return {"status": "error", "message": "Proposal not found"}
        
        # 计算指标变化
        error_before = before_metrics.get("prediction_error", {}).get("mean", 0)
        error_after = after_metrics.get("prediction_error", {}).get("mean", 0)
        
        satisfaction_before = before_metrics.get("satisfaction", {}).get("mean", 0)
        satisfaction_after = after_metrics.get("satisfaction", {}).get("mean", 0)
        
        error_improvement = (error_before - error_after) / error_before if error_before > 0 else 0
        satisfaction_improvement = (satisfaction_after - satisfaction_before) / satisfaction_before if satisfaction_before > 0 else 0
        
        # 判断是否显著改进
        is_significant = (
            error_improvement >= proposal.expected_improvement * 0.5 or
            satisfaction_improvement >= proposal.expected_improvement * 0.5
        )
        
        result = {
            "proposal_id": proposal_id,
            "status": "success" if is_significant else "insufficient",
            "metrics": {
                "error_improvement": error_improvement,
                "satisfaction_improvement": satisfaction_improvement
            },
            "expected_improvement": proposal.expected_improvement,
            "is_significant": is_significant
        }
        
        self._validation_results[proposal_id] = result
        return result
    
    def get_proposal(self, proposal_id: str) -> Optional[ImprovementProposal]:
        """获取提案"""
        return self._proposals.get(proposal_id)


class MetaController:
    """元认知中枢主类"""
    
    def __init__(self, config: Dict, project_root: Path = None):
        self.config = config
        self.project_root = project_root or Path.cwd()
        
        # 组件初始化
        self.monitor = RealTimeMonitor(config.get("monitor", {}))
        self.scheduler = LearningScheduler(config.get("learning", {}))
        self.reflection_trigger = ReflectionTrigger(config.get("reflection", {}))
        self.validator = ImprovementValidator(config)
        
        # 回调
        self._learning_callbacks: Dict[LearnAction, Callable] = {}
        self._reflection_callback: Optional[Callable] = None
        
        # 后台线程
        self._running = False
        self._scheduler_thread: Optional[threading.Thread] = None
        
        logger.info("MetaController initialized")
    
    def register_learning_callback(self, action: LearnAction,
                                   callback: Callable) -> None:
        """注册学习回调"""
        self._learning_callbacks[action] = callback
    
    def register_reflection_callback(self, callback: Callable) -> None:
        """注册反思回调"""
        self._reflection_callback = callback
    
    def monitor_feedback(self, user_input: str, output: str,
                        feedback: str, satisfaction: float = 0.5) -> None:
        """监控反馈（每次交互后调用）"""
        # 记录满意度
        self.monitor.record_satisfaction(satisfaction)
        
        # 计算预测误差（简化：基于满意度）
        prediction_error = 1.0 - satisfaction
        self.monitor.record_prediction_error(prediction_error)
        
        # 检查反思触发
        state = self.monitor.get_state()
        triggers = self.reflection_trigger.check_triggers(state)
        
        for level, reason in triggers:
            logger.info(f"Reflection triggered: {level.value} - {reason}")
            if self._reflection_callback:
                self._reflection_callback(level, reason)
    
    def schedule_learning(self) -> Optional[ScheduleResult]:
        """调度学习（后台线程调用）"""
        state = self.monitor.get_state()
        result = self.scheduler.schedule_learning(state)
        
        if result:
            logger.debug(f"Learning scheduled: {result.action.value}")
            
            # 执行回调
            callback = self._learning_callbacks.get(result.action)
            if callback:
                try:
                    callback(result.params)
                except Exception as e:
                    logger.error(f"Learning callback failed: {e}")
        
        return result
    
    def trigger_reflection(self, level: ReflectionLevel) -> Dict:
        """手动触发反思"""
        return self.reflection_trigger.trigger_reflection(level)
    
    def propose_improvement(self, issue: str, root_cause: str,
                           solution: str, affected_modules: List[str]) -> ImprovementProposal:
        """提出改进方案"""
        return self.validator.create_proposal(
            issue=issue,
            root_cause=root_cause,
            solution=solution,
            affected_modules=affected_modules
        )
    
    def validate_improvement(self, proposal_id: str,
                            before_metrics: Dict,
                            after_metrics: Dict) -> Dict:
        """验证改进"""
        return self.validator.validate_improvement(
            proposal_id, before_metrics, after_metrics
        )
    
    def start_background_scheduler(self, interval_seconds: int = 60) -> None:
        """启动后台调度器"""
        if self._running:
            return
        
        self._running = True
        
        def scheduler_loop():
            while self._running:
                try:
                    self.schedule_learning()
                except Exception as e:
                    logger.error(f"Scheduler error: {e}")
                
                time.sleep(interval_seconds)
        
        self._scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
        self._scheduler_thread.start()
        
        logger.info(f"Background scheduler started (interval: {interval_seconds}s)")
    
    def stop_background_scheduler(self) -> None:
        """停止后台调度器"""
        self._running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        logger.info("Background scheduler stopped")
    
    def get_status(self) -> Dict:
        """获取元认知状态"""
        return {
            "monitor": self.monitor.get_state(),
            "scheduler": {
                "last_schedules": {
                    action.value: time.isoformat() if time else None
                    for action, time in self.scheduler._last_schedule_time.items()
                }
            },
            "reflection": {
                "last_micro": self.reflection_trigger._last_micro.isoformat() if self.reflection_trigger._last_micro else None,
                "last_macro": self.reflection_trigger._last_macro.isoformat() if self.reflection_trigger._last_macro else None,
                "last_deep": self.reflection_trigger._last_deep.isoformat() if self.reflection_trigger._last_deep else None
            }
        }


# 测试代码
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    config = {
        "monitor": {
            "error_increase_threshold": 0.1,
            "satisfaction_drop_threshold": 0.2
        },
        "learning": {
            "user_feedback_weight": 0.8,
            "self_play_weight": 0.3,
            "doc_ingestion_weight": 0.5
        },
        "reflection": {
            "micro_trigger_threshold": 0.3,
            "macro_trigger_days": 3,
            "deep_trigger_days": 7
        }
    }
    
    controller = MetaController(config)
    
    # 注册回调
    def on_learning(params):
        print(f"Learning callback: {params}")
    
    def on_reflection(level, reason):
        print(f"Reflection callback: {level.value} - {reason}")
    
    controller.register_learning_callback(LearnAction.USER_INTERACTION, on_learning)
    controller.register_reflection_callback(on_reflection)
    
    # 模拟反馈
    controller.monitor_feedback("test input", "test output", "positive", 0.9)
    controller.monitor_feedback("test input 2", "test output 2", "negative", 0.3)
    
    # 获取状态
    status = controller.get_status()
    print(f"Status: {json.dumps(status, indent=2, default=str)}")
    
    # 测试调度
    result = controller.schedule_learning()
    if result:
        print(f"Schedule result: {result.to_dict()}")
    
    # 测试反思
    reflection = controller.trigger_reflection(ReflectionLevel.MICRO)
    print(f"Reflection: {reflection}")
