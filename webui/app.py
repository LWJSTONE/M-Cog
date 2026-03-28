#!/usr/bin/env python3
"""
M-Cog WebUI 监控面板
基于 Flask 的轻量级 Web 界面
"""

import json
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response

logger = logging.getLogger(__name__)

# 全局系统引用
_system = None


def create_app(system):
    """创建 Flask 应用"""
    global _system
    _system = system
    
    app = Flask(__name__)
    app.secret_key = 'm-cog-webui-secret-key'
    
    # 注册路由
    register_routes(app)
    
    return app


def register_routes(app):
    """注册路由"""
    
    @app.route('/')
    def index():
        """主页"""
        return render_template('index.html')
    
    @app.route('/api/status')
    def api_status():
        """系统状态 API"""
        if _system:
            status = _system.get_system_status()
            return jsonify(status)
        return jsonify({"error": "System not initialized"}), 500
    
    @app.route('/api/process', methods=['POST'])
    def api_process():
        """处理输入 API"""
        if not _system:
            return jsonify({"error": "System not initialized"}), 500
        
        data = request.get_json()
        user_input = data.get('input', '')
        context = data.get('context', {})
        
        result = _system.process_input(user_input, context)
        return jsonify(result)
    
    @app.route('/api/feedback', methods=['POST'])
    def api_feedback():
        """反馈 API"""
        if not _system:
            return jsonify({"error": "System not initialized"}), 500
        
        data = request.get_json()
        episode_id = data.get('episode_id')
        feedback = data.get('feedback')
        satisfaction = data.get('satisfaction', 0.5)
        
        _system.record_feedback(episode_id, feedback, satisfaction)
        return jsonify({"status": "ok"})
    
    @app.route('/api/evolution', methods=['POST'])
    def api_evolution():
        """进化周期 API"""
        if not _system:
            return jsonify({"error": "System not initialized"}), 500
        
        result = _system.run_evolution_cycle()
        return jsonify(result)
    
    @app.route('/api/knowledge')
    def api_knowledge():
        """知识库状态"""
        if _system and _system._knowledge_engine:
            stats = _system._knowledge_engine.get_statistics()
            return jsonify(stats)
        return jsonify({"error": "Knowledge engine not available"}), 503
    
    @app.route('/api/knowledge/query', methods=['POST'])
    def api_knowledge_query():
        """知识查询"""
        if not _system or not _system._knowledge_engine:
            return jsonify({"error": "Knowledge engine not available"}), 503
        
        data = request.get_json()
        subject = data.get('subject', '')
        predicate = data.get('predicate', '')
        
        results = _system._knowledge_engine.query(subject, predicate)
        return jsonify({
            "results": [r.to_dict() for r in results]
        })
    
    @app.route('/api/memory')
    def api_memory():
        """记忆系统状态"""
        if _system and _system._memory_system:
            stats = _system._memory_system.get_statistics()
            return jsonify(stats)
        return jsonify({"error": "Memory system not available"}), 503
    
    @app.route('/api/memory/episodes')
    def api_episodes():
        """情景记忆"""
        if not _system or not _system._memory_system:
            return jsonify({"error": "Memory system not available"}), 503
        
        limit = request.args.get('limit', 20, type=int)
        episodes = _system._memory_system.episodic.get_recent_episodes(limit)
        return jsonify({
            "episodes": [ep.to_dict() for ep in episodes]
        })
    
    @app.route('/api/tools')
    def api_tools():
        """工具状态"""
        if _system and _system._tool_factory:
            stats = _system._tool_factory.get_statistics()
            return jsonify(stats)
        return jsonify({"error": "Tool factory not available"}), 503
    
    @app.route('/api/tools/list')
    def api_tools_list():
        """工具列表"""
        if not _system or not _system._tool_factory:
            return jsonify({"error": "Tool factory not available"}), 503
        
        tools = _system._tool_factory.list_tools()
        return jsonify({
            "tools": [t.to_dict() for t in tools]
        })
    
    @app.route('/api/tools/execute', methods=['POST'])
    def api_tools_execute():
        """执行工具"""
        if not _system or not _system._tool_factory:
            return jsonify({"error": "Tool factory not available"}), 503
        
        data = request.get_json()
        tool_id = data.get('tool_id')
        params = data.get('params', {})
        
        result = _system._tool_factory.execute_tool(tool_id, params)
        return jsonify(result.to_dict())
    
    @app.route('/api/experts')
    def api_experts():
        """专家状态"""
        if _system and _system._expert_router:
            stats = _system._expert_router.get_expert_statistics()
            return jsonify(stats)
        return jsonify({"error": "Expert router not available"}), 503
    
    @app.route('/api/safety/check', methods=['POST'])
    def api_safety_check():
        """安全检查"""
        if not _system:
            return jsonify({"error": "System not initialized"}), 500
        
        data = request.get_json()
        action = data.get('action', '')
        target = data.get('target', '')
        
        allowed = _system.check_safety(action, target)
        return jsonify({
            "allowed": allowed,
            "action": action,
            "target": target
        })
    
    @app.route('/api/dialectic/analyze', methods=['POST'])
    def api_dialectic_analyze():
        """辩证分析"""
        if not _system or not _system._dialectic_engine:
            return jsonify({"error": "Dialectic engine not available"}), 503
        
        data = request.get_json()
        topic = data.get('topic', '')
        context = data.get('context', '')
        
        result = _system._dialectic_engine.analyze(topic, context)
        return jsonify(result.to_dict())
    
    @app.route('/api/config')
    def api_config():
        """获取配置"""
        if _system:
            # 过滤敏感信息
            config = _system.config.copy()
            return jsonify(config)
        return jsonify({"error": "System not initialized"}), 500


# 用于直接运行
if __name__ == '__main__':
    app = create_app(None)
    app.run(debug=True, port=5000)
