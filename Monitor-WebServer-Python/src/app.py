# app.py - Optimized version
from flask import Flask, jsonify, render_template, request, session, redirect, url_for, flash
from pymongo import MongoClient, ASCENDING, DESCENDING
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import os
import re
from bson import ObjectId
from dateutil import parser as dateparser
import gzip
import functools
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# MongoDB connection
MONGO_HOST = os.getenv('MONGO_HOST', 'mongodb')
MONGO_PORT = int(os.getenv('MONGO_PORT', 27017))
MONGO_DB = os.getenv('MONGO_DB', 'logdb')
MONGO_COLLECTION = os.getenv('MONGO_COLLECTION', 'logs')

BASE_DIR = '/app/logs'
LOG_PATH = os.getenv('LOG_PATH', os.path.join(BASE_DIR, 'access.log'))

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')

# ===== TỐI ƯU: GZIP Compression cho API responses =====
def gzipped(f):
    """Decorator để tự động compress responses nếu client support"""
    @functools.wraps(f)
    def view_func(*args, **kwargs):
        @functools.wraps(f)
        def gzip_wrapper(*args, **kwargs):
            response = f(*args, **kwargs)
            
            # Check if client accepts gzip
            accept_encoding = request.headers.get('Accept-Encoding', '')
            if 'gzip' not in accept_encoding.lower():
                return response
            
            # Get response data
            if isinstance(response, tuple):
                data, status_code = response
            else:
                data = response
                status_code = 200
            
            # Compress JSON responses
            if hasattr(data, 'json'):
                json_data = data.get_data()
                gzip_buffer = gzip.compress(json_data)
                data.set_data(gzip_buffer)
                data.headers['Content-Encoding'] = 'gzip'
                data.headers['Content-Length'] = len(gzip_buffer)
            
            return response
        return gzip_wrapper(*args, **kwargs)
    return view_func

# ===== TỐI ƯU 1: Connection Pooling - Reuse MongoDB client =====
_mongo_client = None

def get_mongo_client():
    """Get or create MongoDB client with connection pooling"""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = MongoClient(
            MONGO_HOST, 
            MONGO_PORT,
            maxPoolSize=50,  # Maximum connections in pool
            minPoolSize=10,  # Minimum connections to keep open
            maxIdleTimeMS=45000  # Close connections idle for 45s
        )
    return _mongo_client

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

def get_users_db():
    """Get MongoDB collection for users"""
    client = get_mongo_client()
    db = client[MONGO_DB]
    return db['users']

# ===== Authentication Functions =====
def init_default_user():
    """Create default admin user if not exists"""
    users_collection = get_users_db()
    existing_user = users_collection.find_one({'username': 'admin'})
    if not existing_user:
        users_collection.insert_one({
            'username': 'admin',
            'password': generate_password_hash('admin'),
            'created_at': datetime.utcnow()
        })
        print('✓ Default admin user created (username: admin, password: admin)')

def verify_user(username, password):
    """Verify user credentials"""
    users_collection = get_users_db()
    user = users_collection.find_one({'username': username})
    if user and check_password_hash(user['password'], password):
        return True
    return False

