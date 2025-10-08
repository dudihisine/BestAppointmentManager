#!/usr/bin/env python3
"""
Test script to demonstrate AI suggestions in different modes.
"""
import requests
import time

BASE_URL = "http://localhost:8000"

def test_mode_change(mode):
    """Test changing to a specific mode and check suggestions."""
    print(f"\n🔄 Testing {mode.upper()} mode...")
    
    # Change mode
    response = requests.post(f"{BASE_URL}/owner/change-intent", 
                           data={"intent": mode})
    
    if response.status_code == 200:
        print(f"✅ Successfully changed to {mode} mode")
        
        # Wait a moment for the change to take effect
        time.sleep(1)
        
        # Get dashboard to see suggestions
        dashboard_response = requests.get(f"{BASE_URL}/owner/dashboard")
        
        if "AI Assistant" in dashboard_response.text:
            print(f"✅ AI suggestions are visible in {mode} mode")
            
            # Extract suggestions section
            content = dashboard_response.text
            start = content.find("AI Assistant")
            end = content.find("Waitlist Overview", start)
            
            if start != -1 and end != -1:
                suggestions_section = content[start:end]
                
                # Count suggestions
                suggestion_count = suggestions_section.count('alert ')
                print(f"📊 Found {suggestion_count} AI suggestions")
                
                # Look for mode-specific content
                if mode == "max_profit" and "💰" in suggestions_section:
                    print("💰 Profit-focused suggestions detected")
                elif mode == "balanced" and "⚖️" in suggestions_section:
                    print("⚖️ Balanced suggestions detected")
                elif mode == "free_time" and "🌿" in suggestions_section:
                    print("🌿 Free-time suggestions detected")
                
        else:
            print(f"❌ No AI suggestions found in {mode} mode")
    else:
        print(f"❌ Failed to change to {mode} mode: {response.status_code}")

def main():
    """Test all three modes."""
    print("🤖 Testing AI Suggestions in Different Modes")
    print("=" * 50)
    
    # Test server health
    try:
        health_response = requests.get(f"{BASE_URL}/health")
        if health_response.status_code == 200:
            print("✅ Server is running")
        else:
            print("❌ Server health check failed")
            return
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server. Make sure it's running on port 8000")
        return
    
    # Test each mode
    modes = ["max_profit", "balanced", "free_time"]
    
    for mode in modes:
        test_mode_change(mode)
        time.sleep(2)  # Wait between mode changes
    
    print("\n🎯 Test Complete!")
    print("\nTo see the suggestions:")
    print("1. Go to: http://localhost:8000/owner")
    print("2. Login with: +972501234567")
    print("3. Change modes and watch the AI suggestions update!")
    print("4. Navigate to different dates to see date-specific suggestions")

if __name__ == "__main__":
    main()
