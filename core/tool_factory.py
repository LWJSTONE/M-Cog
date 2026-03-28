#!/usr/bin/env python3
"""
M-Cog 工具工厂
负责工具的定义、生成、沙盒执行和生命周期管理
"""

import json
import logging
import subprocess
import tempfile
import hashlib
import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, asdict, field
from enum import Enum
import threading
import shutil
import ast
import re

logger = logging.getLogger(__name__)


class ToolType(Enum):
    """工具类型"""
    CODE = "code"
    NEURAL = "neural"


class ToolStatus(Enum):
    """工具状态"""
    DRAFT = "draft"
    TESTING = "testing"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


@dataclass
class ResourceBudget:
    """资源预算"""
    max_cpu_ms: int = 100
    max_memory_mb: int = 50
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ResourceBudget':
        return cls(**data)


@dataclass
class ToolDefinition:
    """工具定义"""
    tool_id: str
    name: str
    tool_type: ToolType
    description: str = ""
    input_schema: Dict = field(default_factory=dict)
    output_schema: Dict = field(default_factory=dict)
    budget: ResourceBudget = field(default_factory=ResourceBudget)
    depends_on: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "type": self.tool_type.value,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "budget": self.budget.to_dict(),
            "depends_on": self.depends_on
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ToolDefinition':
        return cls(
            tool_id=data["tool_id"],
            name=data["name"],
            tool_type=ToolType(data["type"]),
            description=data.get("description", ""),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            budget=ResourceBudget.from_dict(data.get("budget", {})),
            depends_on=data.get("depends_on", [])
        )


@dataclass
class ToolInstance:
    """工具实例"""
    definition: ToolDefinition
    entry_point: str
    source_code: str = ""
    status: ToolStatus = ToolStatus.DRAFT
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    created_at: str = ""
    last_used: str = ""
    
    def to_dict(self) -> Dict:
        return {
            **self.definition.to_dict(),
            "entry_point": self.entry_point,
            "source_code": self.source_code,
            "status": self.status.value,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "success_rate": self.success_count / self.usage_count if self.usage_count > 0 else 0
        }


@dataclass
class ToolCombinator:
    """工具组合器"""
    pattern: str
    sequence: List[str]
    description: str = ""
    success_rate: float = 0.0
    usage_count: int = 0
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    output: Any
    error: str = ""
    execution_time_ms: int = 0
    memory_used_mb: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "memory_used_mb": self.memory_used_mb
        }


class DSLParser:
    """工具定义语言解析器"""
    
    def __init__(self):
        self.keywords = {
            'tool', 'input', 'output', 'type', 'description',
            'budget', 'depends_on', 'max_cpu_ms', 'max_memory_mb'
        }
    
    def parse(self, dsl_text: str) -> ToolDefinition:
        """
        解析工具定义语言
        
        示例:
        tool weather {
            input: location (string), units (string, optional);
            output: temp (number), humidity (number);
            description: "Fetches weather data";
            budget: max_cpu_ms=100, max_memory_mb=20;
        }
        """
        lines = [line.strip() for line in dsl_text.strip().split('\n') if line.strip()]
        
        if not lines or not lines[0].startswith('tool'):
            raise ValueError("DSL must start with 'tool' declaration")
        
        # 解析工具名称
        tool_match = re.match(r'tool\s+(\w+)\s*\{?', lines[0])
        if not tool_match:
            raise ValueError("Invalid tool declaration")
        
        tool_name = tool_match.group(1)
        tool_id = f"tool_{tool_name}"
        
        # 解析其他字段
        input_schema = {}
        output_schema = {}
        description = ""
        budget = ResourceBudget()
        depends_on = []
        
        i = 1
        while i < len(lines):
            line = lines[i].rstrip(';')
            
            if line.startswith('input:'):
                input_schema = self._parse_schema(line[6:].strip())
            elif line.startswith('output:'):
                output_schema = self._parse_schema(line[7:].strip())
            elif line.startswith('description:'):
                description = line[12:].strip().strip('"\'')
            elif line.startswith('budget:'):
                budget = self._parse_budget(line[7:].strip())
            elif line.startswith('depends_on:'):
                depends_on = [d.strip() for d in line[11:].split(',')]
            elif line == '}':
                break
            
            i += 1
        
        return ToolDefinition(
            tool_id=tool_id,
            name=tool_name,
            tool_type=ToolType.CODE,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            budget=budget,
            depends_on=depends_on
        )
    
    def _parse_schema(self, schema_str: str) -> Dict:
        """解析输入输出模式"""
        schema = {}
        
        for field_def in schema_str.split(','):
            field_def = field_def.strip()
            if not field_def:
                continue
            
            # 解析字段名和类型
            parts = field_def.split('(')
            field_name = parts[0].strip()
            
            if len(parts) > 1:
                type_info = parts[1].rstrip(')').strip()
                type_parts = type_info.split(',')
                field_type = type_parts[0].strip()
                optional = 'optional' in [p.strip() for p in type_parts[1:]]
            else:
                field_type = "any"
                optional = False
            
            schema[field_name] = {
                "type": field_type,
                "optional": optional
            }
        
        return schema
    
    def _parse_budget(self, budget_str: str) -> ResourceBudget:
        """解析资源预算"""
        budget = ResourceBudget()
        
        for item in budget_str.split(','):
            item = item.strip()
            if '=' in item:
                key, value = item.split('=')
                key = key.strip()
                value = int(value.strip())
                
                if key == 'max_cpu_ms':
                    budget.max_cpu_ms = value
                elif key == 'max_memory_mb':
                    budget.max_memory_mb = value
        
        return budget


