#!/usr/bin/env python3
"""
修正版 KIMI MCP Client - 通过MCP协议使用技能
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, List
import subprocess

try:
    from openai import OpenAI
except ImportError:
    print("错误: 需要安装openai库")
    print("请运行: pip install openai")
    sys.exit(1)

try:
    from mcp import ClientSession, StdioServerParameters
    import mcp.client.stdio
except ImportError as e:
    print(f"导入MCP库失败: {e}")
    print("请安装: pip install mcp")
    sys.exit(1)


class KIMIMCPClient:
    """KIMI MCP客户端"""
    
    def __init__(self, api_key: str = None, server_script: str = None):
        """
        初始化客户端
        
        Args:
            api_key: KIMI API密钥
            server_script: MCP服务器脚本路径
        """
        self.api_key = api_key or os.getenv('KIMI_API_KEY')
        if not self.api_key:
            raise ValueError("请设置KIMI_API_KEY环境变量")
        
        # 查找服务器脚本
        if server_script is None:
            server_script = os.path.join(
                os.path.dirname(__file__),
                'kimi_skills_by_MCP_server.py'
            )
        
        if not os.path.exists(server_script):
            raise ValueError(f"服务器脚本不存在: {server_script}")
        
        self.server_script = server_script
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.moonshot.cn/v1"
        )
        
        print(f"客户端初始化完成，服务器脚本: {self.server_script}")
    
    async def query_with_tools(self, user_message: str) -> str:
        """
        使用MCP工具进行查询
        
        Args:
            user_message: 用户消息
            
        Returns:
            AI回答
        """
        print(f"\n用户消息: {user_message}")
        
        try:
            # 启动MCP服务器
            server_params = StdioServerParameters(
                command=sys.executable,  # 使用当前Python解释器
                args=[self.server_script]
            )
            
            print("启动MCP服务器...")
            
            async with mcp.client.stdio.stdio_client(server_params) as (read, write):
                print("MCP客户端已连接")
                
                async with ClientSession(read, write) as session:
                    print("创建会话...")
                    
                    # 初始化会话
                    await session.initialize()
                    print("会话初始化完成")
                    
                    # 获取可用工具
                    tools_response = await session.list_tools()
                    print(f"获取到 {len(tools_response.tools)} 个工具")
                    
                    # 转换为OpenAI工具格式
                    tools = []
                    for tool in tools_response.tools:
                        openai_tool = {
                            "type": "function",
                            "function": {
                                "name": tool.name,
                                "description": tool.description,
                                "parameters": tool.inputSchema
                            }
                        }
                        tools.append(openai_tool)
                        print(f"  - 工具: {tool.name}")
                    
                    # 构建KIMI请求
                    messages = [
                        {
                            "role": "system",
                            "content": """你是一个专业的系统运维助手，可以使用提供的工具来检查系统状态。
                            当用户询问系统健康状态时，请调用相应的工具获取实际数据，然后根据返回的结果给用户提供专业的分析和建议。
                            如果工具返回错误，请告知用户错误信息并建议稍后重试。"""
                        },
                        {
                            "role": "user",
                            "content": user_message
                        }
                    ]
                    
                    print("\n调用KIMI API...")
                    
                    # 调用KIMI
                    response = self.client.chat.completions.create(
                        model="moonshot-v1-8k",
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                        temperature=0.1
                    )
                    
                    assistant_message = response.choices[0].message
                    print(f"KIMI响应: {assistant_message.content if assistant_message.content else '需要调用工具'}")
                    
                    # 处理工具调用
                    if assistant_message.tool_calls:
                        print(f"\n检测到工具调用: {len(assistant_message.tool_calls)} 个")
                        messages.append(assistant_message)
                        
                        for tool_call in assistant_message.tool_calls:
                            tool_name = tool_call.function.name
                            tool_args = json.loads(tool_call.function.arguments)
                            
                            print(f"调用工具: {tool_name}, 参数: {tool_args}")
                            
                            # 调用MCP工具
                            try:
                                result = await session.call_tool(tool_name, tool_args)
                                tool_result = result.content[0].text
                                print(f"工具返回: {tool_result[:200]}...")
                            except Exception as e:
                                tool_result = f"工具调用失败: {str(e)}"
                                print(f"工具调用失败: {e}")
                            
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": tool_result
                            })
                        
                        # 获取最终回答
                        print("\n获取最终回答...")
                        final_response = self.client.chat.completions.create(
                            model="moonshot-v1-8k",
                            messages=messages,
                            temperature=0.1
                        )
                        
                        final_answer = final_response.choices[0].message.content
                        print(f"最终回答: {final_answer[:200]}...")
                        return final_answer
                    
                    return assistant_message.content or "无法理解您的请求"
                    
        except Exception as e:
            error_msg = f"执行出错: {str(e)}"
            print(error_msg, file=sys.stderr)
            import traceback
            traceback.print_exc()
            return f"抱歉，执行过程中出现错误: {str(e)}"


async def test_mcp_server_direct():
    """直接测试MCP服务器（不通过KIMI）"""
    print("=" * 60)
    print("测试MCP服务器直接调用")
    print("=" * 60)
    
    server_script = os.path.join(
        os.path.dirname(__file__),
        'kimi_skills_by_MCP_server.py'
    )
    
    if not os.path.exists(server_script):
        print(f"错误: 找不到服务器脚本 {server_script}")
        return
    
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[server_script]
    )
    
    try:
        async with mcp.client.stdio.stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                print("✓ MCP服务器连接成功")
                
                # 列出工具
                tools = await session.list_tools()
                print(f"✓ 可用工具: {[t.name for t in tools.tools]}")
                
                # 测试调用工具
                result = await session.call_tool("system_health_check", {"output_format": "json"})
                print(f"✓ 工具调用成功")
                print(f"返回数据预览: {result.content[0].text[:500]}")
                
                return True
    except Exception as e:
        print(f"✗ MCP服务器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='KIMI MCP Client')
    parser.add_argument('--api-key', help='KIMI API密钥')
    parser.add_argument('--query', '-q', help='直接查询')
    parser.add_argument('--test', action='store_true', help='测试MCP服务器')
    
    args = parser.parse_args()
    
    # 测试模式
    if args.test:
        success = await test_mcp_server_direct()
        sys.exit(0 if success else 1)
    
    try:
        client = KIMIMCPClient(api_key=args.api_key)
        
        if args.query:
            # 单次查询
            response = await client.query_with_tools(args.query)
            print("\n" + "=" * 60)
            print("AI回答:")
            print("=" * 60)
            print(response)
        else:
            # 交互模式
            print("KIMI MCP Agent 已启动")
            print("=" * 60)
            print("命令:")
            print("  - 输入问题直接查询")
            print("  - 输入 'test' 测试MCP服务器")
            print("  - 输入 'exit' 退出")
            print("=" * 60)
            
            while True:
                try:
                    user_input = input("\n你: ").strip()
                    
                    if user_input.lower() in ['exit', 'quit', 'q']:
                        break
                    
                    if user_input.lower() == 'test':
                        await test_mcp_server_direct()
                        continue
                    
                    if not user_input:
                        continue
                    
                    print("\nAI: ", end="", flush=True)
                    response = await client.query_with_tools(user_input)
                    print(response)
                    
                except KeyboardInterrupt:
                    print("\n\n再见！")
                    break
                except Exception as e:
                    print(f"\n错误: {e}")
                    import traceback
                    traceback.print_exc()
                    
    except Exception as e:
        print(f"初始化失败: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    asyncio.run(main())
