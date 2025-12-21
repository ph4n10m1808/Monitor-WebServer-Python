# app.py
from flask import Flask, jsonify, render_template, request
from pymongo import MongoClient
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import os
import re
from bson import ObjectId
from dateutil import parser as dateparser

# MongoDB connection
MONGO_HOST = os.getenv('MONGO_HOST', 'mongodb')
MONGO_PORT = int(os.getenv('MONGO_PORT', 27017))
MONGO_DB = os.getenv('MONGO_DB', 'logdb')
MONGO_COLLECTION = os.getenv('MONGO_COLLECTION', 'logs')

# Đường dẫn đến access.log trong folder src
# Lấy đường dẫn tuyệt đối của thư mục chứa app.py (src/)
# BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = '/app/logs'
LOG_PATH = os.getenv('LOG_PATH', os.path.join(BASE_DIR, 'access.log'))

app = Flask(__name__)

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
    """Get MongoDB connection"""
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
    # """Load vị trí đã đọc từ MongoDB"""
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

def sync_logs_from_file(force_full_read=False):
    """Đọc file log và cập nhật vào database"""
    if not os.path.exists(LOG_PATH):
        return {'success': False, 'message': f'Log file {LOG_PATH} does not exist', 'count': 0}
    
    collection = get_db()
    
    # Nếu force_full_read hoặc chưa có position trong DB, đọc toàn bộ file
    if force_full_read:
        current_position = 0
        print(f"Force full read: Reading entire file {LOG_PATH}...")
    else:
        current_position = load_position(LOG_PATH)
        if current_position == 0:
            print(f"First run: Reading entire file {LOG_PATH}...")
        else:
            # Kiểm tra file có bị rotate không
            file_size = os.path.getsize(LOG_PATH)
            if file_size < current_position:
                current_position = 0
                print("Log file rotated, resetting position to 0")
    
    try:
        count = 0
        batch = []
        batch_size = 100
        
        with open(LOG_PATH, 'r', errors='ignore') as f:
            # Di chuyển đến vị trí đã đọc
            f.seek(current_position)
            
            # Đọc các dòng mới
            for line in f:
                parsed = parse_log_line(line.strip())
                if parsed:
                    batch.append(parsed)
                    
                    # Insert batch when it reaches batch_size
                    if len(batch) >= batch_size:
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
                            count += len(to_insert)
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
                    if len(to_insert) == 1:
                        collection.insert_one(to_insert[0])
                    else:
                        collection.insert_many(to_insert)
                    count += len(to_insert)
        
        # Lưu vị trí mới vào MongoDB
        save_position(LOG_PATH, current_position)
        
        return {
            'success': True,
            'message': f'Synced {count} new log entries',
            'count': count
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'message': f'Error syncing logs: {str(e)}',
            'count': 0
        }

def load_entries(limit=10000, since=None):
    """Load log entries from MongoDB"""
    collection = get_db()
    query = {}
    if since:
        query['time'] = {'$gte': since}
    
    # Sort by time descending and limit
    cursor = collection.find(query).sort('time', -1).limit(limit)
    entries = list(cursor)
    return entries

def serialize_log_entry(entry):
    """Convert MongoDB entry to JSON-serializable format"""
    result = {}
    for key, value in entry.items():
        if key == '_id':
            result[key] = str(value)
        elif isinstance(value, datetime):
            result[key] = value.isoformat()
        elif isinstance(value, ObjectId):
            result[key] = str(value)
        else:
            result[key] = value
    return result

def build_search_query():
    """Build MongoDB query from request parameters"""
    query = {}
    
    # Search by IP (regex for partial match)
    ip = request.args.get('ip', '').strip()
    if ip:
        query['ip'] = {'$regex': ip, '$options': 'i'}
    
    # Search by Ident (regex for partial match)
    ident = request.args.get('ident', '').strip()
    if ident:
        query['ident'] = {'$regex': ident, '$options': 'i'}
    
    # Search by User (regex for partial match)
    user = request.args.get('user', '').strip()
    if user:
        query['user'] = {'$regex': user, '$options': 'i'}
    
    # Search by Path/Request (regex for partial match)
    path = request.args.get('path', '').strip()
    if path:
        query['path'] = {'$regex': path, '$options': 'i'}
    
    # Search by Method (exact match, case insensitive)
    method = request.args.get('method', '').strip()
    if method:
        query['method'] = {'$regex': f'^{re.escape(method)}$', '$options': 'i'}
    
    # Search by Status Code (exact match or range)
    status = request.args.get('status', '').strip()
    if status:
        try:
            query['status'] = int(status)
        except ValueError:
            pass
    
    # Search by Size (range)
    size_min = request.args.get('size_min', '').strip()
    size_max = request.args.get('size_max', '').strip()
    if size_min or size_max:
        size_query = {}
        if size_min:
            try:
                size_query['$gte'] = int(size_min)
            except ValueError:
                pass
        if size_max:
            try:
                size_query['$lte'] = int(size_max)
            except ValueError:
                pass
        if size_query:
            query['size'] = size_query
    
    # Search by Referer (regex for partial match)
    referer = request.args.get('referer', '').strip()
    if referer:
        query['referer'] = {'$regex': referer, '$options': 'i'}
    
    # Search by User Agent (regex for partial match)
    agent = request.args.get('agent', '').strip()
    if agent:
        query['agent'] = {'$regex': agent, '$options': 'i'}
    
    return query