class CodeGenerator:
    """代码生成器"""
    
    PYTHON_TEMPLATE = '''
"""
Auto-generated tool: {name}
{description}
"""

import json
import time
from typing import Dict, Any

def validate_input(params: Dict[str, Any]) -> bool:
    """Validate input parameters"""
    {input_validation}
    return True

def execute(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute the tool
    
    Args:
        params: Input parameters
            {input_docs}
    
    Returns:
        Output dictionary
            {output_docs}
    """
    # Validate input
    validate_input(params)
    
    # Extract parameters
    {extract_params}
    
    # TODO: Implement tool logic here
    result = {{
        {output_defaults}
    }}
    
    return result

def main():
    """Main entry point for command line usage"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python {filename} '<json_params>'")
        sys.exit(1)
    
    try:
        params = json.loads(sys.argv[1])
        result = execute(params)
        print(json.dumps(result))
    except Exception as e:
        print(json.dumps({{"error": str(e)}}))
        sys.exit(1)

if __name__ == "__main__":
    main()
'''

    CPP_TEMPLATE = '''
/*
 * Auto-generated tool: {name}
 * {description}
 */

#include <iostream>
#include <string>
#include <json/json.h>

struct InputParams {{
    {input_struct}
}};

struct OutputResult {{
    {output_struct}
}};

OutputResult execute(const InputParams& params) {{
    OutputResult result;
    // TODO: Implement tool logic here
    return result;
}}

int main(int argc, char* argv[]) {{
    if (argc < 2) {{
        std::cerr << "Usage: " << argv[0] << " <json_params>" << std::endl;
        return 1;
    }}
    
    try {{
        Json::Value root;
        Json::Reader reader;
        reader.parse(argv[1], root);
        
        InputParams params;
        {parse_input}
        
        OutputResult result = execute(params);
        
        Json::Value output;
        {format_output}
        
        std::cout << output << std::endl;
    }} catch (const std::exception& e) {{
        std::cerr << "{{\\"error\\": \\"" << e.what() << "\\"}}" << std::endl;
        return 1;
    }}
    
    return 0;
}}
'''

    def generate_python(self, definition: ToolDefinition) -> str:
        """生成 Python 代码"""
        # 输入验证代码
        input_validation_lines = []
        for field_name, field_info in definition.input_schema.items():
            if not field_info.get("optional", False):
                input_validation_lines.append(
                    f'if "{field_name}" not in params:\n'
                    f'    raise ValueError("Missing required parameter: {field_name}")'
                )
        input_validation = '\n    '.join(input_validation_lines) or 'pass'
        
        # 输入文档
        input_docs = '\n            '.join(
            f"{name}: {info.get('type', 'any')}"
            for name, info in definition.input_schema.items()
        ) or "None"
        
        # 输出文档
        output_docs = '\n            '.join(
            f"{name}: {info.get('type', 'any')}"
            for name, info in definition.output_schema.items()
        ) or "None"
        
        # 参数提取
        extract_params = '\n    '.join(
            f"{name} = params.get('{name}')"
            for name in definition.input_schema.keys()
        ) or "pass"
        
        # 输出默认值
        output_defaults = ',\n        '.join(
            f'"{name}": None'
            for name in definition.output_schema.keys()
        ) or '"result": None'
        
        return self.PYTHON_TEMPLATE.format(
            name=definition.name,
            description=definition.description,
            input_validation=input_validation,
            input_docs=input_docs,
            output_docs=output_docs,
            extract_params=extract_params,
            output_defaults=output_defaults,
            filename=f"{definition.name}.py"
        )
    
    def generate_cpp(self, definition: ToolDefinition) -> str:
        """生成 C++ 代码"""
        # 简化版本，实际需要更复杂的模板
        input_struct = '\n    '.join(
            f'std::string {name};' if info.get('type') == 'string' else f'double {name};'
            for name, info in definition.input_schema.items()
        ) or 'char placeholder;'
        
        output_struct = '\n    '.join(
            f'std::string {name};' if info.get('type') == 'string' else f'double {name};'
            for name, info in definition.output_schema.items()
        ) or 'char placeholder;'
        
        return self.CPP_TEMPLATE.format(
            name=definition.name,
            description=definition.description,
            input_struct=input_struct,
            output_struct=output_struct,
            parse_input="// Parse input",
            format_output="// Format output"
        )


