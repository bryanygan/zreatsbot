"""
Bot Monitor - Tracks bot state, uptime, and metrics
"""
import time
import psutil
import os
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import json

class BotMonitor:
    """Singleton class to monitor bot state and metrics"""

    _instance = None
    _start_time: float = None
    _last_command: Optional[Dict[str, Any]] = None
    _restart_requested: bool = False
    _restart_reason: str = ""
    _process = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Initialize monitor state"""
        self._start_time = time.time()
        self._last_command = None
        self._restart_requested = False
        self._restart_reason = ""
        self._process = psutil.Process(os.getpid())

    @property
    def uptime_seconds(self) -> float:
        """Get bot uptime in seconds"""
        return time.time() - self._start_time

    @property
    def uptime_formatted(self) -> str:
        """Get formatted uptime string"""
        uptime = self.uptime_seconds
        days = int(uptime // 86400)
        hours = int((uptime % 86400) // 3600)
        minutes = int((uptime % 3600) // 60)
        seconds = int(uptime % 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")

        return " ".join(parts)

    @property
    def start_time_iso(self) -> str:
        """Get bot start time in ISO format"""
        return datetime.fromtimestamp(self._start_time).isoformat()

    def record_command(self, command_type: str, user: str, channel: str, **kwargs):
        """Record a command execution"""
        self._last_command = {
            "type": command_type,
            "user": user,
            "channel": channel,
            "timestamp": datetime.now().isoformat(),
            "additional_data": kwargs
        }

    def get_last_command(self) -> Optional[Dict[str, Any]]:
        """Get the last command executed"""
        return self._last_command

    def request_restart(self, reason: str = "Manual restart"):
        """Request a bot restart"""
        self._restart_requested = True
        self._restart_reason = reason

    def is_restart_requested(self) -> bool:
        """Check if restart was requested"""
        return self._restart_requested

    def get_restart_reason(self) -> str:
        """Get restart reason"""
        return self._restart_reason

    def clear_restart_request(self):
        """Clear restart request flag"""
        self._restart_requested = False
        self._restart_reason = ""

    def get_system_metrics(self) -> Dict[str, Any]:
        """Get system resource metrics"""
        try:
            cpu_percent = self._process.cpu_percent(interval=0.1)
            memory_info = self._process.memory_info()

            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
                "threads": self._process.num_threads(),
                "open_files": len(self._process.open_files()) if hasattr(self._process, 'open_files') else 0
            }
        except Exception as e:
            return {
                "error": str(e),
                "cpu_percent": 0,
                "memory_mb": 0,
                "threads": 0,
                "open_files": 0
            }

    def get_full_status(self) -> Dict[str, Any]:
        """Get complete bot status"""
        return {
            "status": "running",
            "uptime": {
                "seconds": round(self.uptime_seconds, 2),
                "formatted": self.uptime_formatted,
                "start_time": self.start_time_iso
            },
            "last_command": self._last_command,
            "system": self.get_system_metrics(),
            "restart_pending": self._restart_requested,
            "restart_reason": self._restart_reason
        }


# Global instance
_monitor = BotMonitor()

def get_monitor() -> BotMonitor:
    """Get the global monitor instance"""
    return _monitor
