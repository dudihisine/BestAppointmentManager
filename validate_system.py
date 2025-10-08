#!/usr/bin/env python3
"""
Quick system validation script.
"""
import sys
import os
sys.path.append(os.path.dirname(__file__))

def validate_system():
    """Quick system validation."""
    print("🧪 Quick System Validation")
    print("=" * 40)
    
    tests_passed = 0
    tests_failed = 0
    
    # Test 1: Health endpoint
    try:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        response = client.get("/health")
        if response.status_code == 200:
            print("✅ Health endpoint working")
            tests_passed += 1
        else:
            print("❌ Health endpoint failed")
            tests_failed += 1
    except Exception as e:
        print(f"❌ Health endpoint error: {e}")
        tests_failed += 1
    
    # Test 2: Database connection
    try:
        from app.db import test_db_connection
        if test_db_connection():
            print("✅ Database connection working")
            tests_passed += 1
        else:
            print("❌ Database connection failed")
            tests_failed += 1
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        tests_failed += 1
    
    # Test 3: Redis connection
    try:
        from app.db import test_redis_connection
        if test_redis_connection():
            print("✅ Redis connection working")
            tests_passed += 1
        else:
            print("❌ Redis connection failed")
            tests_failed += 1
    except Exception as e:
        print(f"❌ Redis connection error: {e}")
        tests_failed += 1
    
    # Test 4: Webhook routing
    try:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        response = client.post("/webhooks/whatsapp", data={
            "From": "whatsapp:+1234567890",
            "Body": "test",
            "MessageSid": "test123"
        })
        if response.status_code == 200:
            print("✅ Webhook routing working")
            tests_passed += 1
        else:
            print("❌ Webhook routing failed")
            tests_failed += 1
    except Exception as e:
        print(f"❌ Webhook routing error: {e}")
        tests_failed += 1
    
    # Test 5: Session management
    try:
        from app.utils.session import SessionManager
        session_manager = SessionManager()
        session = session_manager.set_session("+1234567890", "test", "start")
        if session and session_manager.get_session("+1234567890"):
            print("✅ Session management working")
            tests_passed += 1
        else:
            print("❌ Session management failed")
            tests_failed += 1
    except Exception as e:
        print(f"❌ Session management error: {e}")
        tests_failed += 1
    
    print("=" * 40)
    print(f"✅ Passed: {tests_passed}")
    print(f"❌ Failed: {tests_failed}")
    
    if tests_failed == 0:
        print("🎉 ALL CORE TESTS PASSED!")
        print("🚀 System is ready for Task 5!")
        return True
    else:
        print("⚠️  Some tests failed. Please review.")
        return False

if __name__ == "__main__":
    success = validate_system()
    sys.exit(0 if success else 1)
