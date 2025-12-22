# collector.py - Optimized version
import time
import os
import re
import json
from pymongo import MongoClient, ASCENDING
from dateutil import parser as dateparser
from datetime import datetime

# MongoDB connection
MONGO_HOST = os.getenv('MONGO_HOST', 'mongodb')
MONGO_PORT = int(os.getenv('MONGO_PORT', 27017))
MONGO_DB = os.getenv('MONGO_DB', 'logdb')
MONGO_COLLECTION = os.getenv('MONGO_COLLECTION', 'logs')

BASE_DIR = '/app/logs'
LOG_PATH = os.getenv('LOG_PATH', os.path.join(BASE_DIR, 'access.log'))
READ_INTERVAL = int(os.getenv('READ_INTERVAL', '30'))  # 30 seconds

# Regex cho Common/Combined Log Format
LOG_PATTERN = re.compile(
    r'(?P<ip>\S+) '
    r'(?P<ident>\S+) '
    r'(?P<user>\S+) '
    r'\[(?P<time>[^\]]+)\] '
    r'"(?P<request>[^"]*)" '
    r'(?P<status>\d{3}) '
    r'(?P<size>\S+)'
    r'( "(?P<referer>[^"]*)")?'
    r'( "(?P<agent>[^"]*)")?'
)

# ===== TỐI ƯU 1: Connection Pooling =====
_mongo_client = None

def get_mongo_client():
    """Get or create MongoDB client with connection pooling"""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(
            MONGO_HOST, 
            MONGO_PORT,
            maxPoolSize=50,
            minPoolSize=10,
            maxIdleTimeMS=45000
        )
    return _mongo_client

def get_db():
    """Get MongoDB collection"""
    client = get_mongo_client()
    db = client[MONGO_DB]
    return db[MONGO_COLLECTION]

def get_position_db():
    """Get MongoDB collection for storing file positions"""
    client = get_mongo_client()
    db = client[MONGO_DB]
    return db['file_positions']

def save_position(file_path, position):
    """Lưu vị trí đã đọc vào MongoDB"""
    position_collection = get_position_db()
    position_collection.update_one(
        {'file_path': file_path},
        {
            '$set': {
                'file_path': file_path,
                'position': position,
                'updated_at': datetime.utcnow()
            }
        },
        upsert=True
    )

def load_position(file_path):
    """Load vị trí đã đọc từ MongoDB"""
    position_collection = get_position_db()
    doc = position_collection.find_one({'file_path': file_path})
    if doc:
        return doc.get('position', 0)
    return 0

def parse_log_line(line):
    """Parse một dòng log"""
    if not line.strip():
        return None
    m = LOG_PATTERN.match(line)
    if not m:
        return None
    d = m.groupdict()
    method, path, proto = (None, None, None)
    if d.get('request'):
        parts = d['request'].split()
        if len(parts) == 3:
            method, path, proto = parts
        elif len(parts) == 2:
            method, path = parts
    try:
        dt = dateparser.parse(d['time'].replace(':', ' ', 1))
    except Exception:
        dt = datetime.utcnow()
    size = None if d['size'] == '-' else int(d['size'])
    return {
        'ip': d.get('ip'),
        'user': d.get('user'),
        'time': dt if dt else datetime.utcnow(),
        'method': method,
        'path': path,
        'proto': proto,
        'status': int(d.get('status')) if d.get('status') else None,
        'size': size,
        'referer': d.get('referer') if d.get('referer') else None,
        'agent': d.get('agent') if d.get('agent') else None
    }

def read_new_lines(file_path, start_position):
    """Đọc các dòng mới từ vị trí start_position"""
    new_lines = []
    current_position = start_position
    
    try:
        with open(file_path, 'r', errors='ignore') as f:
            f.seek(start_position)
            while True:
                line = f.readline()
                if not line:
                    break
                new_lines.append(line.strip())
                current_position = f.tell()
    except Exception as e:
        print(f"Error reading file: {e}")
    
    return new_lines, current_position

