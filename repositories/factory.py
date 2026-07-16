# repositories/factory.py
from config import DATA_SOURCE
from repositories.base import DataRepository
from repositories.json_repository import JsonRepository
from repositories.sqlite_repository import SQLiteRepository

class RepositoryFactory:
    """Factory لتوفير التطبيق المناسب لـ DataRepository حسب الإعدادات"""
    
    _instance = None  # لتخزين النسخة المفردة (Singleton) إن أردت
    
    @staticmethod
    def get_repository() -> DataRepository:
        """
        إرجاع نسخة من DataRepository بناءً على DATA_SOURCE في config.py
        """
        if DATA_SOURCE == 'sqlite':
            return SQLiteRepository()
        else:
            # افتراضياً JSON
            return JsonRepository()