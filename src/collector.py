# collector.py
import time
import os
from tinydb import TinyDB, Query
from dateutil import parser as dateparser

LOG_PATH = '/var/log/apache2/access.log' # thay đổi theo môi trường
DB_PATH = 'logs.json'

# Regex cho Common/Combined Log Format
LOG_PATTERN = re.compile(
    r'(?P<ip>\S+) ' # IP
    r'(?P<ident>\S+) ' # ident
    r'(?P<user>\S+) ' # user
    r'\[(?P<time>[^\]]+)\] ' # time
    r'"(?P<request>[^"]*)" ' # request
    r'(?P<status>\d{3}) ' # status
    r'(?P<size>\S+)' # size
    r'( "(?P<referer>[^"]*)")?'
    r'( "(?P<agent>[^"]*)")?'
)
def parse_log_line(line):
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
        dt = None
    size = None if d['size'] == '-' else int(d['size'])
    return {
        'ip': d.get('ip'),
        'user': d.get('user'),
        'time': dt.isoformat() if dt else None,
        'method': method,
        'path': path,
        'proto': proto,
        'status': int(d.get('status')) if d.get('status') else None,
        'size': size,
        'referer': d.get('referer'),
        'agent': d.get('agent')
    }
def follow(thefile):
    thefile.seek(0, os.SEEK_END)
    while True:
        line = thefile.readline()
        if not line:
            time.sleep(0.5)
        continue    
    yield line
if __name__ == '__main__':
    db = TinyDB(DB_PATH)
print('Starting log collector...')
with open(LOG_PATH, 'r', errors='ignore') as f:
    loglines = follow(f)
for line in loglines:
    parsed = parse_log_line(line.strip())
if parsed:
    db.insert(parsed)