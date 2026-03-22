#!/usr/bin/env python3
"""
系统健康检查技能 - 主程序
"""

import json
import sys
import time
from datetime import datetime
from typing import Dict, List, Any
import os

# 添加当前目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import psutil
except ImportError:
    print("错误: 需要安装psutil库")
    print("请运行: pip3 install psutil")
    sys.exit(1)

from utils import (
    color_print, get_thresholds, check_threshold,
    format_bytes, format_percent, AlertLevel
)

class SystemHealthChecker:
    """系统健康检查器"""
    
    def __init__(self):
        self.thresholds = get_thresholds()
        self.alerts = []
        self.start_time = time.time()
        
    def check_cpu(self) -> Dict[str, Any]:
        """检查CPU状态"""
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
            'per_cpu': psutil.cpu_percent(interval=1, percpu=True)
        }
        
        # 检查阈值
        level = check_threshold(cpu_percent, self.thresholds['cpu']['usage'])
        if level != AlertLevel.INFO:
            result['status'] = level.value
            self.alerts.append({
                'component': 'CPU',
                'level': level.value,
                'message': f"CPU使用率 {cpu_percent}% 超过阈值 {self.thresholds['cpu']['usage']['warning']}%"
            })
        
        return result
    
    def check_memory(self) -> Dict[str, Any]:
        """检查内存状态"""
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
        level = check_threshold(mem.percent, self.thresholds['memory']['usage'])
        if level != AlertLevel.INFO:
            result['status'] = level.value
            self.alerts.append({
                'component': 'Memory',
                'level': level.value,
                'message': f"内存使用率 {mem.percent}% 超过阈值 {self.thresholds['memory']['usage']['warning']}%"
            })
        
        return result
    
    def check_disk(self) -> Dict[str, Any]:
        """检查磁盘状态"""
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
                level = check_threshold(usage_percent, self.thresholds['disk']['usage'])
                if level != AlertLevel.INFO:
                    partition_info['status'] = level.value
                    issues.append({
                        'component': f"Disk {partition.mountpoint}",
                        'level': level.value,
                        'message': f"磁盘使用率 {usage_percent}% 超过阈值 {self.thresholds['disk']['usage']['warning']}%"
                    })
                
                partitions.append(partition_info)
                
            except PermissionError:
                continue
        
        if issues:
            self.alerts.extend(issues)
        
        return {
            'status': 'OK' if not issues else 'WARNING',
            'partitions': partitions
        }
    
    def check_network(self) -> Dict[str, Any]:
        """检查网络状态"""
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
    
    def check_processes(self) -> Dict[str, Any]:
        """检查关键进程"""
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
    
    def generate_report(self, results: Dict[str, Any]) -> str:
        """生成人类可读的报告"""
        duration = time.time() - self.start_time
        
        report = []
        report.append("=" * 60)
        report.append(color_print("系统健康检查报告", "bold"))
        report.append(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"检查耗时: {duration:.2f} 秒")
        report.append(f"主机名: {os.uname().nodename}")
        report.append("=" * 60)
        
        # CPU信息
        report.append(f"\n{color_print('CPU状态', 'cyan')}")
        cpu = results['cpu']
        report.append(f"  使用率: {cpu['usage_percent']}%")
        report.append(f"  核心数: {cpu['core_count']}")
        load = cpu['load_average']
        report.append(f"  负载: 1m={load['1min']:.2f}, 5m={load['5min']:.2f}, 15m={load['15min']:.2f}")
        
        # 内存信息
        report.append(f"\n{color_print('内存状态', 'cyan')}")
        mem = results['memory']['memory']
        report.append(f"  总计: {mem['total']}")
        report.append(f"  已用: {mem['used']} ({mem['used_formatted']})")
        report.append(f"  可用: {mem['available']}")
        
        # 磁盘信息
        report.append(f"\n{color_print('磁盘状态', 'cyan')}")
        for disk in results['disk']['partitions']:
            status_color = "green" if disk['status'] == 'OK' else "red"
            report.append(f"  {disk['mountpoint']}: {disk['percent_formatted']} "
                         f"({disk['used']}/{disk['total']}) "
                         f"{color_print(disk['status'], status_color)}")
        
        # 告警信息
        if self.alerts:
            report.append(f"\n{color_print('告警信息', 'yellow')}")
            for alert in self.alerts:
                level_color = {
                    'WARNING': 'yellow',
                    'CRITICAL': 'red'
                }.get(alert['level'], 'white')
                report.append(f"  [{color_print(alert['level'], level_color)}] "
                            f"{alert['component']}: {alert['message']}")
        else:
            report.append(f"\n{color_print('✓ 所有检查项均正常', 'green')}")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)
    
    def run(self, output_format: str = 'text') -> None:
        """运行完整健康检查"""
        print(color_print("正在执行系统健康检查...", "cyan"))
        
        results = {
            'cpu': self.check_cpu(),
            'memory': self.check_memory(),
            'disk': self.check_disk(),
            'network': self.check_network(),
            'processes': self.check_processes(),
            'timestamp': datetime.now().isoformat()
        }
        
        if output_format == 'json':
            print(json.dumps(results, indent=2, ensure_ascii=False))
        else:
            report = self.generate_report(results)
            print(report)
        
        # 返回状态码
        has_critical = any(alert['level'] == 'CRITICAL' for alert in self.alerts)
        sys.exit(2 if has_critical else (1 if self.alerts else 0))


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
    checker.run(output_format=args.format)


if __name__ == '__main__':
    main()
