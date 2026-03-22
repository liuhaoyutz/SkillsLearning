# 在Agent中调用此技能的示例
import subprocess
import json

def execute_system_health_skill():
    """执行系统健康检查技能"""
    result = subprocess.run(
        ['./system-health-check-skill/scripts/health_check.py', '--format', 'json'],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        data = json.loads(result.stdout)
        # 根据检查结果做出决策
        if data['cpu']['usage_percent'] > 80:
            return "系统负载较高，建议检查正在运行的进程"
        return "系统状态正常"
    else:
        return f"检查失败: {result.stderr}"

# Agent可以这样调用
response = execute_system_health_skill()
