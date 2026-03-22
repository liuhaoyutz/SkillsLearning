#!/usr/bin/env python3
"""
修复版 MCP Server - 系统健康检查技能
"""

import json
import subprocess
import os
import sys
from typing import Any, List
import asyncio
import traceback

# 添加当前目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.models import InitializationOptions
    import mcp.server.stdio
    import mcp.types as types
except ImportError as e:
    print(f"导入MCP库失败: {e}", file=sys.stderr)
    print("请安装: pip install mcp", file=sys.stderr)
    sys.exit(1)


class SystemHealthMCPServer:
    """系统健康检查MCP服务器"""
    
    def __init__(self):
        # 查找skill脚本路径
        self.skill_path = self._find_skill_path()
        self.server = Server("system-health-check")
        self.setup_handlers()
        print(f"MCP Server初始化完成，Skill路径: {self.skill_path}", file=sys.stderr)
    
    def _find_skill_path(self):
        """查找skill脚本路径"""
        possible_paths = [
            os.path.join(os.path.dirname(__file__), 'system-health-check-skill', 'scripts', 'health_check.py'),
            os.path.join(os.path.dirname(__file__), 'health_check.py'),
            '/usr/local/bin/health_check.py',
            os.path.join(os.getcwd(), 'system-health-check-skill', 'scripts', 'health_check.py')
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                print(f"找到Skill脚本: {path}", file=sys.stderr)
                return path
        
        # 如果找不到，返回默认路径
        default_path = os.path.join(os.path.dirname(__file__), 'system-health-check-skill', 'scripts', 'health_check.py')
        print(f"警告: 未找到Skill脚本，使用默认路径: {default_path}", file=sys.stderr)
        return default_path
    
    def setup_handlers(self):
        """设置MCP处理器"""
        
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            """列出所有可用的工具"""
            return [
                types.Tool(
                    name="system_health_check",
                    description="执行Linux系统健康检查，返回CPU、内存、磁盘、网络等状态",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "check_type": {
                                "type": "string",
                                "enum": ["full", "cpu", "memory", "disk", "network"],
                                "description": "检查类型，full为完整检查",
                                "default": "full"
                            },
                            "output_format": {
                                "type": "string",
                                "enum": ["json", "text"],
                                "description": "输出格式",
                                "default": "json"
                            }
                        }
                    }
                ),
                types.Tool(
                    name="get_cpu_metrics",
                    description="获取CPU使用率、负载等指标",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                types.Tool(
                    name="get_memory_metrics",
                    description="获取内存使用情况",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]
        
        @self.server.call_tool()
        async def handle_call_tool(
            name: str, 
            arguments: dict | None
        ) -> List[types.TextContent]:
            """处理工具调用"""
            
            print(f"调用工具: {name}, 参数: {arguments}", file=sys.stderr)
            
            if name == "system_health_check":
                return await self.run_health_check(arguments or {})
            elif name == "get_cpu_metrics":
                return await self.get_cpu_metrics()
            elif name == "get_memory_metrics":
                return await self.get_memory_metrics()
            else:
                return [types.TextContent(
                    type="text",
                    text=f"未知工具: {name}"
                )]
    
    async def run_health_check(self, args: dict) -> List[types.TextContent]:
        """运行健康检查"""
        output_format = args.get('output_format', 'json')
        
        # 检查skill脚本是否存在
        if not os.path.exists(self.skill_path):
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "Skill脚本不存在",
                    "path": self.skill_path
                }, indent=2)
            )]
        
        # 构建命令
        cmd = [sys.executable, self.skill_path, f"--format={output_format}"]
        
        try:
            print(f"执行命令: {' '.join(cmd)}", file=sys.stderr)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            print(f"命令返回码: {result.returncode}", file=sys.stderr)
            print(f"stdout长度: {len(result.stdout)}", file=sys.stderr)
            
            if result.stderr:
                print(f"stderr: {result.stderr[:200]}", file=sys.stderr)
            
            # 检查是否有输出
            if not result.stdout.strip():
                return [types.TextContent(
                    type="text",
                    text=json.dumps({
                        "error": "脚本没有输出",
                        "stderr": result.stderr,
                        "returncode": result.returncode
                    }, indent=2)
                )]
            
            if output_format == 'json':
                try:
                    # 验证JSON格式
                    data = json.loads(result.stdout)
                    
                    # 添加状态信息（但不影响原有的退出码逻辑）
                    if result.returncode == 2:
                        data['_severity'] = "CRITICAL"
                        data['_message'] = "检测到严重问题，请检查告警信息"
                    elif result.returncode == 1:
                        data['_severity'] = "WARNING"
                        data['_message'] = "检测到警告，建议关注"
                    else:
                        data['_severity'] = "OK"
                        data['_message'] = "系统状态正常"
                    
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(data, indent=2, ensure_ascii=False)
                    )]
                except json.JSONDecodeError as e:
                    return [types.TextContent(
                        type="text",
                        text=json.dumps({
                            "error": f"JSON解析失败: {str(e)}",
                            "raw_output": result.stdout[:500],
                            "stderr": result.stderr
                        }, indent=2)
                    )]
            else:
                return [types.TextContent(
                    type="text",
                    text=result.stdout
                )]
                
        except subprocess.TimeoutExpired:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": "技能执行超时 (30秒)"
                }, indent=2)
            )]
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": f"执行错误: {str(e)}",
                    "traceback": traceback.format_exc()
                }, indent=2)
            )]
    
    async def get_cpu_metrics(self) -> List[types.TextContent]:
        """获取CPU指标"""
        result = await self.run_health_check({'output_format': 'json'})
        
        try:
            # 解析JSON数据
            data = json.loads(result[0].text)
            
            # 提取CPU相关数据
            if 'cpu' in data:
                cpu_data = data['cpu']
                formatted_output = {
                    'usage_percent': cpu_data.get('usage_percent', 0),
                    'core_count': cpu_data.get('core_count', 0),
                    'load_average': cpu_data.get('load_average', {}),
                    'per_cpu_usage': cpu_data.get('per_cpu', []),
                    'status': cpu_data.get('status', 'UNKNOWN'),
                    'severity': data.get('_severity', 'UNKNOWN'),
                    'message': data.get('_message', '')
                }
            else:
                # 如果数据格式不同，尝试直接返回
                formatted_output = {
                    'cpu_data': data.get('cpu', {}),
                    'severity': data.get('_severity', 'UNKNOWN')
                }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(formatted_output, indent=2, ensure_ascii=False)
            )]
        except (json.JSONDecodeError, KeyError, IndexError, AttributeError) as e:
            # 如果解析失败，返回原始结果并添加错误信息
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": f"解析CPU数据失败: {str(e)}",
                    "raw_data": result[0].text[:500]
                }, indent=2)
            )]
    
    async def get_memory_metrics(self) -> List[types.TextContent]:
        """获取内存指标"""
        result = await self.run_health_check({'output_format': 'json'})
        
        try:
            data = json.loads(result[0].text)
            
            # 提取内存相关数据
            if 'memory' in data:
                memory_data = data['memory']
                formatted_output = {
                    'memory': memory_data.get('memory', {}),
                    'swap': memory_data.get('swap', {}),
                    'status': memory_data.get('status', 'UNKNOWN'),
                    'severity': data.get('_severity', 'UNKNOWN'),
                    'message': data.get('_message', '')
                }
            else:
                formatted_output = {
                    'memory_data': data.get('memory', {}),
                    'severity': data.get('_severity', 'UNKNOWN')
                }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(formatted_output, indent=2, ensure_ascii=False)
            )]
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            return [types.TextContent(
                type="text",
                text=json.dumps({
                    "error": f"解析内存数据失败: {str(e)}",
                    "raw_data": result[0].text[:500]
                }, indent=2)
            )]
    
    async def run(self):
        """运行MCP服务器"""
        print("启动MCP服务器...", file=sys.stderr)
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="system-health-check",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )


async def main():
    """主函数"""
    server = SystemHealthMCPServer()
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