class SandboxExecutor:
    """沙盒执行器"""
    
    FORBIDDEN_IMPORTS = {
        'os.system', 'os.popen', 'subprocess.call', 'subprocess.run',
        'subprocess.Popen', 'eval', 'exec', 'compile', '__import__',
        'shutil.rmtree', 'shutil.move', 'shutil.copy'
    }
    
    FORBIDDEN_FUNCTIONS = {
        'system', 'popen', 'exec', 'eval', 'compile'
    }
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.sandbox_enabled = self.config.get("sandbox_enabled", True)
        self.max_cpu_ms = self.config.get("max_tool_cpu_ms", 100)
        self.max_memory_mb = self.config.get("max_tool_memory_mb", 50)
    
    def validate_code(self, source_code: str) -> Tuple[bool, str]:
        """验证代码安全性"""
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        
        # 检查禁止的导入
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in self.FORBIDDEN_IMPORTS:
                        return False, f"Forbidden import: {alias.name}"
            
            elif isinstance(node, ast.ImportFrom):
                if node.module in self.FORBIDDEN_IMPORTS:
                    return False, f"Forbidden import from: {node.module}"
            
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.FORBIDDEN_FUNCTIONS:
                        return False, f"Forbidden function: {node.func.id}"
        
        return True, "Code validation passed"
    
    def execute(self, source_code: str, params: Dict,
               timeout_ms: int = None) -> ExecutionResult:
        """在沙盒中执行代码"""
        timeout_ms = timeout_ms or self.max_cpu_ms
        
        # 验证代码
        if self.sandbox_enabled:
            is_valid, message = self.validate_code(source_code)
            if not is_valid:
                return ExecutionResult(
                    success=False,
                    output=None,
                    error=f"Code validation failed: {message}"
                )
        
        start_time = time.time()
        
        try:
            # 创建临时文件执行
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.py', delete=False
            ) as f:
                f.write(source_code)
                temp_file = f.name
            
            # 执行
            result = subprocess.run(
                [sys.executable, temp_file, json.dumps(params)],
                capture_output=True,
                text=True,
                timeout=timeout_ms / 1000
            )
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            if result.returncode != 0:
                return ExecutionResult(
                    success=False,
                    output=None,
                    error=result.stderr or "Unknown error",
                    execution_time_ms=execution_time_ms
                )
            
            output = json.loads(result.stdout)
            
            return ExecutionResult(
                success=True,
                output=output,
                execution_time_ms=execution_time_ms
            )
            
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                success=False,
                output=None,
                error=f"Execution timeout ({timeout_ms}ms)"
            )
        except json.JSONDecodeError as e:
            return ExecutionResult(
                success=False,
                output=None,
                error=f"Invalid JSON output: {e}"
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output=None,
                error=str(e)
            )
        finally:
            # 清理临时文件
            try:
                os.unlink(temp_file)
            except:
                pass