def login_required(f):
    """Decorator to protect routes that require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ===== TỐI ƯU 2: MongoDB Indexes cho performance =====
def ensure_indexes():
    """Create indexes for better query performance"""
    collection = get_db()
    try:
        # Compound indexes for common queries
        collection.create_index([('time', DESCENDING)], background=True)
        collection.create_index([('ip', ASCENDING), ('time', DESCENDING)], background=True)
        collection.create_index([('path', ASCENDING), ('time', DESCENDING)], background=True)
        collection.create_index([('status', ASCENDING)], background=True)
        collection.create_index([('method', ASCENDING)], background=True)
        print("✓ Indexes created/verified")
    except Exception as e:
        print(f"Warning: Could not create indexes: {e}")

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

# ===== TỐI ƯU 3: Sử dụng MongoDB unique index thay vì find_one check =====
def sync_logs_from_file(force_full_read=False):
    """Đọc file log và cập nhật vào database"""
    if not os.path.exists(LOG_PATH):
        return {'success': False, 'message': f'Log file {LOG_PATH} does not exist', 'count': 0}
    
    collection = get_db()
    
    # Create unique index để tránh duplicate
    try:
        collection.create_index(
            [('ip', ASCENDING), ('path', ASCENDING), ('time', ASCENDING)], 
            unique=True, 
            background=True
        )
    except:
        pass  # Index already exists
    
    if force_full_read:
        current_position = 0
        print(f"Force full read: Reading entire file {LOG_PATH}...")
    else:
        current_position = load_position(LOG_PATH)
        if current_position == 0:
            print(f"First run: Reading entire file {LOG_PATH}...")
        else:
            file_size = os.path.getsize(LOG_PATH)
            if file_size < current_position:
                current_position = 0
                print("Log file rotated, resetting position to 0")
    
    try:
        count = 0
        batch = []
        batch_size = 500  # Increased batch size
        
        with open(LOG_PATH, 'r', errors='ignore') as f:
            f.seek(current_position)
            
            for line in f:
                parsed = parse_log_line(line.strip())
                if parsed:
                    batch.append(parsed)
                    
                    if len(batch) >= batch_size:
                        # Use insert_many with ordered=False để skip duplicates
                        if batch:
                            try:
                                collection.insert_many(batch, ordered=False)
                                count += len(batch)
                            except Exception as e:
                                # Count only successful inserts
                                if hasattr(e, 'details') and 'writeErrors' in e.details:
                                    count += len(batch) - len(e.details['writeErrors'])
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
    
    ip = request.args.get('ip', '').strip()
    if ip:
        query['ip'] = {'$regex': ip, '$options': 'i'}
    
    ident = request.args.get('ident', '').strip()
    if ident:
        query['ident'] = {'$regex': ident, '$options': 'i'}
    
    user = request.args.get('user', '').strip()
    if user:
        query['user'] = {'$regex': user, '$options': 'i'}
    
    path = request.args.get('path', '').strip()
    if path:
        query['path'] = {'$regex': path, '$options': 'i'}
    
    method = request.args.get('method', '').strip()
    if method:
        query['method'] = method.upper()
    
    status = request.args.get('status', '').strip()
    if status:
        try:
            query['status'] = int(status)
        except ValueError:
            pass
    
    time_from = request.args.get('time_from', '').strip()
    if time_from:
        try:
            dt_from = dateparser.parse(time_from)
            if dt_from:
                query.setdefault('time', {})['$gte'] = dt_from
        except:
            pass
    
    time_to = request.args.get('time_to', '').strip()
    if time_to:
        try:
            dt_to = dateparser.parse(time_to)
            if dt_to:
                query.setdefault('time', {})['$lte'] = dt_to
        except:
            pass
    
    return query

# ===== TỐI ƯU 4: Sử dụng MongoDB Aggregation Pipeline thay vì load hết data =====
@app.route('/api/stats')
@login_required
def api_stats():
    """API trả về thống kê log - tối ưu với aggregation pipeline"""
    try:
        collection = get_db()
        limit = min(50000, max(100, int(request.args.get('limit', 10000))))
        
        # Sử dụng aggregation pipeline - xử lý trực tiếp trên DB thay vì load về memory
        pipeline = [
            {'$sort': {'time': -1}},
            {'$limit': limit},
            {'$facet': {
                'total': [{'$count': 'count'}],
                'latest': [{'$limit': 1}, {'$project': {'time': 1}}],
                'top_ips': [
                    {'$group': {'_id': '$ip', 'count': {'$sum': 1}}},
                    {'$sort': {'count': -1}},
                    {'$limit': 20}
                ],
                'top_paths': [
                    {'$group': {'_id': '$path', 'count': {'$sum': 1}}},
                    {'$sort': {'count': -1}},
                    {'$limit': 20}
                ],
                'status': [
                    {'$group': {'_id': {'$toString': '$status'}, 'count': {'$sum': 1}}},
                    {'$sort': {'count': -1}}
                ],
                'methods': [
                    {'$group': {'_id': '$method', 'count': {'$sum': 1}}},
                    {'$sort': {'count': -1}}
                ],
            'user_agents': [
                {'$group': {'_id': {'$substr': ['$agent', 0, 100]}, 'count': {'$sum': 1}}},
                {'$sort': {'count': -1}},
                {'$limit': 10}
            ],
            'referers': [
                {'$group': {'_id': {'$substr': ['$referer', 0, 100]}, 'count': {'$sum': 1}}},
                {'$sort': {'count': -1}},
                {'$limit': 10}
            ],
            'rpm': [
                {'$project': {
                    'minute': {
                        '$dateToString': {
                            'format': '%Y-%m-%dT%H:%M:00.000Z',
                            'date': '$time'
                        }
                    }
                }},
                {'$group': {'_id': '$minute', 'count': {'$sum': 1}}},
                {'$sort': {'_id': 1}}
            ],
            'hourly': [
                {'$project': {
                    'hour': {
                        '$dateToString': {
                            'format': '%Y-%m-%dT%H:00:00.000Z',
                            'date': '$time'
                        }
                    }
                }},
                {'$group': {'_id': '$hour', 'count': {'$sum': 1}}},
                {'$sort': {'_id': 1}}
            ],
            'size_distribution': [
                {'$project': {
                    'range': {
                        '$switch': {
                            'branches': [
                                {'case': {'$lt': [{'$divide': ['$size', 1024]}, 1]}, 'then': '< 1 KB'},
                                {'case': {'$lt': [{'$divide': ['$size', 1024]}, 10]}, 'then': '1-10 KB'},
                                {'case': {'$lt': [{'$divide': ['$size', 1024]}, 100]}, 'then': '10-100 KB'},
                                {'case': {'$lt': [{'$divide': ['$size', 1024]}, 1024]}, 'then': '100 KB - 1 MB'}
                            ],
                            'default': '> 1 MB'
                        }
                    }
                }},
                {'$group': {'_id': '$range', 'count': {'$sum': 1}}}
            ]
        }}
    ]
    
        result = list(collection.aggregate(pipeline, maxTimeMS=10000))[0]
        
        # Format output
        total_count = result['total'][0]['count'] if result['total'] else 0
        latest_time = result['latest'][0]['time'].isoformat() if result['latest'] else None
        
        return jsonify({
            'rpm': [[item['_id'], item['count']] for item in result['rpm']],
            'top_ips': [[item['_id'], item['count']] for item in result['top_ips']],
            'top_paths': [[item['_id'], item['count']] for item in result['top_paths']],
            'status': [[item['_id'], item['count']] for item in result['status']],
            'methods': [[item['_id'], item['count']] for item in result['methods']],
            'top_user_agents': [[item['_id'], item['count']] for item in result['user_agents']],
            'top_referers': [[item['_id'], item['count']] for item in result['referers']],
            'hourly': [[item['_id'], item['count']] for item in result['hourly']],
            'size_distribution': [[item['_id'], item['count']] for item in result['size_distribution']],
            'latest_time': latest_time,
            'total_entries': total_count
        })
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch statistics',
            'message': str(e)
        }), 500

@app.route('/api/logs')
@login_required
def api_logs():
    """API trả về danh sách logs với search và filter"""
    try:
        collection = get_db()
        
        # Build query from parameters
        query = build_search_query()
        
        # Pagination with validation
        page = max(1, int(request.args.get('page', 1)))
        per_page = min(1000, max(10, int(request.args.get('per_page', 100))))
        skip = (page - 1) * per_page
        
        # Get total count (with timeout)
        total = collection.count_documents(query, maxTimeMS=5000)
        
        # Get logs with projection to reduce data transfer
        cursor = collection.find(
            query,
            {
                '_id': 1, 'ip': 1, 'user': 1, 'time': 1,
                'method': 1, 'path': 1, 'status': 1, 'size': 1,
                'referer': 1, 'agent': 1
            }
        ).sort('time', -1).skip(skip).limit(per_page)
        
        logs = [serialize_log_entry(entry) for entry in cursor]
        
        return jsonify({
            'logs': logs,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': (total + per_page - 1) // per_page,
            'has_next': page * per_page < total,
            'has_prev': page > 1
        })
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch logs',
            'message': str(e)
        }), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page and handler"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            return render_template('login.html', error='Vui lòng nhập tên đăng nhập và mật khẩu')
        
        if verify_user(username, password):
            session['username'] = username
            session['login_time'] = datetime.utcnow().isoformat()
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Tên đăng nhập hoặc mật khẩu không đúng')
    
    # If already logged in, redirect to dashboard
    if 'username' in session:
        return redirect(url_for('index'))
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout handler"""
    session.pop('username', None)
    session.pop('login_time', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """Trang chủ - tự động sync logs từ file vào DB lần đầu"""
    # Ensure indexes on first load
    ensure_indexes()
    
    current_position = load_position(LOG_PATH)
    is_first_run = (current_position == 0)
    
    sync_result = sync_logs_from_file(force_full_read=is_first_run)
    
    if sync_result['success']:
        if sync_result['count'] > 0:
            print(f"✓ Synced {sync_result['count']} log entries from {LOG_PATH} to database")
        else:
            print(f"✓ No new log entries to sync (already up to date)")
    else:
        print(f"✗ Error syncing logs: {sync_result['message']}")
    
    return render_template('index.html')

@app.route('/api/sync', methods=['POST'])
@login_required
def api_sync():
    """API để trigger sync logs manually"""
    force = request.json.get('force', False) if request.is_json else False
    result = sync_logs_from_file(force_full_read=force)
    return jsonify(result)

if __name__ == '__main__':
    # Initialize default user on startup
    init_default_user()
    app.run(host='0.0.0.0', port=5000, debug=True)
