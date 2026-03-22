#!/usr/bin/env python3
"""
工具函数模块
"""

import json
import os
from enum import Enum
from typing import Dict, Any

class AlertLevel(Enum):
    """告警级别"""
    INFO = 'INFO'
    WARNING = 'WARNING'
    CRITICAL = 'CRITICAL'

def color_print(text: str, color: str = None, bold: bool = False) -> str:
    """带颜色的打印（返回带ANSI码的字符串）"""
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'magenta': '\033[95m',
        'cyan': '\033[96m',
        'white': '\033[97m',
        'bold': '\033[1m',
        'reset': '\033[0m'
    }
    
    if color and color in colors:
        text = f"{colors[color]}{text}{colors['reset']}"
    if bold:
        text = f"{colors['bold']}{text}{colors['reset']}"
    
    return text

def get_thresholds() -> Dict[str, Any]:
    """获取阈值配置"""
    # 尝试从references目录加载配置
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, '..', 'references', 'thresholds.json')
    
    default_thresholds = {
        'cpu': {
            'usage': {
                'warning': 80,
                'critical': 95
            }
        },
        'memory': {
            'usage': {
                'warning': 85,
                'critical': 95
            }
        },
        'disk': {
            'usage': {
                'warning': 85,
                'critical': 95
            }
        }
    }
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                thresholds = json.load(f)
                # 合并默认配置
                for key in default_thresholds:
                    if key not in thresholds:
                        thresholds[key] = default_thresholds[key]
                return thresholds
    except Exception:
        pass
    
    return default_thresholds

def check_threshold(value: float, thresholds: Dict[str, int]) -> AlertLevel:
    """检查是否超过阈值"""
    if value >= thresholds.get('critical', 95):
        return AlertLevel.CRITICAL
    elif value >= thresholds.get('warning', 80):
        return AlertLevel.WARNING
    return AlertLevel.INFO

def format_bytes(bytes_val: int) -> str:
    """格式化字节大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PB"

def format_percent(percent: float) -> str:
    """格式化百分比"""
    return f"{percent:.1f}%"
