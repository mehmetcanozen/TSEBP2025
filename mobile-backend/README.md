# 🎵 Audio Extractor — Backend API

Edge deployment mimarisi için FastAPI backend. Model işleme **cihazda** yapılır;
bu API auth, model güncelleme ve geçmiş yönetimini sağlar.

---

## 🏗️ Mimari

```
Windows App  ──┐
               ├──► [FastAPI Backend] ──► [PostgreSQL]
Mobile App   ──┘
     │
     └── Model çalıştırma LOCAL (cihazda)
```

---

## 📁 Klasör Yapısı

```
backend/
├── main.py                  # Uygulama giriş noktası
├── core/
│   ├── config.py            # Ayarlar (.env)
│   ├── security.py          # JWT, bcrypt
│   └── dependencies.py      # FastAPI dependency injection
├── database/
│   ├── db.py                # SQLAlchemy engine
│   ├── models.py            # ORM tabloları
│   └── schemas.py           # Pydantic şemaları
├── routers/
│   ├── auth.py              # /auth/*
│   ├── model_update.py      # /model/*
│   ├── history.py           # /history/*
│   └── devices.py           # /devices/*
├── scripts/
│   ├── create_admin.py      # İlk admin oluştur
│   └── convert_to_onnx.py   # PyTorch → ONNX
├── tests/
│   ├── test_auth.py
│   └── test_history.py
├── models_store/            # .onnx dosyaları (git ignore)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## 🚀 Kurulum

### 1. Ortam hazırlama

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. .env oluştur

```bash
cp .env.example .env
# .env dosyasını düzenle
```

### 3. PostgreSQL başlat

```bash
# Docker ile:
docker-compose up db -d

# Veya yerel PostgreSQL kullanıyorsan:
createdb audioapp
```

### 4. Çalıştır

```bash
uvicorn main:app --reload
```

Uygulama → http://localhost:8000  
Docs    → http://localhost:8000/docs

---

## 🐳 Docker ile Tam Kurulum

```bash
cp .env.example .env
# .env'i düzenle

docker-compose up --build
```

---

## 👤 İlk Admin Oluştur

```bash
python scripts/create_admin.py
```

---

## 🔌 API Endpoint'leri

### Auth
| Method | URL | Açıklama | Auth |
|--------|-----|----------|------|
| POST | `/auth/register` | Kayıt ol | ❌ |
| POST | `/auth/login` | Giriş yap → token al | ❌ |
| POST | `/auth/refresh` | Access token yenile | ❌ |
| POST | `/auth/logout` | Çıkış yap | ❌ |
| GET  | `/auth/me` | Profil bilgisi | ✅ |
| PUT  | `/auth/change-password` | Şifre değiştir | ✅ |

### Model Güncelleme
| Method | URL | Açıklama | Auth |
|--------|-----|----------|------|
| GET  | `/model/latest?platform=android&current_version=1.0.0` | Güncelleme var mı? | ✅ |
| GET  | `/model/download/{version_id}` | Model indir | ✅ |
| POST | `/model/upload` | Yeni model yükle | 🔒 Admin |
| GET  | `/model/versions` | Tüm versiyonlar | 🔒 Admin |
| PATCH | `/model/versions/{id}/toggle` | Aktif/pasif yap | 🔒 Admin |

### Geçmiş
| Method | URL | Açıklama | Auth |
|--------|-----|----------|------|
| POST | `/history` | İşlem kaydı ekle | ✅ |
| GET  | `/history?page=1&per_page=20` | Geçmişi getir | ✅ |
| DELETE | `/history` | Tüm geçmişi sil | ✅ |

### Cihaz
| Method | URL | Açıklama | Auth |
|--------|-----|----------|------|
| POST | `/devices/register` | Cihaz kaydet | ✅ |

---

## 📱 Uygulama Tarafında Kullanım

### 1. Login → Token al
```http
POST /auth/login
{"email": "user@example.com", "password": "pass123"}

→ {"access_token": "...", "refresh_token": "..."}
```

### 2. Model güncellemesi kontrol et (uygulama açılışında)
```http
GET /model/latest?platform=android&current_version=1.0.0
Authorization: Bearer <access_token>

→ {"has_update": true, "latest_version": "1.1.0", "download_url": "/model/download/3", ...}
```

### 3. Yeni modeli indir
```http
GET /model/download/3
Authorization: Bearer <access_token>

→ model.onnx binary stream
```

### 4. İşlem geçmişini kaydet
```http
POST /history
Authorization: Bearer <access_token>
{"file_name": "vocals.wav", "duration_seconds": 95.3, "model_version": "1.1.0", "platform": "android", "status": "success"}
```

### 5. Token yenile (access_token süresi dolunca)
```http
POST /auth/refresh
{"refresh_token": "..."}

→ Yeni access_token + yeni refresh_token
```

---

## 🧠 Model Dönüştürme (PyTorch → ONNX)

```bash
python scripts/convert_to_onnx.py \
  --model model.pt \
  --output models_store/model_v1.0.0.onnx \
  --input_len 16000
```

---

## 🧪 Testler

```bash
pip install pytest httpx
pytest tests/ -v
```

---

## 🌐 Production Deployment (Render.com — Ücretsiz)

1. GitHub'a push et
2. https://render.com → New Web Service
3. Environment variables ekle (.env içeriği)
4. Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

---

## 🔐 Güvenlik Notları

- `.env` dosyasını asla git'e commit etme
- `SECRET_KEY` için uzun ve rastgele bir değer kullan: `openssl rand -hex 32`
- Production'da `DEBUG=False` yap
- CORS `allow_origins=["*"]` yerine gerçek domain yaz
