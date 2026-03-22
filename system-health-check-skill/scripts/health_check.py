#!/usr/bin/env python3
"""
系统健康检查技能 - 主程序（修复版）
"""

import json
import sys
import time
from datetime import datetime
from typing import Dict, Any
import os
import traceback

# 添加当前目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 检查psutil是否安装
try:
    import psutil
except ImportError as e:
    error_msg = {
        "error": "psutil库未安装",
        "message": "请运行: pip3 install psutil",
        "exception": str(e)
    }
    print(json.dumps(error_msg, indent=2))
    sys.exit(1)

from utils import (
    color_print, get_thresholds, check_threshold,
    format_bytes, format_percent, AlertLevel
)

class SystemHealthChecker:
    """系统健康检查器"""
    
    def __init__(self):
        try:
            self.thresholds = get_thresholds()
        except Exception as e:
            print(f"警告: 加载阈值配置失败: {e}", file=sys.stderr)
            self.thresholds = {
                'cpu': {'usage': {'warning': 80, 'critical': 95}},
                'memory': {'usage': {'warning': 85, 'critical': 95}},
                'disk': {'usage': {'warning': 85, 'critical': 95}}
            }
        
        self.alerts = []
        self.start_time = time.time()
        
    def check_cpu(self) -> Dict[str, Any]:
        """检查CPU状态"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg()
            
            result = {
                'status': 'OK',
                'usage_percent': cpu_percent,
                'core_count': cpu_count,
                'load_average': {
                    '1min': load_avg[0],
                    '5min': load_avg[1],
                    '15min': load_avg[2]
                },
                'per_cpu': psutil.cpu_percent(interval=0, percpu=True)
            }
            
            # 检查阈值
            if 'cpu' in self.thresholds:
                level = check_threshold(cpu_percent, self.thresholds['cpu']['usage'])
                if level != AlertLevel.INFO:
                    result['status'] = level.value
                    self.alerts.append({
                        'component': 'CPU',
                        'level': level.value,
                        'message': f"CPU使用率 {cpu_percent}% 超过阈值"
                    })
            
            return result
        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e),
                'usage_percent': 0,
                'core_count': 0,
                'load_average': {'1min': 0, '5min': 0, '15min': 0}
            }
    
    def check_memory(self) -> Dict[str, Any]:
        """检查内存状态"""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            result = {
                'status': 'OK',
                'memory': {
                    'total': format_bytes(mem.total),
                    'available': format_bytes(mem.available),
                    'used': format_bytes(mem.used),
                    'percent': mem.percent,
                    'used_formatted': format_percent(mem.percent)
                },
                'swap': {
                    'total': format_bytes(swap.total),
                    'used': format_bytes(swap.used),
                    'percent': swap.percent,
                    'used_formatted': format_percent(swap.percent)
                }
            }
            
            # 检查内存阈值
            if 'memory' in self.thresholds:
                level = check_threshold(mem.percent, self.thresholds['memory']['usage'])
                if level != AlertLevel.INFO:
                    result['status'] = level.value
                    self.alerts.append({
                        'component': 'Memory',
                        'level': level.value,
                        'message': f"内存使用率 {mem.percent}% 超过阈值"
                    })
            
            return result
        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }
    
    def check_disk(self) -> Dict[str, Any]:
        """检查磁盘状态"""
        try:
            partitions = []
            issues = []
            
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    usage_percent = usage.percent
                    
                    partition_info = {
                        'device': partition.device,
                        'mountpoint': partition.mountpoint,
                        'fstype': partition.fstype,
                        'total': format_bytes(usage.total),
                        'used': format_bytes(usage.used),
                        'free': format_bytes(usage.free),
                        'percent': usage_percent,
                        'percent_formatted': format_percent(usage_percent),
                        'status': 'OK'
                    }
                    
                    # 检查磁盘使用阈值
                    if 'disk' in self.thresholds:
                        level = check_threshold(usage_percent, self.thresholds['disk']['usage'])
                        if level != AlertLevel.INFO:
                            partition_info['status'] = level.value
                            issues.append({
                                'component': f"Disk {partition.mountpoint}",
                                'level': level.value,
                                'message': f"磁盘使用率 {usage_percent}% 超过阈值"
                            })
                    
                    partitions.append(partition_info)
                    
                except (PermissionError, OSError) as e:
                    # 跳过无法访问的分区
                    continue
            
            if issues:
                self.alerts.extend(issues)
            
            return {
                'status': 'OK' if not issues else 'WARNING',
                'partitions': partitions
            }
        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e),
                'partitions': []
            }
    
    def check_network(self) -> Dict[str, Any]:
        """检查网络状态"""
        try:
            net_io = psutil.net_io_counters()
            connections = len(psutil.net_connections())
            
            result = {
                'status': 'OK',
                'network_io': {
                    'bytes_sent': format_bytes(net_io.bytes_sent),
                    'bytes_recv': format_bytes(net_io.bytes_recv),
                    'packets_sent': net_io.packets_sent,
                    'packets_recv': net_io.packets_recv,
                    'errin': net_io.errin,
                    'errout': net_io.errout
                },
                'active_connections': connections
            }
            
            # 检查错误包
            if net_io.errin > 0 or net_io.errout > 0:
                level = AlertLevel.WARNING
                result['status'] = level.value
                self.alerts.append({
                    'component': 'Network',
                    'level': level.value,
                    'message': f"检测到网络错误 - 接收错误: {net_io.errin}, 发送错误: {net_io.errout}"
                })
            
            return result
        except Exception as e:
            return {
                'status': 'ERROR',
                'error': str(e)
            }
    
    def check_processes(self) -> Dict[str, Any]:
        """检查关键进程"""
        try:
            critical_processes = ['sshd', 'systemd', 'cron', 'rsyslog']
            running_processes = []
            missing_processes = []
            
            for proc in psutil.process_iter(['name', 'pid', 'cpu_percent', 'memory_percent']):
                try:
                    proc_info = proc.info
                    if proc_info['name'] in critical_processes:
                        running_processes.append(proc_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            running_names = [p['name'] for p in running_processes]
            for proc in critical_processes:
                if proc not in running_names:
                    missing_processes.append(proc)
            
            if missing_processes:
                self.alerts.append({
                    'component': 'Process',
                    'level': AlertLevel.WARNING.value,
                    'message': f"关键进程未运行: {', '.join(missing_processes)}"
                })
            
            return {
                'critical_processes': running_processes,
                'missing_processes': missing_processes
            }
        except Exception as e:
            return {
                'error': str(e),
                'critical_processes': [],
                'missing_processes': []
            }
    
    def run(self, output_format: str = 'text') -> int:
        """运行完整健康检查"""
        try:
            results = {
                'cpu': self.check_cpu(),
                'memory': self.check_memory(),
                'disk': self.check_disk(),
                'network': self.check_network(),
                'processes': self.check_processes(),
                'timestamp': datetime.now().isoformat(),
                'hostname': os.uname().nodename
            }
            
            if output_format == 'json':
                # 确保输出有效的JSON
                json_output = json.dumps(results, indent=2, ensure_ascii=False, default=str)
                print(json_output)
            else:
                # 文本输出
                report = self.generate_report(results)
                print(report)
            
            # 返回状态码
            has_critical = any(alert.get('level') == 'CRITICAL' for alert in self.alerts)
            if has_critical:
                return 2
            elif self.alerts:
                return 1
            else:
                return 0
                
        except Exception as e:
            error_output = {
                "error": str(e),
                "traceback": traceback.format_exc()
            }
            print(json.dumps(error_output), file=sys.stderr)
            return 2
    
    def generate_report(self, results: Dict[str, Any]) -> str:
        """生成人类可读的报告"""
        duration = time.time() - self.start_time
        
        report = []
        report.append("=" * 60)
        report.append("系统健康检查报告")
        report.append(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"检查耗时: {duration:.2f} 秒")
        report.append(f"主机名: {results.get('hostname', 'unknown')}")
        report.append("=" * 60)
        
        # CPU信息
        cpu = results.get('cpu', {})
        if cpu.get('status') != 'ERROR':
            report.append("\nCPU状态:")
            report.append(f"  使用率: {cpu.get('usage_percent', 0)}%")
            report.append(f"  核心数: {cpu.get('core_count', 0)}")
            load = cpu.get('load_average', {})
            report.append(f"  负载: 1m={load.get('1min', 0):.2f}, 5m={load.get('5min', 0):.2f}, 15m={load.get('15min', 0):.2f}")
        else:
            report.append(f"\nCPU状态: 错误 - {cpu.get('error', 'unknown')}")
        
        # 内存信息
        mem = results.get('memory', {})
        if mem.get('status') != 'ERROR':
            mem_data = mem.get('memory', {})
            report.append("\n内存状态:")
            report.append(f"  总计: {mem_data.get('total', 'N/A')}")
            report.append(f"  已用: {mem_data.get('used', 'N/A')} ({mem_data.get('used_formatted', 'N/A')})")
            report.append(f"  可用: {mem_data.get('available', 'N/A')}")
        else:
            report.append(f"\n内存状态: 错误 - {mem.get('error', 'unknown')}")
        
        # 磁盘信息
        disk = results.get('disk', {})
        if disk.get('status') != 'ERROR':
            report.append("\n磁盘状态:")
            for part in disk.get('partitions', []):
                report.append(f"  {part['mountpoint']}: {part['percent_formatted']} "
                            f"({part['used']}/{part['total']})")
        else:
            report.append(f"\n磁盘状态: 错误 - {disk.get('error', 'unknown')}")
        
        # 告警信息
        if self.alerts:
            report.append(f"\n告警信息:")
            for alert in self.alerts:
                report.append(f"  [{alert['level']}] {alert['component']}: {alert['message']}")
        else:
            report.append(f"\n✓ 所有检查项均正常")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='系统健康检查工具')
    parser.add_argument('--format', '-f', choices=['text', 'json'], 
                       default='text', help='输出格式')
    parser.add_argument('--quick', '-q', action='store_true',
                       help='快速检查（跳过耗时项目）')
    
    args = parser.parse_args()
    
    checker = SystemHealthChecker()
    exit_code = checker.run(output_format=args.format)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
