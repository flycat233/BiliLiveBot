# -*- coding: utf-8 -*-
"""
数据导出模块
提供数据导出功能
"""

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from io import StringIO

from core.logger import get_logger
from core.database import db

logger = get_logger("export")


class DataExporter:
    """数据导出器"""
    
    def __init__(self):
        self.export_dir = Path("./data/exports")
        self.export_dir.mkdir(parents=True, exist_ok=True)
    
    def export_to_json(self, data: List[Dict], filename: str) -> str:
        """
        导出为JSON格式
        
        Args:
            data: 要导出的数据
            filename: 文件名
            
        Returns:
            导出文件路径
        """
        filepath = self.export_dir / f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"数据已导出为JSON: {filepath}")
            return str(filepath)
        
        except Exception as e:
            logger.error(f"导出JSON失败: {e}", exc_info=True)
            raise
    
    def export_to_csv(self, data: List[Dict], filename: str, 
                     fieldnames: Optional[List[str]] = None) -> str:
        """
        导出为CSV格式
        
        Args:
            data: 要导出的数据
            filename: 文件名
            fieldnames: 字段名列表，None则自动从数据中提取
            
        Returns:
            导出文件路径
        """
        if not data:
            raise ValueError("没有数据可导出")
        
        filepath = self.export_dir / f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            # 如果没有指定字段名，从第一条数据中提取
            if fieldnames is None:
                fieldnames = list(data[0].keys())
            
            with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
            
            logger.info(f"数据已导出为CSV: {filepath}")
            return str(filepath)
        
        except Exception as e:
            logger.error(f"导出CSV失败: {e}", exc_info=True)
            raise
    
    def export_user_analytics(self, format: str = 'json') -> str:
        """
        导出用户分析数据
        
        Args:
            format: 导出格式 ('json' 或 'csv')
            
        Returns:
            导出文件路径
        """
        data = db.get_all_users_analytics(limit=10000)
        
        if format == 'json':
            return self.export_to_json(data, 'user_analytics')
        elif format == 'csv':
            return self.export_to_csv(data, 'user_analytics')
        else:
            raise ValueError(f"不支持的格式: {format}")
    
    def export_danmaku_records(self, room_id: Optional[int] = None, 
                               limit: int = 10000, format: str = 'json') -> str:
        """
        导出弹幕记录
        
        Args:
            room_id: 房间ID，None表示所有房间
            limit: 导出数量限制
            format: 导出格式
            
        Returns:
            导出文件路径
        """
        data = db.get_recent_danmaku(room_id, limit)
        
        filename = f'danmaku_records_room{room_id}' if room_id else 'danmaku_records_all'
        
        if format == 'json':
            return self.export_to_json(data, filename)
        elif format == 'csv':
            return self.export_to_csv(data, filename)
        else:
            raise ValueError(f"不支持的格式: {format}")
    
    def export_performance_metrics(self, metric_name: str, hours: int = 24, 
                                   format: str = 'json') -> str:
        """
        导出性能指标
        
        Args:
            metric_name: 指标名称
            hours: 时间范围（小时）
            format: 导出格式
            
        Returns:
            导出文件路径
        """
        data = db.get_metrics(metric_name, hours)
        
        filename = f'metrics_{metric_name}_{hours}h'
        
        if format == 'json':
            return self.export_to_json(data, filename)
        elif format == 'csv':
            return self.export_to_csv(data, filename)
        else:
            raise ValueError(f"不支持的格式: {format}")
    
    def export_error_logs(self, limit: int = 1000, format: str = 'json') -> str:
        """
        导出错误日志
        
        Args:
            limit: 导出数量限制
            format: 导出格式
            
        Returns:
            导出文件路径
        """
        data = db.get_recent_errors(limit)
        
        if format == 'json':
            return self.export_to_json(data, 'error_logs')
        elif format == 'csv':
            return self.export_to_csv(data, 'error_logs')
        else:
            raise ValueError(f"不支持的格式: {format}")
    
    def get_export_list(self) -> List[Dict]:
        """
        获取导出文件列表
        
        Returns:
            文件信息列表
        """
        files = []
        
        for filepath in self.export_dir.glob("*"):
            if filepath.is_file():
                stat = filepath.stat()
                files.append({
                    'filename': filepath.name,
                    'size': stat.st_size,
                    'created_at': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                    'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
        
        # 按修改时间倒序排序
        files.sort(key=lambda x: x['modified_at'], reverse=True)
        
        return files
    
    def delete_export(self, filename: str) -> bool:
        """
        删除导出文件
        
        Args:
            filename: 文件名
            
        Returns:
            是否删除成功
        """
        filepath = self.export_dir / filename
        
        if not filepath.exists():
            return False
        
        try:
            filepath.unlink()
            logger.info(f"删除导出文件: {filename}")
            return True
        except Exception as e:
            logger.error(f"删除导出文件失败: {e}", exc_info=True)
            return False


# 全局导出器实例
exporter = DataExporter()
