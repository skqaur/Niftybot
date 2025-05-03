import time
import logging
from functools import wraps

logger = logging.getLogger('app.utils')

def retry(max_attempts=3, delay=1):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                    if attempt < max_attempts - 1:
                        time.sleep(delay)
            logger.error(f"All {max_attempts} attempts failed")
            raise last_exception
        return wrapper
    return decorator