class ToolFactory:
    """工具工厂主类"""
    
    def __init__(self, config: Dict, project_root: Path = None):
        self.config = config
        self.project_root = project_root or Path.cwd()
        
        self.registry_path = self.project_root / config.get(
            "registry_path", "mutable/tools/registry.json"
        )
        self.sources_dir = self.project_root / config.get(
            "sources_dir", "mutable/tools/sources"
        )
        self.compiled_dir = self.project_root / config.get(
            "compiled_dir", "mutable/tools/compiled"
        )
        
        # 组件
        self.dsl_parser = DSLParser()
        self.code_generator = CodeGenerator()
        self.sandbox = SandboxExecutor(config)
        
        # 工具注册表
        self.tools: Dict[str, ToolInstance] = {}
        self.combinators: List[ToolCombinator] = []
        
        # 创建目录
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        self.compiled_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载注册表
        self._load_registry()
        
        logger.info(f"ToolFactory initialized with {len(self.tools)} tools")
    
    def _load_registry(self) -> None:
        """加载工具注册表"""
        if self.registry_path.exists():
            try:
                with open(self.registry_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 加载工具
                for tool_data in data.get("tools", []):
                    tool_id = tool_data["tool_id"]
                    definition = ToolDefinition.from_dict(tool_data)
                    
                    # 加载源代码
                    source_file = self.sources_dir / f"{tool_id}.py"
                    source_code = ""
                    if source_file.exists():
                        with open(source_file, 'r', encoding='utf-8') as f:
                            source_code = f.read()
                    
                    self.tools[tool_id] = ToolInstance(
                        definition=definition,
                        entry_point=tool_data.get("entry_point", ""),
                        source_code=source_code,
                        status=ToolStatus(tool_data.get("status", "active")),
                        usage_count=tool_data.get("usage_count", 0),
                        success_count=tool_data.get("success_count", 0),
                        failure_count=tool_data.get("failure_count", 0),
                        created_at=tool_data.get("created_at", ""),
                        last_used=tool_data.get("last_used", "")
                    )
                
                # 加载组合器
                for comb_data in data.get("combinators", []):
                    self.combinators.append(ToolCombinator(
                        pattern=comb_data.get("pattern", ""),
                        sequence=comb_data.get("sequence", []),
                        description=comb_data.get("description", ""),
                        success_rate=comb_data.get("success_rate", 0.0),
                        usage_count=comb_data.get("usage_count", 0)
                    ))
                
                logger.info(f"Loaded {len(self.tools)} tools from registry")
                
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
    
    def _save_registry(self) -> None:
        """保存工具注册表"""
        data = {
            "tools": [tool.to_dict() for tool in self.tools.values()],
            "combinators": [c.to_dict() for c in self.combinators],
            "metadata": {
                "updated_at": datetime.now().isoformat(),
                "version": "1.0.0"
            }
        }
        
        with open(self.registry_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    def create_tool_from_dsl(self, dsl_text: str) -> ToolInstance:
        """从 DSL 创建工具"""
        # 解析 DSL
        definition = self.dsl_parser.parse(dsl_text)
        
        # 生成代码
        source_code = self.code_generator.generate_python(definition)
        
        # 保存源代码
        source_file = self.sources_dir / f"{definition.tool_id}.py"
        with open(source_file, 'w', encoding='utf-8') as f:
            f.write(source_code)
        
        # 创建实例
        instance = ToolInstance(
            definition=definition,
            entry_point=str(source_file),
            source_code=source_code,
            status=ToolStatus.DRAFT,
            created_at=datetime.now().isoformat()
        )
        
        self.tools[definition.tool_id] = instance
        self._save_registry()
        
        logger.info(f"Created tool from DSL: {definition.tool_id}")
        return instance
    
    def test_tool(self, tool_id: str, test_params: Dict) -> ExecutionResult:
        """测试工具"""
        tool = self.tools.get(tool_id)
        if not tool:
            return ExecutionResult(
                success=False,
                output=None,
                error=f"Tool not found: {tool_id}"
            )
        
        result = self.sandbox.execute(tool.source_code, test_params)
        
        # 更新统计
        tool.usage_count += 1
        if result.success:
            tool.success_count += 1
            if tool.status == ToolStatus.DRAFT:
                tool.status = ToolStatus.ACTIVE
        else:
            tool.failure_count += 1
        
        tool.last_used = datetime.now().isoformat()
        self._save_registry()
        
        return result
    
    def execute_tool(self, tool_id: str, params: Dict) -> ExecutionResult:
        """执行工具"""
        return self.test_tool(tool_id, params)
    
    def register_combinator(self, pattern: str, sequence: List[str],
                           description: str = "") -> ToolCombinator:
        """注册工具组合器"""
        combinator = ToolCombinator(
            pattern=pattern,
            sequence=sequence,
            description=description
        )
        
        self.combinators.append(combinator)
        self._save_registry()
        
        logger.info(f"Registered combinator: {pattern}")
        return combinator
    
    def execute_combinator(self, pattern: str, params: Dict) -> ExecutionResult:
        """执行组合工具"""
        # 查找组合器
        combinator = None
        for c in self.combinators:
            if c.pattern == pattern:
                combinator = c
                break
        
        if not combinator:
            return ExecutionResult(
                success=False,
                output=None,
                error=f"Combinator not found: {pattern}"
            )
        
        # 顺序执行工具
        current_output = params
        total_time = 0
        
        for tool_id in combinator.sequence:
            result = self.execute_tool(tool_id, current_output)
            total_time += result.execution_time_ms
            
            if not result.success:
                return ExecutionResult(
                    success=False,
                    output=None,
                    error=f"Tool {tool_id} failed: {result.error}",
                    execution_time_ms=total_time
                )
            
            current_output = result.output
        
        # 更新组合器统计
        combinator.usage_count += 1
        
        return ExecutionResult(
            success=True,
            output=current_output,
            execution_time_ms=total_time
        )
    
    def audit_tools(self, days_unused: int = 30) -> Dict:
        """工具审计"""
        now = datetime.now()
        stats = {
            "total": len(self.tools),
            "active": 0,
            "deprecated": 0,
            "to_archive": [],
            "to_promote": []
        }
        
        for tool_id, tool in self.tools.items():
            if tool.status == ToolStatus.ACTIVE:
                stats["active"] += 1
            
            # 检查是否需要归档
            if tool.usage_count == 0 and tool.created_at:
                created = datetime.fromisoformat(tool.created_at)
                if (now - created).days > days_unused:
                    stats["to_archive"].append(tool_id)
            
            # 检查是否可以提升为稳定
            if tool.usage_count > 100:
                success_rate = tool.success_count / tool.usage_count
                if success_rate > 0.9:
                    stats["to_promote"].append(tool_id)
        
        return stats
    
    def archive_tool(self, tool_id: str) -> bool:
        """归档工具"""
        tool = self.tools.get(tool_id)
        if not tool:
            return False
        
        tool.status = ToolStatus.ARCHIVED
        self._save_registry()
        
        logger.info(f"Archived tool: {tool_id}")
        return True
    
    def get_tool(self, tool_id: str) -> Optional[ToolInstance]:
        """获取工具"""
        return self.tools.get(tool_id)
    
    def list_tools(self, status: ToolStatus = None) -> List[ToolInstance]:
        """列出工具"""
        tools = list(self.tools.values())
        if status:
            tools = [t for t in tools if t.status == status]
        return tools
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        total_usage = sum(t.usage_count for t in self.tools.values())
        total_success = sum(t.success_count for t in self.tools.values())
        
        return {
            "total_tools": len(self.tools),
            "active_tools": len([t for t in self.tools.values() if t.status == ToolStatus.ACTIVE]),
            "total_usage": total_usage,
            "overall_success_rate": total_success / total_usage if total_usage > 0 else 0,
            "combinators": len(self.combinators)
        }


# 测试代码
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = {
            "registry_path": "tools/registry.json",
            "sources_dir": "tools/sources",
            "compiled_dir": "tools/compiled",
            "sandbox_enabled": True
        }
        
        factory = ToolFactory(config, Path(tmpdir))
        
        # 从 DSL 创建工具
        dsl = '''
        tool calculator {
            input: a (number), b (number), operation (string);
            output: result (number);
            description: "Performs basic calculations";
            budget: max_cpu_ms=10, max_memory_mb=5;
        }
        '''
        
        tool = factory.create_tool_from_dsl(dsl)
        print(f"Created tool: {tool.definition.tool_id}")
        print(f"Source code:\n{tool.source_code[:500]}...")
        
        # 测试工具
        result = factory.test_tool(
            "tool_calculator",
            {"a": 5, "b": 3, "operation": "add"}
        )
        print(f"Test result: {result.to_dict()}")
        
        # 统计
        stats = factory.get_statistics()
        print(f"Statistics: {stats}")