@app.route('/api/sync', methods=['POST', 'GET'])
def api_sync():
    """API để sync logs từ file vào database"""
    force = request.args.get('force', 'false').lower() == 'true'
    result = sync_logs_from_file(force_full_read=force)
    return jsonify(result)

@app.route('/api/logs')
def api_logs():
    """API trả về danh sách log entries với search"""
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 50))
    skip = (page - 1) * limit
    
    collection = get_db()
    
    # Build search query
    search_query = build_search_query()
    
    # Get total count with search
    total = collection.count_documents(search_query)
    
    # Get logs with pagination and search
    cursor = collection.find(search_query).sort('time', -1).skip(skip).limit(limit)
    entries = [serialize_log_entry(e) for e in cursor]
    
    return jsonify({
        'logs': entries,
        'total': total,
        'page': page,
        'limit': limit,
        'pages': (total + limit - 1) // limit if total > 0 else 0,
        'filters': {
            'ip': request.args.get('ip', ''),
            'ident': request.args.get('ident', ''),
            'user': request.args.get('user', ''),
            'path': request.args.get('path', ''),
            'method': request.args.get('method', ''),
            'status': request.args.get('status', ''),
            'size_min': request.args.get('size_min', ''),
            'size_max': request.args.get('size_max', ''),
            'referer': request.args.get('referer', ''),
            'agent': request.args.get('agent', '')
        }
    })

@app.route('/api/stats')
def api_stats():
    """API trả về thống kê log"""
    entries = load_entries()
    now = datetime.utcnow()
    # requests per minute (last 60 minutes)
    rpm = defaultdict(int)
    top_ips = Counter()
    top_paths = Counter()
    status = Counter()

    for e in entries:
        t = e.get('time')
        if not t:
            continue
        try:
            # Handle both string and datetime objects
            if isinstance(t, str):
                dt = datetime.fromisoformat(t)
            elif isinstance(t, datetime):
                dt = t
            else:
                continue
            minute = dt.replace(second=0, microsecond=0)
            rpm[minute.isoformat()] += 1
        except Exception:
            continue
        
        if e.get('ip'):
            top_ips[e['ip']] += 1
        if e.get('path'):
            top_paths[e['path']] += 1
        if e.get('status'):
            status[str(e['status'])] += 1

    # sort rpm by time (last 60 points)
    rpm_items = sorted(rpm.items())
    
    # Lấy timestamp của log mới nhất
    latest_log = entries[0] if entries else None
    latest_time = None
    if latest_log and latest_log.get('time'):
        t = latest_log['time']
        if isinstance(t, datetime):
            latest_time = t.isoformat()
        elif isinstance(t, str):
            latest_time = t
    
    return jsonify({
        'rpm': rpm_items,
        'top_ips': top_ips.most_common(20),
        'top_paths': top_paths.most_common(20),
        'status': status.most_common(),
        'latest_time': latest_time,
        'total_entries': len(entries)
    })

@app.route('/api/stats/since/<timestamp>')
def api_stats_since(timestamp):
    """API trả về thống kê từ một timestamp cụ thể"""
    try:
        since = datetime.fromisoformat(timestamp)
    except:
        since = datetime.utcnow() - timedelta(hours=1)
    
    entries = load_entries(since=since)
    rpm = defaultdict(int)
    top_ips = Counter()
    top_paths = Counter()
    status = Counter()

    for e in entries:
        t = e.get('time')
        if not t:
            continue
        try:
            if isinstance(t, str):
                dt = datetime.fromisoformat(t)
            elif isinstance(t, datetime):
                dt = t
            else:
                continue
            minute = dt.replace(second=0, microsecond=0)
            rpm[minute.isoformat()] += 1
        except Exception:
            continue
        
        if e.get('ip'):
            top_ips[e['ip']] += 1
        if e.get('path'):
            top_paths[e['path']] += 1
        if e.get('status'):
            status[str(e['status'])] += 1

    rpm_items = sorted(rpm.items())
    
    latest_log = entries[0] if entries else None
    latest_time = None
    if latest_log and latest_log.get('time'):
        t = latest_log['time']
        if isinstance(t, datetime):
            latest_time = t.isoformat()
        elif isinstance(t, str):
            latest_time = t
    
    return jsonify({
        'rpm': rpm_items,
        'top_ips': top_ips.most_common(20),
        'top_paths': top_paths.most_common(20),
        'status': status.most_common(),
        'latest_time': latest_time,
        'new_entries': len(entries)
    })

@app.route('/')
def index():
    """Trang chủ - tự động sync logs từ file vào DB lần đầu"""
    # Kiểm tra xem đã sync chưa (dựa vào position trong DB)
    current_position = load_position(LOG_PATH)
    is_first_run = (current_position == 0)
    
    # Sync logs từ file vào database
    sync_result = sync_logs_from_file(force_full_read=is_first_run)
    
    if sync_result['success']:
        if sync_result['count'] > 0:
            print(f"✓ Synced {sync_result['count']} log entries from {LOG_PATH} to database")
        else:
            print(f"✓ No new log entries to sync (already up to date)")
    else:
        print(f"✗ Error syncing logs: {sync_result['message']}")
    
    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)