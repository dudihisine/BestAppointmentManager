#!/usr/bin/env python3
"""
Simple test runner that validates system functionality.
"""
import os
import sys
import subprocess

def run_tests():
    """Run the test suite and return success status."""
    print("🧪 Running WhatsApp Appointment Assistant Test Suite...")
    print("=" * 60)
    
    try:
        # Run the test suite
        result = subprocess.run([
            sys.executable, "test_suite.py"
        ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
        
        # Print output
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        
        # Check if tests passed
        success = result.returncode == 0
        
        if success:
            print("\n✅ ALL TESTS PASSED!")
            print("🚀 System is validated and ready for Task 5!")
        else:
            print(f"\n❌ Tests failed with exit code: {result.returncode}")
            print("Please review the output above and fix any issues.")
        
        return success
        
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
