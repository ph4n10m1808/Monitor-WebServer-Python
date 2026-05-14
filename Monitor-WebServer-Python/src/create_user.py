#!/usr/bin/env python3
"""
Script để tạo user mới trong MongoDB
Usage: python create_user.py <username> <password>
"""
import sys
import os
from pymongo import MongoClient
from werkzeug.security import generate_password_hash
from datetime import datetime

# MongoDB connection
MONGO_HOST = os.getenv('MONGO_HOST', 'localhost')
MONGO_PORT = int(os.getenv('MONGO_PORT', 27017))
MONGO_DB = os.getenv('MONGO_DB', 'logdb')

def create_user(username, password):
    """Create a new user in MongoDB"""
    try:
        client = MongoClient(MONGO_HOST, MONGO_PORT)
        db = client[MONGO_DB]
        users_collection = db['users']
        
        # Check if user exists
        existing_user = users_collection.find_one({'username': username})
        if existing_user:
            print(f'❌ User "{username}" already exists!')
            return False
        
        # Create new user
        user_doc = {
            'username': username,
            'password': generate_password_hash(password),
            'created_at': datetime.utcnow()
        }
        
        users_collection.insert_one(user_doc)
        print(f'✅ User "{username}" created successfully!')
        return True
        
    except Exception as e:
        print(f'❌ Error creating user: {e}')
        return False
    finally:
        client.close()

def list_users():
    """List all users in database"""
    try:
        client = MongoClient(MONGO_HOST, MONGO_PORT)
        db = client[MONGO_DB]
        users_collection = db['users']
        
        users = list(users_collection.find({}, {'password': 0}))
        if not users:
            print('No users found in database')
            return
        
        print(f'\n📋 Total users: {len(users)}')
        print('-' * 60)
        for user in users:
            created = user.get('created_at', 'N/A')
            print(f"Username: {user['username']:<20} Created: {created}")
        print('-' * 60)
        
    except Exception as e:
        print(f'❌ Error listing users: {e}')
    finally:
        client.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage:')
        print('  Create user: python create_user.py <username> <password>')
        print('  List users:  python create_user.py --list')
        sys.exit(1)
    
    if sys.argv[1] == '--list':
        list_users()
    elif len(sys.argv) == 3:
        username = sys.argv[1]
        password = sys.argv[2]
        create_user(username, password)
    else:
        print('Invalid arguments!')
        print('Usage:')
        print('  Create user: python create_user.py <username> <password>')
        print('  List users:  python create_user.py --list')
        sys.exit(1)
