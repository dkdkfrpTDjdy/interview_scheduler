import threading
import time
from datetime import datetime, timedelta

class SyncManager:
    def __init__(self, db_manager):
        self.db = db_manager
        self.last_sync = datetime.now()
        self.sync_interval = timedelta(minutes=1)  # 1분마다 동기화
        
    def start_background_sync(self):
        """백그라운드 동기화 시작"""
        def sync_loop():
            while True:
                try:
                    if datetime.now() - self.last_sync > self.sync_interval:
                        self.force_sync()
                        self.last_sync = datetime.now()
                    time.sleep(30)  # 30초마다 체크
                except Exception as e:
                    logger.error(f"백그라운드 동기화 오류: {e}")
                    time.sleep(60)  # 오류 시 1분 대기
        
        thread = threading.Thread(target=sync_loop, daemon=True)
        thread.start()
    
    def force_sync(self):
        """강제 동기화"""
        try:
            # 캐시 클리어
            if hasattr(st, 'cache_data'):
                st.cache_data.clear()
            
            # 구글 시트 새로고침
            self.db.force_refresh()
            
            return True
        except Exception as e:
            logger.error(f"강제 동기화 실패: {e}")
            return False

# app.py에 추가
sync_manager = SyncManager(db)
sync_manager.start_background_sync()