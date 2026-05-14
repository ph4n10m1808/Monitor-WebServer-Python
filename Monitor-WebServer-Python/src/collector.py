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
READ_INTERVAL = float(os.getenv('READ_INTERVAL', '1.0'))  # TỐI ƯU: Đổi từ 30s sang 1s để real-time

# ===== FRAMEWORK NHẬN DIỆN TẤN CÔNG (ATTACK DETECTION) =====
ATTACK_SIGNATURES = {
    'SQLi': re.compile(r'(%27)|(\')|(--)|(%23)|(#)|(UNION.*SELECT)|(OR.*=.*)', re.IGNORECASE),
    'XSS': re.compile(r'(%3C|<).*?(script|img|svg|onload|onerror|prompt|alert).*?(%3E|>)', re.IGNORECASE),
    'LFI/PathTraversal': re.compile(r'(\.\./|\.\.\\|%2e%2e%2f|%2e%2e%5c|etc/passwd|windows/win\.ini)', re.IGNORECASE),
    'RCE/CommandInjection': re.compile(r'(%3B|;).*?(wget|curl|bash|sh|nc|netcat|perl|python|php|system|exec)', re.IGNORECASE),
    'SSTI': re.compile(r'(\{\{.*?\}\}|\$\{.*?\}|<%.*?%>)', re.IGNORECASE),
    'Scanner': re.compile(r'(nmap|sqlmap|nikto|dirb|gobuster|wpscan|masscan|zmap)', re.IGNORECASE)
}

def detect_attacks(path, agent, referer):
    """Phân tích payload để phát hiện tấn công"""
    payload = f"{path} {agent} {referer}"
    detected = []
    for attack_type, pattern in ATTACK_SIGNATURES.items():
        if pattern.search(payload):
            detected.append(attack_type)
    return detected

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
        # TỐI ƯU: Sử dụng strptime thay cho dateparser (tăng tốc ~6-10x)
        dt = datetime.strptime(d['time'], "%d/%b/%Y:%H:%M:%S %z")
    except Exception:
        dt = datetime.utcnow()
    size = None if d['size'] == '-' else int(d['size'])
    
    agent = d.get('agent')
    referer = d.get('referer')
    attacks = detect_attacks(path, agent, referer)
    
    return {
        'ip': d.get('ip'),
        'user': d.get('user'),
        'time': dt,
        'method': method,
        'path': path,
        'proto': proto,
        'status': int(d.get('status')) if d.get('status') else None,
        'size': size,
        'referer': referer if referer else None,
        'agent': agent if agent else None,
        'is_attack': len(attacks) > 0,
        'attack_types': attacks
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
    
    # TỐI ƯU 2: Bỏ unique index (ip, path, time) để không làm mất request (Vì A/D flood request rất nhanh trong cùng 1s)
    # Nếu index đã tồn tại từ trước, ta sẽ drop nó để tránh lỗi DuplicateKey
    try:
        collection.drop_index('ip_1_path_1_time_1')
        print("✓ Dropped strict unique index to allow concurrent requests in the same second")
    except:
        pass
        
    try:
        collection.create_index([('time', ASCENDING)], background=True)
        collection.create_index([('ip', ASCENDING)], background=True)
    except:
        pass
    
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
    
    # TỐI ƯU: Đưa logic đọc file vào function riêng, giới hạn batch size, không đọc toàn bộ file vào memory list
    def process_logs(start_pos, batch_size=5000):
        pos = start_pos
        cnt = 0
        batch = []
        try:
            with open(LOG_PATH, 'r', errors='ignore') as f:
                f.seek(pos)
                for line in f:
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

    # Đọc lần đầu nếu chưa có position
    if current_position == 0:
        print('First run: Reading entire file and storing to database...')
        current_position, count = process_logs(0)
        save_position(LOG_PATH, current_position)
        print(f'✓ Initial read complete: {count} entries stored')
    
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
                
                # Đọc các dòng mới, không nạp hết list vào memory
                new_position, new_count = process_logs(current_position)
                
                if new_position > current_position:
                    if new_count > 0:
                        print(f'✓ Inserted {new_count} new entries at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
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
