import time
import os
from datetime import datetime
from pymongo import ASCENDING
from config import Config
from database import get_db, get_mongo_client
from utils import parse_log_line

def save_position(filename, pos):
    try:
        with open(Config.POS_FILE_COLLECTOR, 'w') as f:
            f.write(str(pos))
    except:
        pass

def load_position(filename):
    if os.path.exists(Config.POS_FILE_COLLECTOR):
        try:
            with open(Config.POS_FILE_COLLECTOR, 'r') as f:
                return int(f.read().strip())
        except:
            return 0
    return 0

def process_logs(collection, start_pos, batch_size=5000):
    pos = start_pos
    cnt = 0
    batch = []
    try:
        if not os.path.exists(Config.LOG_PATH):
            return pos, 0
            
        with open(Config.LOG_PATH, 'r', errors='ignore') as f:
            f.seek(pos)
            while True:
                line = f.readline()
                if not line:
                    break
                parsed = parse_log_line(line.strip())
                if parsed:
                    batch.append(parsed)
                    if len(batch) >= batch_size:
                        try:
                            collection.insert_many(batch, ordered=False)
                            cnt += len(batch)
                        except Exception as e:
                            if hasattr(e, 'details') and 'writeErrors' in e.details:
                                cnt += len(batch) - len(e.details['writeErrors'])
                        batch = []
                pos = f.tell()
            
            if batch:
                try:
                    collection.insert_many(batch, ordered=False)
                    cnt += len(batch)
                except Exception as e:
                    if hasattr(e, 'details') and 'writeErrors' in e.details:
                        cnt += len(batch) - len(e.details['writeErrors'])
    except Exception as e:
        print(f"Error processing file: {e}")
    return pos, cnt

if __name__ == '__main__':
    collection = get_db()
    
    # Ensure indexes
    try:
        collection.create_index([('time', ASCENDING)], background=True)
        collection.create_index([('ip', ASCENDING)], background=True)
    except:
        pass
    
    print(f'Starting log collector...')
    print(f'Reading from: {Config.LOG_PATH}')
    print(f'Writing to MongoDB: {Config.MONGO_HOST}:{Config.MONGO_PORT}/{Config.MONGO_DB}.{Config.MONGO_COLLECTION}')
    
    if not os.path.exists(Config.LOG_PATH):
        print(f'Warning: Log file {Config.LOG_PATH} does not exist. Waiting...')
        while not os.path.exists(Config.LOG_PATH):
            time.sleep(5)
    
    current_position = load_position(Config.LOG_PATH)
    print(f'Starting from position: {current_position}')
    
    while True:
        try:
            if os.path.exists(Config.LOG_PATH):
                file_size = os.path.getsize(Config.LOG_PATH)
                if file_size < current_position:
                    print('Log file rotated detected, resetting position to 0')
                    current_position = 0
                
                new_position, new_count = process_logs(collection, current_position)
                
                if new_position > current_position:
                    if new_count > 0:
                        print(f'✓ Inserted {new_count} new entries at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
                    current_position = new_position
                    save_position(Config.LOG_PATH, current_position)
            
            time.sleep(Config.READ_INTERVAL)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f'Error in main loop: {e}')
            time.sleep(Config.READ_INTERVAL)
