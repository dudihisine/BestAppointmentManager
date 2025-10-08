#!/usr/bin/env python3
"""
Background worker for processing appointment reminders and notifications.
"""
import os
import sys
import logging
from rq import Worker, Connection
from redis import Redis

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Start the background worker."""
    try:
        # Connect to Redis
        redis_conn = Redis(host='localhost', port=6379, db=0)
        
        # Create worker for different queues
        queues = ['appointment_reminders', 'waitlist_notifications', 'daily_reports']
        
        logger.info("Starting background worker...")
        logger.info(f"Listening to queues: {', '.join(queues)}")
        
        with Connection(redis_conn):
            worker = Worker(queues)
            worker.work()
            
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
