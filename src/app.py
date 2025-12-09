# app.py
from flask import Flask, jsonify, render_template
from tinydb import TinyDB
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import itertools


DB_PATH = 'logs.json'
app = Flask(__name__)
def load_entries(limit=10000):
    db = TinyDB(DB_PATH)
    return db.all()[-limit:]
@app.route('/api/stats')
def api_stats():
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
            dt = datetime.fromisoformat(t)
        except Exception:
            continue
    minute = dt.replace(second=0, microsecond=0)
    rpm[minute.isoformat()] += 1
    if e.get('ip'):
        top_ips[e['ip']] += 1
    if e.get('path'):
        top_paths[e['path']] += 1
    if e.get('status'):
        status[str(e['status'])] += 1


    # sort rpm by time (last 60 points)
    rpm_items = sorted(rpm.items())
    return jsonify({
        'rpm': rpm_items,
        'top_ips': top_ips.most_common(10),
        'top_paths': top_paths.most_common(10),
        'status': status.most_common(),
    })




@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)