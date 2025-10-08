#!/usr/bin/env python3
"""
Comprehensive end-to-end test suite for the appointment management system.
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add the project root to the sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal
from app.models import Owner, Service, Client, Appointment, AppointmentStatus
from app.routes.client import handle_client_message
from app.services.test_messaging import enable_test_mode, get_captured_messages, clear_captured_messages
from app.utils.session import clear_session

class SystemTester:
    """Comprehensive system testing class."""
    
    def __init__(self):
        self.db = SessionLocal()
        self.test_phone = "+1234567890"
        self.test_results = []
        
    async def run_all_tests(self):
        """Run all system tests."""
        print("🧪 **COMPREHENSIVE SYSTEM TEST SUITE**")
        print("=" * 60)
        
        # Enable test mode
        enable_test_mode()
        
        # Run test categories
        await self.test_booking_flow()
        await self.test_appointment_management()
        await self.test_natural_language()
        await self.test_background_jobs()
        await self.test_error_handling()
        await self.test_owner_dashboard()
        
        # Print summary
        self.print_test_summary()
        
    async def test_booking_flow(self):
        """Test complete booking flow."""
        print("\n📅 **TEST 1: Complete Booking Flow**")
        print("-" * 40)
        
        # Clear any existing session
        clear_session(self.test_phone)
        clear_captured_messages(self.test_phone)
        
        # Test booking flow steps
        steps = [
            ("book", "Start booking"),
            ("Test User", "Provide name"),
            ("1", "Select service"),
            ("2", "Select tomorrow"),
            ("1", "Select time slot")
        ]
        
        for message, description in steps:
            print(f"  📝 {description}: '{message}'")
            await handle_client_message(self.test_phone, message, self.db)
            
            captured = get_captured_messages(self.test_phone)
            if captured:
                print(f"    ✅ Response: {captured[-1]['content'][:50]}...")
            else:
                print(f"    ❌ No response")
        
        # Check if appointment was created
        appointment = self.db.query(Appointment).filter(
            Appointment.client_id == self.db.query(Client).filter(Client.phone == self.test_phone).first().id
        ).order_by(Appointment.id.desc()).first()
        
        if appointment:
            print(f"  ✅ Appointment created: ID {appointment.id}")
            self.test_results.append(("Booking Flow", "PASS"))
        else:
            print(f"  ❌ No appointment created")
            self.test_results.append(("Booking Flow", "FAIL"))
    
    async def test_appointment_management(self):
        """Test appointment management (view, cancel, reschedule)."""
        print("\n📋 **TEST 2: Appointment Management**")
        print("-" * 40)
        
        # Test viewing appointments
        clear_captured_messages(self.test_phone)
        await handle_client_message(self.test_phone, "appointments", self.db)
        
        captured = get_captured_messages(self.test_phone)
        if captured and "appointments" in captured[-1]['content'].lower():
            print(f"  ✅ View appointments: Working")
            self.test_results.append(("View Appointments", "PASS"))
        else:
            print(f"  ❌ View appointments: Failed")
            self.test_results.append(("View Appointments", "FAIL"))
        
        # Test cancel flow
        clear_captured_messages(self.test_phone)
        await handle_client_message(self.test_phone, "cancel", self.db)
        
        captured = get_captured_messages(self.test_phone)
        if captured and "cancel" in captured[-1]['content'].lower():
            print(f"  ✅ Cancel flow: Working")
            self.test_results.append(("Cancel Flow", "PASS"))
        else:
            print(f"  ❌ Cancel flow: Failed")
            self.test_results.append(("Cancel Flow", "FAIL"))
    
    async def test_natural_language(self):
        """Test natural language command recognition."""
        print("\n🗣️ **TEST 3: Natural Language Commands**")
        print("-" * 40)
        
        natural_commands = [
            ("Hi! Can you show me my appointments?", "appointments"),
            ("I'd like to book a haircut", "booking"),
            ("I need to cancel my appointment", "cancel"),
            ("Can I reschedule?", "reschedule")
        ]
        
        for command, expected_action in natural_commands:
            clear_captured_messages(self.test_phone)
            await handle_client_message(self.test_phone, command, self.db)
            
            captured = get_captured_messages(self.test_phone)
            if captured and expected_action in captured[-1]['content'].lower():
                print(f"  ✅ '{command}' → {expected_action}")
                self.test_results.append((f"Natural Language: {expected_action}", "PASS"))
            else:
                print(f"  ❌ '{command}' → Failed")
                self.test_results.append((f"Natural Language: {expected_action}", "FAIL"))
    
    async def test_background_jobs(self):
        """Test background job system."""
        print("\n⏰ **TEST 4: Background Jobs**")
        print("-" * 40)
        
        try:
            from app.services.background_jobs import send_appointment_reminder
            
            # Get a test appointment
            appointment = self.db.query(Appointment).filter(
                Appointment.status == AppointmentStatus.CONFIRMED
            ).first()
            
            if appointment:
                clear_captured_messages(appointment.client.phone)
                await send_appointment_reminder(appointment.id, '24h')
                
                captured = get_captured_messages(appointment.client.phone)
                if captured and "reminder" in captured[-1]['content'].lower():
                    print(f"  ✅ Appointment reminders: Working")
                    self.test_results.append(("Background Jobs", "PASS"))
                else:
                    print(f"  ❌ Appointment reminders: Failed")
                    self.test_results.append(("Background Jobs", "FAIL"))
            else:
                print(f"  ⚠️ No confirmed appointments for testing")
                self.test_results.append(("Background Jobs", "SKIP"))
                
        except Exception as e:
            print(f"  ❌ Background jobs test failed: {e}")
            self.test_results.append(("Background Jobs", "FAIL"))
    
    async def test_error_handling(self):
        """Test error handling and edge cases."""
        print("\n⚠️ **TEST 5: Error Handling**")
        print("-" * 40)
        
        # Test invalid commands
        clear_captured_messages(self.test_phone)
        await handle_client_message(self.test_phone, "invalid_command_123", self.db)
        
        captured = get_captured_messages(self.test_phone)
        if captured and ("help" in captured[-1]['content'].lower() or "command" in captured[-1]['content'].lower()):
            print(f"  ✅ Invalid command handling: Working")
            self.test_results.append(("Error Handling", "PASS"))
        else:
            print(f"  ❌ Invalid command handling: Failed")
            self.test_results.append(("Error Handling", "FAIL"))
    
    async def test_owner_dashboard(self):
        """Test owner dashboard functionality."""
        print("\n👨‍💼 **TEST 6: Owner Dashboard**")
        print("-" * 40)
        
        try:
            # Test dashboard data retrieval
            owner = self.db.query(Owner).first()
            if owner:
                from app.services.optimizer import get_optimization_suggestions
                
                today = datetime.now().date()
                suggestions = await get_optimization_suggestions(self.db, owner.id, today)
                
                if suggestions.get('success'):
                    print(f"  ✅ Dashboard data: Working")
                    print(f"    - Suggestions: {suggestions.get('total_suggestions', 0)}")
                    self.test_results.append(("Owner Dashboard", "PASS"))
                else:
                    print(f"  ❌ Dashboard data: Failed")
                    self.test_results.append(("Owner Dashboard", "FAIL"))
            else:
                print(f"  ⚠️ No owner found for testing")
                self.test_results.append(("Owner Dashboard", "SKIP"))
                
        except Exception as e:
            print(f"  ❌ Dashboard test failed: {e}")
            self.test_results.append(("Owner Dashboard", "FAIL"))
    
    def print_test_summary(self):
        """Print test results summary."""
        print("\n" + "=" * 60)
        print("📊 **TEST RESULTS SUMMARY**")
        print("=" * 60)
        
        passed = len([r for r in self.test_results if r[1] == "PASS"])
        failed = len([r for r in self.test_results if r[1] == "FAIL"])
        skipped = len([r for r in self.test_results if r[1] == "SKIP"])
        total = len(self.test_results)
        
        print(f"✅ Passed: {passed}/{total}")
        print(f"❌ Failed: {failed}/{total}")
        print(f"⏭️ Skipped: {skipped}/{total}")
        
        print(f"\n📋 **Detailed Results:**")
        for test_name, result in self.test_results:
            status_emoji = "✅" if result == "PASS" else "❌" if result == "FAIL" else "⏭️"
            print(f"  {status_emoji} {test_name}: {result}")
        
        if failed == 0:
            print(f"\n🎉 **ALL TESTS PASSED!** The system is ready for production!")
        else:
            print(f"\n⚠️ **{failed} tests failed.** Please review and fix issues.")
        
        print(f"\n💡 **Next Steps:**")
        print(f"  1. Start the background worker: python worker.py")
        print(f"  2. Access the web interface: http://localhost:8000")
        print(f"  3. Test with real WhatsApp: Configure Twilio credentials")
        print(f"  4. Deploy to production: Set up production environment")

async def main():
    """Run the complete test suite."""
    tester = SystemTester()
    try:
        await tester.run_all_tests()
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        tester.db.close()

if __name__ == "__main__":
    asyncio.run(main())
