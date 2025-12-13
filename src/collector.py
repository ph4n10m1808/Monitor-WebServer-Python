# collector.py
import time
import os
import re
import json
from pymongo import MongoClient
from dateutil import parser as dateparser
from datetime import datetime

# MongoDB connection
MONGO_HOST = os.getenv('MONGO_HOST', 'mongodb')
MONGO_PORT = int(os.getenv('MONGO_PORT', 27017))
MONGO_DB = os.getenv('MONGO_DB', 'logdb')
MONGO_COLLECTION = os.getenv('MONGO_COLLECTION', 'logs')

# Đường dẫn đến access.log trong folder src
# Lấy đường dẫn tuyệt đối của thư mục chứa collector.py (src/)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.getenv('LOG_PATH', os.path.join(BASE_DIR, 'access.log'))
READ_INTERVAL = int(os.getenv('READ_INTERVAL', '30'))  # 30 seconds

# Regex cho Common/Combined Log Format
LOG_PATTERN = re.compile(
    r'(?P<ip>\S+) '  # IP
    r'(?P<ident>\S+) '  # ident
    r'(?P<user>\S+) '  # user
    r'\[(?P<time>[^\]]+)\] '  # time
    r'"(?P<request>[^"]*)" '  # request
    r'(?P<status>\d{3}) '  # status
    r'(?P<size>\S+)'  # size
    r'( "(?P<referer>[^"]*)")?'
    r'( "(?P<agent>[^"]*)")?'
)

def get_db():
    """Get MongoDB collection"""
    client = MongoClient(MONGO_HOST, MONGO_PORT)
    db = client[MONGO_DB]
    return db[MONGO_COLLECTION]

def get_position_db():
    """Get MongoDB collection for storing file positions"""
    client = MongoClient(MONGO_HOST, MONGO_PORT)
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
    # split request
    method, path, proto = (None, None, None)
    if d.get('request'):
        parts = d['request'].split()
        if len(parts) == 3:
            method, path, proto = parts
        elif len(parts) == 2:
            method, path = parts
    # parse time like: 10/Oct/2000:13:55:36 -0700
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
            # Di chuyển đến vị trí đã đọc
            f.seek(start_position)
            # Đọc tất cả dòng mới
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
    print(f'Starting log collector...')
    print(f'Reading from: {LOG_PATH}')
    print(f'Writing to MongoDB: {MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}.{MONGO_COLLECTION}')
    print(f'Reading interval: {READ_INTERVAL} seconds')
    
    # Đợi file log tồn tại
    if not os.path.exists(LOG_PATH):
        print(f'Warning: Log file {LOG_PATH} does not exist. Waiting...')
        while not os.path.exists(LOG_PATH):
            time.sleep(5)
    
    # Load vị trí đã đọc từ MongoDB
    current_position = load_position(LOG_PATH)
    print(f'Starting from position: {current_position}')
    
    # Đọc lần đầu - đọc toàn bộ file nếu chưa có position hoặc position = 0
    if current_position == 0:
        print('First run: Reading entire file and storing to database...')
        count = 0
        batch = []
        batch_size = 100  # Insert in batches for better performance
        
        try:
            with open(LOG_PATH, 'r', errors='ignore') as f:
                for line in f:
                    parsed = parse_log_line(line.strip())
                    if parsed:
                        batch.append(parsed)
                        count += 1
                        
                        # Insert batch when it reaches batch_size
                        if len(batch) >= batch_size:
                            # Check for duplicates before inserting
                            to_insert = []
                            for entry in batch:
                                existing = collection.find_one({
                                    'ip': entry['ip'],
                                    'path': entry['path'],
                                    'time': entry['time']
                                })
                                if not existing:
                                    to_insert.append(entry)
                            
                            if to_insert:
                                collection.insert_many(to_insert)
                            batch = []
                    
                    current_position = f.tell()
            
            # Insert remaining entries
            if batch:
                to_insert = []
                for entry in batch:
                    existing = collection.find_one({
                        'ip': entry['ip'],
                        'path': entry['path'],
                        'time': entry['time']
                    })
                    if not existing:
                        to_insert.append(entry)
                
                if to_insert:
                    collection.insert_many(to_insert)
            
            print(f'✓ Inserted {count} log entries from initial read into database')
            save_position(LOG_PATH, current_position)
            print(f'✓ Saved position: {current_position} to MongoDB')
        except Exception as e:
            print(f'Error during initial read: {e}')
            import traceback
            traceback.print_exc()
    
    # Vòng lặp đọc log mới mỗi 30s
    print(f'Starting periodic reading every {READ_INTERVAL} seconds...')
    while True:
        try:
            # Kiểm tra file có bị rotate không (file nhỏ hơn vị trí đã đọc)
            if not os.path.exists(LOG_PATH):
                print(f'Log file {LOG_PATH} not found. Waiting...')
                time.sleep(READ_INTERVAL)
                continue
                
            file_size = os.path.getsize(LOG_PATH)
            if file_size < current_position:
                print('Log file rotated, resetting position to 0')
                current_position = 0
            
            # Đọc các dòng mới
            new_lines, new_position = read_new_lines(LOG_PATH, current_position)
            
            if new_lines:
                count = 0
                batch = []
                for line in new_lines:
                    parsed = parse_log_line(line)
                    if parsed:
                        batch.append(parsed)
                
                # Check for duplicates and insert
                to_insert = []
                for entry in batch:
                    existing = collection.find_one({
                        'ip': entry['ip'],
                        'path': entry['path'],
                        'time': entry['time']
                    })
                    if not existing:
                        to_insert.append(entry)
                
                if to_insert:
                    if len(to_insert) == 1:
                        collection.insert_one(to_insert[0])
                    else:
                        collection.insert_many(to_insert)
                    count = len(to_insert)
                
                if count > 0:
                    print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] ✓ Inserted {count} new log entries into database')
                else:
                    print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] No new unique log entries')
                
                current_position = new_position
                save_position(LOG_PATH, current_position)
            else:
                print(f'[{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}] No new log entries in file')
            
        except Exception as e:
            print(f'Error processing logs: {e}')
            import traceback
            traceback.print_exc()
        
        # Đợi 30 giây trước khi đọc lại
        time.sleep(READ_INTERVAL)