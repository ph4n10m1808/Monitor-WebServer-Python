# 🔐 Hướng Dẫn Xác Thực (Authentication)

Hệ thống Monitor WebServer Python đã được tích hợp tính năng đăng nhập để bảo vệ dashboard.

## 📋 Tính Năng

- ✅ Form đăng nhập với giao diện đẹp
- ✅ Lưu trữ thông tin user trong MongoDB
- ✅ Mật khẩu được hash bằng Werkzeug (bcrypt)
- ✅ Session-based authentication
- ✅ Bảo vệ tất cả routes (dashboard, API)
- ✅ Tự động tạo user admin mặc định
- ✅ Hiển thị username và nút đăng xuất

## 🚀 Khởi Động Hệ Thống

### 1. Sử dụng Docker Compose (Khuyến nghị)

```bash
docker-compose up --build -d
```

### 2. Truy cập Dashboard

Mở trình duyệt và vào: http://localhost:5050/login

### 3. Thông tin đăng nhập mặc định

```
Username: admin
Password: admin
```

**⚠️ Quan trọng**: Nên thay đổi mật khẩu admin sau khi đăng nhập lần đầu!

## 👤 Quản Lý Users

### Tạo User Mới

Có 2 cách để tạo user:

#### Cách 1: Sử dụng script Python (Trong container)

```bash
# Vào container dashboard
docker exec -it log_dashboard bash

# Tạo user mới
python create_user.py john_doe mypassword123

# Liệt kê tất cả users
python create_user.py --list
```

#### Cách 2: Sử dụng MongoDB trực tiếp

```bash
# Kết nối MongoDB
docker exec -it log_mongodb mongosh

# Chuyển sang database logdb
use logdb

# Xem danh sách users
db.users.find().pretty()

# Tạo user mới (cần hash password trước)
# Sử dụng script create_user.py thay vì tạo thủ công
```

### Liệt Kê Users

```bash
docker exec -it log_dashboard python create_user.py --list
```

### Xóa User

```bash
docker exec -it log_mongodb mongosh

use logdb
db.users.deleteOne({username: "john_doe"})
```

## 🔒 Cấu Trúc Database

### Collection: `users`

```json
{
  "_id": ObjectId("..."),
  "username": "admin",
  "password": "$2b$12$...",  // Hashed password
  "created_at": ISODate("2024-01-01T00:00:00Z")
}
```

### Indexes

```javascript
// Unique index trên username
db.users.createIndex({ username: 1 }, { unique: true });
```

## 🔐 Security Best Practices

### 1. Thay đổi SECRET_KEY trong Production

Trong [docker-compose.yml](docker-compose.yml):

```yaml
environment:
  - SECRET_KEY=your-very-long-random-secret-key-here
```

Tạo secret key ngẫu nhiên:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Thay đổi mật khẩu admin

```bash
# Vào container
docker exec -it log_dashboard bash

# Xóa admin cũ
docker exec -it log_mongodb mongosh logdb --eval "db.users.deleteOne({username: 'admin'})"

# Tạo admin mới với password mạnh
python create_user.py admin "your-strong-password-here"
```

### 3. Sử dụng HTTPS trong Production

Cấu hình reverse proxy (Nginx) với SSL certificate:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:5050;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 🔄 Workflow

1. **User truy cập** → Redirect đến `/login`
2. **Nhập credentials** → Server kiểm tra trong MongoDB
3. **Đăng nhập thành công** → Tạo session, redirect đến dashboard
4. **Truy cập protected routes** → Middleware kiểm tra session
5. **Đăng xuất** → Xóa session, redirect về login

## 📝 Routes

| Route        | Method    | Protected | Mô tả              |
| ------------ | --------- | --------- | ------------------ |
| `/login`     | GET, POST | ❌        | Trang đăng nhập    |
| `/logout`    | GET       | ❌        | Đăng xuất          |
| `/`          | GET       | ✅        | Dashboard chính    |
| `/api/stats` | GET       | ✅        | API thống kê       |
| `/api/logs`  | GET       | ✅        | API danh sách logs |
| `/api/sync`  | POST      | ✅        | API đồng bộ logs   |

## 🐛 Troubleshooting

### Lỗi: "Session not found"

```bash
# Restart container dashboard
docker-compose restart dashboard
```

### Lỗi: "User not found"

```bash
# Kiểm tra xem user có tồn tại không
docker exec -it log_mongodb mongosh logdb --eval "db.users.find().pretty()"

# Tạo lại user admin
docker exec -it log_dashboard python create_user.py admin admin
```

### Quên mật khẩu

```bash
# Reset password cho user admin
docker exec -it log_mongodb mongosh logdb --eval "db.users.deleteOne({username: 'admin'})"
docker exec -it log_dashboard python create_user.py admin newpassword123
```

## 📚 Tài Liệu Thêm

- [Flask Sessions](https://flask.palletsprojects.com/en/2.3.x/quickstart/#sessions)
- [Werkzeug Security](https://werkzeug.palletsprojects.com/en/2.3.x/utils/#module-werkzeug.security)
- [MongoDB Security](https://www.mongodb.com/docs/manual/security/)

## 🎯 Next Steps

1. Thêm tính năng "Quên mật khẩu"
2. Thêm role-based access control (Admin, Viewer)
3. Thêm 2FA (Two-Factor Authentication)
4. Thêm API key authentication cho API endpoints
5. Thêm rate limiting cho login attempts

---

**Developed with ❤️ for secure log monitoring**
