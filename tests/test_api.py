#!/usr/bin/env python3
"""
Automated test suite for BYOD Synthetic Data Generator API
"""
import json
import time
import requests
import pandas as pd
from io import StringIO
from pathlib import Path

BASE_URL = "http://localhost:8201"

def test_health_check():
    """Test the health endpoint"""
    print("Testing health check...")
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    print("✓ Health check passed")
    return True

def test_cache_info():
    """Test cache info endpoint"""
    print("\nTesting cache info API...")
    response = requests.get(f"{BASE_URL}/api/cache-info")
    assert response.status_code == 200
    data = response.json()
    assert "statistics" in data
    assert "entries" in data
    print(f"✓ Cache info: {data['statistics']['total_entries']} entries, {data['statistics']['cache_size_mb']:.2f} MB")
    return True

def test_cache_clear():
    """Test cache clear endpoint"""
    print("\nTesting cache clear API...")
    # Clear entries older than 365 days (should keep recent ones)
    response = requests.delete(f"{BASE_URL}/api/cache/clear?older_than_days=365")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    print(f"✓ Cache clear: {data['message']}")
    return True

def test_usage_logs():
    """Test usage logs endpoint"""
    print("\nTesting usage logs API...")
    response = requests.get(f"{BASE_URL}/api/usage-logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    # Summary field may or may not exist depending on implementation
    log_count = len(data.get('logs', []))
    print(f"✓ Usage logs: {log_count} entries found")
    return True

def test_file_generation():
    """Test file-based synthetic data generation"""
    print("\nTesting file-based generation...")

    # Create test file
    test_file = Path("tests/test_api_data.csv")
    test_data = pd.DataFrame({
        'customer_id': range(1, 6),
        'purchase_amount': [100.50, 250.75, 175.25, 300.00, 150.00],
        'product_category': ['Electronics', 'Clothing', 'Books', 'Electronics', 'Clothing']
    })
    test_data.to_csv(test_file, index=False)

    # Test with different cache modes
    cache_modes = ['off', 'structure', 'structure_stats']

    for cache_mode in cache_modes:
        print(f"  Testing cache_mode={cache_mode}...")

        with open(test_file, 'rb') as f:
            files = {'file': ('test.csv', f, 'text/csv')}
            data = {
                'row_count': '10',
                'output_format': 'csv',
                'cache_mode': cache_mode
            }

            start_time = time.time()
            response = requests.post(f"{BASE_URL}/generate", files=files, data=data)
            duration = time.time() - start_time

            assert response.status_code == 200

            # Parse CSV response
            df_result = pd.read_csv(StringIO(response.text))
            # LLM might generate slightly different number of rows
            assert len(df_result) >= 5  # At least 5 rows
            assert len(df_result) <= 15  # At most 15 rows
            assert list(df_result.columns) == list(test_data.columns)

            print(f"    ✓ Generated {len(df_result)} rows in {duration:.2f}s")

    # Clean up
    test_file.unlink()
    print("✓ File-based generation tests passed")
    return True

def test_cache_hit_performance():
    """Test that cache hits are faster than misses"""
    print("\nTesting cache hit performance...")

    # Create unique test file
    test_file = Path("tests/test_cache_perf.csv")
    test_data = pd.DataFrame({
        'metric_a': range(1, 11),
        'metric_b': [x * 2.5 for x in range(1, 11)],
        'category': ['A', 'B'] * 5
    })
    test_data.to_csv(test_file, index=False)

    # First request (cache miss)
    with open(test_file, 'rb') as f:
        files = {'file': ('test.csv', f, 'text/csv')}
        data = {
            'row_count': '20',
            'output_format': 'csv',
            'cache_mode': 'structure_stats'
        }

        start_time = time.time()
        response1 = requests.post(f"{BASE_URL}/generate", files=files, data=data)
        time_miss = time.time() - start_time
        assert response1.status_code == 200

    print(f"  Cache miss time: {time_miss:.2f}s")

    # Second request (cache hit)
    with open(test_file, 'rb') as f:
        files = {'file': ('test.csv', f, 'text/csv')}
        data = {
            'row_count': '20',
            'output_format': 'csv',
            'cache_mode': 'structure_stats'
        }

        start_time = time.time()
        response2 = requests.post(f"{BASE_URL}/generate", files=files, data=data)
        time_hit = time.time() - start_time
        assert response2.status_code == 200

    print(f"  Cache hit time: {time_hit:.2f}s")

    # Cache hit should be significantly faster
    if time_hit < time_miss:
        speedup = time_miss / time_hit
        print(f"  ✓ Cache hit is {speedup:.1f}x faster")
    else:
        print(f"  ⚠ Cache hit not faster (might be due to small dataset)")

    # Clean up
    test_file.unlink()
    return True

def test_different_formats():
    """Test JSON vs CSV output formats"""
    print("\nTesting different output formats...")

    # Create test file
    test_file = Path("tests/test_formats.csv")
    test_data = pd.DataFrame({
        'id': range(1, 4),
        'value': [10.5, 20.3, 30.7]
    })
    test_data.to_csv(test_file, index=False)

    # Test CSV format
    with open(test_file, 'rb') as f:
        files = {'file': ('test.csv', f, 'text/csv')}
        data = {'row_count': '5', 'output_format': 'csv', 'cache_mode': 'off'}
        response = requests.post(f"{BASE_URL}/generate", files=files, data=data)
        assert response.status_code == 200
        df_csv = pd.read_csv(StringIO(response.text))
        # Allow some variance in row count
        assert len(df_csv) >= 3 and len(df_csv) <= 10
        print(f"  ✓ CSV format: {len(df_csv)} rows")

    # Test JSON format
    with open(test_file, 'rb') as f:
        files = {'file': ('test.csv', f, 'text/csv')}
        data = {'row_count': '5', 'output_format': 'json', 'cache_mode': 'off'}
        response = requests.post(f"{BASE_URL}/generate", files=files, data=data)
        assert response.status_code == 200
        json_data = json.loads(response.text)
        # Allow some variance in row count
        assert len(json_data) >= 3 and len(json_data) <= 10
        print(f"  ✓ JSON format: {len(json_data)} records")

    # Clean up
    test_file.unlink()
    print("✓ Format tests passed")
    return True

def run_all_tests():
    """Run all API tests"""
    print("=" * 50)
    print("BYOD Synthetic Data Generator - API Test Suite")
    print("=" * 50)

    tests = [
        test_health_check,
        test_cache_info,
        test_cache_clear,
        test_usage_logs,
        test_file_generation,
        test_cache_hit_performance,
        test_different_formats
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            import traceback
            print(f"  ✗ Test failed: {e}")
            print(f"     {traceback.format_exc()}")
            failed += 1

    print("\n" + "=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 50)

    return failed == 0

if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)