#!/usr/bin/env python3
"""
İlk admin kullanıcısını oluştur.
Kullanım: python scripts/create_admin.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import SessionLocal, engine, Base
from database.models import User
from core.security import hash_password

Base.metadata.create_all(bind=engine)


def create_admin():
    print("=== Admin Kullanıcı Oluştur ===")
    email    = input("E-posta: ").strip()
    username = input("Kullanıcı adı: ").strip()
    password = input("Şifre (gizli): ").strip()

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            print("❌ Bu e-posta zaten kayıtlı!")
            return

        admin = User(
            email=email,
            username=username,
            password=hash_password(password),
            is_admin=True,
        )
        db.add(admin)
        db.commit()
        print(f"✅ Admin oluşturuldu: {username} ({email})")
    finally:
        db.close()


if __name__ == "__main__":
    create_admin()
