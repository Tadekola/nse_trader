import redis
from datetime import timedelta

class CacheManager:
    """Redis-based caching system for market data"""
    
    def __init__(self):
        self.redis = redis.Redis(
            host='host.docker.internal',
            port=6379,
            db=0,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_keepalive=True
        )
    
    def get_cached_data(self, key):
        return self.redis.get(key)
    
    def set_cached_data(self, key, value, ttl=60):
        self.redis.setex(key, timedelta(seconds=ttl), value)
