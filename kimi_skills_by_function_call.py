#!/usr/bin/env python3
"""
KIMI Agent - 系统健康检查技能集成
"""

import json
import logging
import os
import subprocess
import sys
from typing import Any, Dict

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class KIMISkillAgent:
    """KIMI大模型技能Agent"""

    def __init__(self, api_key: str = None, skill_path: str = None):
        """
        初始化Agent

        Args:
            api_key: KIMI API密钥
            skill_path: Skill技能包路径
        """
        self.api_key = api_key or os.getenv("KIMI_API_KEY")
        if not self.api_key:
            raise ValueError("请设置KIMI_API_KEY环境变量")

        self.skill_path = skill_path or os.path.join(
            os.path.dirname(__file__),
            "system-health-check-skill",
            "scripts",
            "health_check.py",
        )

        # 定义技能函数列表（用于Function Calling）
        self.functions = [
            {
                "name": "system_health_check",
                "description": "执行Linux系统健康检查，包括CPU、内存、磁盘、网络和进程状态",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "check_type": {
                            "type": "string",
                            "enum": [
                                "full",
                                "cpu",
                                "memory",
                                "disk",
                                "network",
                                "process",
                            ],
                            "description": "检查类型，full为完整检查，其他为单项检查",
                        },
                        "output_format": {
                            "type": "string",
                            "enum": ["text", "json"],
                            "description": "输出格式",
                            "default": "json",
                        },
                        "threshold_warning": {
                            "type": "integer",
                            "description": "自定义警告阈值（百分比）",
                            "minimum": 0,
                            "maximum": 100,
                        },
                    },
                    "required": ["check_type"],
                },
            }
        ]

    def execute_skill(
        self, function_name: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行技能"""
        if function_name != "system_health_check":
            return {"error": f"未知的函数: {function_name}"}

        try:
            # 构建命令
            cmd = [
                self.skill_path,
                f"--format={parameters.get('output_format', 'json')}",
            ]

            # 如果只检查单项，可以通过参数控制
            check_type = parameters.get("check_type", "full")
            if check_type != "full":
                # 可以通过环境变量传递自定义阈值
                env = os.environ.copy()
                if "threshold_warning" in parameters:
                    env["CUSTOM_THRESHOLD"] = str(parameters["threshold_warning"])

                result = subprocess.run(
                    cmd, capture_output=True, text=True, env=env, timeout=30
                )
            else:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            # 解析输出
            if parameters.get("output_format") == "json":
                try:
                    data = json.loads(result.stdout)
                    return {
                        "success": True,
                        "data": data,
                        "exit_code": result.returncode,
                    }
                except json.JSONDecodeError:
                    return {
                        "success": True,
                        "output": result.stdout,
                        "error_output": result.stderr,
                        "exit_code": result.returncode,
                    }
            else:
                return {
                    "success": True,
                    "output": result.stdout,
                    "error_output": result.stderr,
                    "exit_code": result.returncode,
                }

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "技能执行超时"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def chat_with_kimi(self, user_message: str) -> str:
        """
        与KIMI进行对话（需要安装openai库）

        pip install openai
        """
        try:
            from openai import OpenAI
        except ImportError:
            logger.error("请安装openai库: pip install openai")
            return "错误: 需要安装openai库"

        client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.moonshot.cn/v1",  # KIMI API地址
        )

        messages = [
            {
                "role": "system",
                "content": """你是一个专业的系统运维助手，可以帮助用户检查Linux系统健康状态。
                当用户询问系统状态时，你应该调用system_health_check函数来获取实际数据，
                然后根据返回的结果给用户提供专业的分析和建议。""",
            },
            {"role": "user", "content": user_message},
        ]

        # 第一次请求，获取是否需要调用函数
        response = client.chat.completions.create(
            model="moonshot-v1-8k",
            messages=messages,
            tools=[{"type": "function", "function": func} for func in self.functions],
            tool_choice="auto",
        )

        assistant_message = response.choices[0].message

        # 检查是否需要调用函数
        if assistant_message.tool_calls:
            # 执行函数调用
            tool_call = assistant_message.tool_calls[0]
            function_name = tool_call.function.name
            parameters = json.loads(tool_call.function.arguments)

            logger.info(f"调用函数: {function_name}, 参数: {parameters}")

            # 执行技能
            result = self.execute_skill(function_name, parameters)

            # 将函数结果添加到消息中
            messages.append(assistant_message)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

            # 第二次请求，让KIMI基于函数结果生成回答
            second_response = client.chat.completions.create(
                model="moonshot-v1-8k", messages=messages
            )

            return second_response.choices[0].message.content
        else:
            # 不需要调用函数，直接返回
            return assistant_message.content


def main():
    """主函数 - 命令行交互界面"""
    import argparse

    parser = argparse.ArgumentParser(description="KIMI Agent - 系统健康检查技能")
    parser.add_argument("--api-key", help="KIMI API密钥")
    parser.add_argument("--skill-path", help="技能包路径")
    parser.add_argument("--query", "-q", help="直接查询（非交互模式）")

    args = parser.parse_args()

    try:
        agent = KIMISkillAgent(api_key=args.api_key, skill_path=args.skill_path)

        if args.query:
            # 单次查询模式
            response = agent.chat_with_kimi(args.query)
            print(response)
        else:
            # 交互模式
            print("KIMI Agent 已启动 (输入 'exit' 退出)")
            print("-" * 50)

            while True:
                try:
                    user_input = input("\n你: ").strip()
                    if user_input.lower() in ["exit", "quit", "q"]:
                        break
                    if not user_input:
                        continue

                    print("\nAI: ", end="")
                    response = agent.chat_with_kimi(user_input)
                    print(response)

                except KeyboardInterrupt:
                    print("\n再见！")
                    break
                except Exception as e:
                    print(f"\n错误: {e}")

    except Exception as e:
        print(f"初始化失败: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
