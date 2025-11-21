"""Test script to check if uma_module can be imported"""
import sys
import traceback

print("=" * 50)
print("Testing Uma Module Import")
print("=" * 50)

try:
    print("\n1. Testing uma_module import...")
    import uma_module
    print("✓ uma_module imported successfully")
    
    print("\n2. Checking if functions exist...")
    assert hasattr(uma_module, 'start_uma_background_tasks'), "start_uma_background_tasks not found"
    print("✓ start_uma_background_tasks found")
    
    assert hasattr(uma_module, 'init_uma_db'), "init_uma_db not found"
    print("✓ init_uma_db found")
    
    assert hasattr(uma_module, 'uma_update_timers'), "uma_update_timers not found"
    print("✓ uma_update_timers found")
    
    print("\n3. Checking logger...")
    assert hasattr(uma_module, 'uma_logger'), "uma_logger not found"
    print("✓ uma_logger found")
    
    print("\n4. Testing uma_handler import...")
    import uma_handler
    print("✓ uma_handler imported successfully")
    
    assert hasattr(uma_handler, 'download_timeline'), "download_timeline not found"
    print("✓ download_timeline found")
    
    assert hasattr(uma_handler, 'update_uma_events'), "update_uma_events not found"
    print("✓ update_uma_events found")
    
    print("\n" + "=" * 50)
    print("✓ ALL TESTS PASSED")
    print("=" * 50)
    
except ImportError as e:
    print(f"\n✗ Import Error: {e}")
    traceback.print_exc()
    sys.exit(1)
except AssertionError as e:
    print(f"\n✗ Assertion Error: {e}")
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f"\n✗ Unexpected Error: {e}")
    traceback.print_exc()
    sys.exit(1)
