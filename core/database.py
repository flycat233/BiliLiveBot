# -*- coding: utf-8 -*-
"""
数据库模块
提供SQLite数据持久化功能
"""

import sqlite3
import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from core.logger import get_logger

logger = get_logger("database")


class Database:
    """数据库管理器"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, db_path: str = "./data/database.db"):
        if not hasattr(self, 'initialized'):
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.initialized = True
            self._init_database()
    
    @contextmanager
    def get_connection(self):
        """获取数据库连接（上下文管理器）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            conn.close()
    
    def _init_database(self):
        """初始化数据库表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 用户分析表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_name TEXT NOT NULL,
                    uid INTEGER,
                    danmaku_count INTEGER DEFAULT 0,
                    gift_count INTEGER DEFAULT 0,
                    gift_value REAL DEFAULT 0,
                    last_seen TIMESTAMP,
                    first_seen TIMESTAMP,
                    interests TEXT,
                    sentiment_score REAL DEFAULT 0,
                    activity_level TEXT DEFAULT 'low',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_name 
                ON user_analytics(user_name)
            """)
            
            # 弹幕记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS danmaku_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id INTEGER,
                    user_name TEXT NOT NULL,
                    uid INTEGER,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    medal_name TEXT,
                    medal_level INTEGER,
                    is_admin BOOLEAN DEFAULT 0,
                    is_vip BOOLEAN DEFAULT 0
                )
            """)
            
            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_danmaku_timestamp 
                ON danmaku_records(timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_danmaku_room 
                ON danmaku_records(room_id)
            """)
            
            # 礼物记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS gift_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id INTEGER,
                    user_name TEXT NOT NULL,
                    uid INTEGER,
                    gift_name TEXT NOT NULL,
                    gift_id INTEGER,
                    num INTEGER DEFAULT 1,
                    price REAL DEFAULT 0,
                    total_coin REAL DEFAULT 0,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 签到记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS checkin_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_name TEXT NOT NULL,
                    uid INTEGER,
                    checkin_date DATE NOT NULL,
                    continuous_days INTEGER DEFAULT 1,
                    total_days INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_name, checkin_date)
                )
            """)
            
            # 抽签记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lottery_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_name TEXT NOT NULL,
                    uid INTEGER,
                    result TEXT NOT NULL,
                    lottery_date DATE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 性能监控表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    metric_unit TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 错误日志表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    stack_trace TEXT,
                    context TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            logger.info("数据库初始化完成")
    
    # ==================== 用户分析相关 ====================
    
    def save_user_analytics(self, user_data: Dict):
        """保存用户分析数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 检查用户是否存在
            cursor.execute(
                "SELECT id FROM user_analytics WHERE user_name = ?",
                (user_data['user_name'],)
            )
            existing = cursor.fetchone()
            
            if existing:
                # 更新现有记录
                cursor.execute("""
                    UPDATE user_analytics 
                    SET danmaku_count = ?,
                        gift_count = ?,
                        gift_value = ?,
                        last_seen = ?,
                        interests = ?,
                        sentiment_score = ?,
                        activity_level = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE user_name = ?
                """, (
                    user_data.get('danmaku_count', 0),
                    user_data.get('gift_count', 0),
                    user_data.get('gift_value', 0),
                    user_data.get('last_seen'),
                    json.dumps(user_data.get('interests', []), ensure_ascii=False),
                    user_data.get('sentiment_score', 0),
                    user_data.get('activity_level', 'low'),
                    user_data['user_name']
                ))
            else:
                # 插入新记录
                cursor.execute("""
                    INSERT INTO user_analytics 
                    (user_name, uid, danmaku_count, gift_count, gift_value, 
                     last_seen, first_seen, interests, sentiment_score, activity_level)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    user_data['user_name'],
                    user_data.get('uid'),
                    user_data.get('danmaku_count', 0),
                    user_data.get('gift_count', 0),
                    user_data.get('gift_value', 0),
                    user_data.get('last_seen'),
                    user_data.get('first_seen'),
                    json.dumps(user_data.get('interests', []), ensure_ascii=False),
                    user_data.get('sentiment_score', 0),
                    user_data.get('activity_level', 'low')
                ))
    
    def get_user_analytics(self, user_name: str) -> Optional[Dict]:
        """获取用户分析数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_analytics WHERE user_name = ?",
                (user_name,)
            )
            row = cursor.fetchone()
            
            if row:
                data = dict(row)
                if data.get('interests'):
                    data['interests'] = json.loads(data['interests'])
                return data
            return None
    
    def get_all_users_analytics(self, limit: int = 100) -> List[Dict]:
        """获取所有用户分析数据"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM user_analytics ORDER BY last_seen DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            
            result = []
            for row in rows:
                data = dict(row)
                if data.get('interests'):
                    data['interests'] = json.loads(data['interests'])
                result.append(data)
            
            return result
    
    # ==================== 弹幕记录相关 ====================
    
    def save_danmaku(self, danmaku_data: Dict):
        """保存弹幕记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO danmaku_records 
                (room_id, user_name, uid, content, medal_name, medal_level, 
                 is_admin, is_vip)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                danmaku_data.get('room_id'),
                danmaku_data['user']['uname'],
                danmaku_data['user'].get('uid'),
                danmaku_data['content'],
                danmaku_data.get('medal', {}).get('name') if danmaku_data.get('medal') else None,
                danmaku_data.get('medal', {}).get('level') if danmaku_data.get('medal') else None,
                danmaku_data['user'].get('is_admin', False),
                danmaku_data['user'].get('is_vip', False)
            ))
    
    def get_recent_danmaku(self, room_id: Optional[int] = None, 
                          limit: int = 100) -> List[Dict]:
        """获取最近的弹幕记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            if room_id:
                cursor.execute("""
                    SELECT * FROM danmaku_records 
                    WHERE room_id = ?
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (room_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM danmaku_records 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== 礼物记录相关 ====================
    
    def save_gift(self, gift_data: Dict):
        """保存礼物记录"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO gift_records 
                (room_id, user_name, uid, gift_name, gift_id, num, price, total_coin)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                gift_data.get('room_id'),
                gift_data['user']['uname'],
                gift_data['user'].get('uid'),
                gift_data['gift_name'],
                gift_data.get('gift_id'),
                gift_data.get('num', 1),
                gift_data.get('price', 0),
                gift_data.get('total_coin', 0)
            ))
    
    # ==================== 签到抽签相关 ====================
    
    def save_checkin(self, user_name: str, uid: Optional[int] = None) -> Dict:
        """保存签到记录"""
        today = datetime.now().date()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 检查今天是否已签到
            cursor.execute("""
                SELECT * FROM checkin_records 
                WHERE user_name = ? AND checkin_date = ?
            """, (user_name, today))
            
            if cursor.fetchone():
                return {"success": False, "message": "今天已经签到过了"}
            
            # 获取最近一次签到
            cursor.execute("""
                SELECT * FROM checkin_records 
                WHERE user_name = ?
                ORDER BY checkin_date DESC 
                LIMIT 1
            """, (user_name,))
            
            last_checkin = cursor.fetchone()
            
            continuous_days = 1
            total_days = 1
            
            if last_checkin:
                last_date = datetime.strptime(last_checkin['checkin_date'], '%Y-%m-%d').date()
                total_days = last_checkin['total_days'] + 1
                
                # 检查是否连续签到
                if (today - last_date).days == 1:
                    continuous_days = last_checkin['continuous_days'] + 1
            
            # 插入新签到记录
            cursor.execute("""
                INSERT INTO checkin_records 
                (user_name, uid, checkin_date, continuous_days, total_days)
                VALUES (?, ?, ?, ?, ?)
            """, (user_name, uid, today, continuous_days, total_days))
            
            return {
                "success": True,
                "continuous_days": continuous_days,
                "total_days": total_days
            }
    
    def save_lottery(self, user_name: str, uid: Optional[int], result: str):
        """保存抽签记录"""
        today = datetime.now().date()
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO lottery_records 
                (user_name, uid, result, lottery_date)
                VALUES (?, ?, ?, ?)
            """, (user_name, uid, result, today))
    
    # ==================== 性能监控相关 ====================
    
    def save_metric(self, metric_name: str, metric_value: float, 
                   metric_unit: str = ""):
        """保存性能指标"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO performance_metrics 
                (metric_name, metric_value, metric_unit)
                VALUES (?, ?, ?)
            """, (metric_name, metric_value, metric_unit))
    
    def get_metrics(self, metric_name: str, hours: int = 24) -> List[Dict]:
        """获取性能指标"""
        since = datetime.now() - timedelta(hours=hours)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM performance_metrics 
                WHERE metric_name = ? AND timestamp >= ?
                ORDER BY timestamp DESC
            """, (metric_name, since))
            
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== 错误日志相关 ====================
    
    def save_error(self, error_type: str, error_message: str, 
                  stack_trace: str = "", context: str = ""):
        """保存错误日志"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO error_logs 
                (error_type, error_message, stack_trace, context)
                VALUES (?, ?, ?, ?)
            """, (error_type, error_message, stack_trace, context))
    
    def get_recent_errors(self, limit: int = 100) -> List[Dict]:
        """获取最近的错误日志"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM error_logs 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,))
            
            return [dict(row) for row in cursor.fetchall()]
    
    # ==================== 数据清理相关 ====================
    
    def clean_old_data(self, days: int = 30):
        """清理旧数据"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # 清理旧弹幕记录
            cursor.execute("""
                DELETE FROM danmaku_records 
                WHERE timestamp < ?
            """, (cutoff_date,))
            danmaku_deleted = cursor.rowcount
            
            # 清理旧礼物记录
            cursor.execute("""
                DELETE FROM gift_records 
                WHERE timestamp < ?
            """, (cutoff_date,))
            gift_deleted = cursor.rowcount
            
            # 清理旧性能指标
            cursor.execute("""
                DELETE FROM performance_metrics 
                WHERE timestamp < ?
            """, (cutoff_date,))
            metrics_deleted = cursor.rowcount
            
            # 清理旧错误日志
            cursor.execute("""
                DELETE FROM error_logs 
                WHERE timestamp < ?
            """, (cutoff_date,))
            errors_deleted = cursor.rowcount
            
            logger.info(f"清理完成: 弹幕{danmaku_deleted}条, 礼物{gift_deleted}条, "
                       f"指标{metrics_deleted}条, 错误{errors_deleted}条")
    
    # ==================== 数据备份相关 ====================
    
    def backup(self, backup_dir: str = "./data/backups"):
        """备份数据库"""
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_path / f"database_backup_{timestamp}.db"
        
        try:
            shutil.copy2(self.db_path, backup_file)
            logger.info(f"数据库备份成功: {backup_file}")
            
            # 清理旧备份（保留最近10个）
            backups = sorted(backup_path.glob("database_backup_*.db"))
            if len(backups) > 10:
                for old_backup in backups[:-10]:
                    old_backup.unlink()
                    logger.info(f"删除旧备份: {old_backup}")
            
            return True
        except Exception as e:
            logger.error(f"数据库备份失败: {e}")
            return False


# 全局数据库实例
db = Database()