if __name__ == '__main__':
    collection = get_db()
    
    # ===== TỐI ƯU 2: Tạo unique index để tránh duplicate =====
    try:
        collection.create_index(
            [('ip', ASCENDING), ('path', ASCENDING), ('time', ASCENDING)], 
            unique=True, 
            background=True
        )
        print("✓ Unique index created")
    except:
        pass  # Index already exists
    
    print(f'Starting log collector...')
    print(f'Reading from: {LOG_PATH}')
    print(f'Writing to MongoDB: {MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}.{MONGO_COLLECTION}')
    print(f'Reading interval: {READ_INTERVAL} seconds')
    
    if not os.path.exists(LOG_PATH):
        print(f'Warning: Log file {LOG_PATH} does not exist. Waiting...')
        while not os.path.exists(LOG_PATH):
            time.sleep(5)
    
    current_position = load_position(LOG_PATH)
    print(f'Starting from position: {current_position}')
    
    # Đọc lần đầu nếu chưa có position
    if current_position == 0:
        print('First run: Reading entire file and storing to database...')
        count = 0
        batch = []
        batch_size = 500  # Increased batch size
        
        try:
            with open(LOG_PATH, 'r', errors='ignore') as f:
                for line in f:
                    parsed = parse_log_line(line.strip())
                    if parsed:
                        batch.append(parsed)
                        
                        if len(batch) >= batch_size:
                            try:
                                collection.insert_many(batch, ordered=False)
                                count += len(batch)
                                print(f'  Inserted {count} entries...')
                            except Exception as e:
                                # Count successful inserts even with duplicates
                                if hasattr(e, 'details') and 'writeErrors' in e.details:
                                    successful = len(batch) - len(e.details['writeErrors'])
                                    count += successful
                                    print(f'  Inserted {count} entries (skipped duplicates)...')
                            batch = []
                    
                    current_position = f.tell()
                
                # Insert remaining
                if batch:
                    try:
                        collection.insert_many(batch, ordered=False)
                        count += len(batch)
                    except Exception as e:
                        if hasattr(e, 'details') and 'writeErrors' in e.details:
                            count += len(batch) - len(e.details['writeErrors'])
            
            save_position(LOG_PATH, current_position)
            print(f'✓ Initial read complete: {count} entries stored')
        except Exception as e:
            print(f'Error during initial read: {e}')
    
    # ===== Main loop - đọc incremental =====
    print('Starting incremental read loop...')
    error_count = 0
    max_errors = 10
    
    while True:
        try:
            # Kiểm tra file có bị rotate không
            if os.path.exists(LOG_PATH):
                file_size = os.path.getsize(LOG_PATH)
                if file_size < current_position:
                    print('Log file rotated detected, resetting position to 0')
                    current_position = 0
                
                # Đọc các dòng mới
                new_lines, new_position = read_new_lines(LOG_PATH, current_position)
                
                if new_lines:
                    batch = []
                    for line in new_lines:
                        parsed = parse_log_line(line)
                        if parsed:
                            batch.append(parsed)
                    
                    if batch:
                        try:
                            collection.insert_many(batch, ordered=False)
                            print(f'✓ Inserted {len(batch)} new entries at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
                        except Exception as e:
                            # Handle duplicates gracefully
                            if hasattr(e, 'details') and 'writeErrors' in e.details:
                                successful = len(batch) - len(e.details['writeErrors'])
                                if successful > 0:
                                    print(f'✓ Inserted {successful} new entries (skipped {len(e.details["writeErrors"])} duplicates)')
                            else:
                                print(f'Error inserting batch: {e}')
                    
                    # Update position
                    current_position = new_position
                    save_position(LOG_PATH, current_position)
                
                error_count = 0  # Reset error count on success
            else:
                print(f'Warning: Log file {LOG_PATH} does not exist')
                error_count += 1
            
            time.sleep(READ_INTERVAL)
            
        except KeyboardInterrupt:
            print('\nStopping collector...')
            break
        except Exception as e:
            error_count += 1
            print(f'Error in main loop (count: {error_count}/{max_errors}): {e}')
            if error_count >= max_errors:
                print(f'Too many errors, stopping collector')
                break
            time.sleep(READ_INTERVAL)
    
    print('Collector stopped')
