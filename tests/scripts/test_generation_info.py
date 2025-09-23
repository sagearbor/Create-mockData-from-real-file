#!/usr/bin/env python3
"""Test script to verify generation_info is returned in API responses."""

import requests
import json
import io

# API base URL
API_BASE = "http://localhost:8201"

def test_generation_with_sample_data():
    """Test generation with sample CSV data."""

    # Create sample CSV data
    csv_data = """name,age,email,city
John Doe,30,john@example.com,New York
Jane Smith,25,jane@example.com,Los Angeles
Bob Johnson,35,bob@example.com,Chicago
Alice Brown,28,alice@example.com,Houston
Mike Davis,32,mike@example.com,Phoenix"""

    # Create file-like object
    files = {
        'file': ('sample.csv', io.BytesIO(csv_data.encode()), 'text/csv')
    }

    data = {
        'num_rows': 10,
        'match_threshold': 0.8,
        'output_format': 'csv',
        'use_cache': True,
        'file_count': 1,
        'preview_only': True
    }

    print("Testing /generate endpoint...")
    response = requests.post(f"{API_BASE}/generate", files=files, data=data)

    if response.status_code == 200:
        result = response.json()
        print(f"✓ Request successful")

        # Check for generation_info
        if 'generation_info' in result:
            gen_info = result['generation_info']
            print(f"✓ generation_info found in response")
            print(f"  - Method: {gen_info.get('method', 'not specified')}")
            print(f"  - Cache used: {gen_info.get('use_cached', 'not specified')}")
            print(f"  - Threshold: {gen_info.get('match_threshold', 'not specified')}")

            # Check method type
            method = gen_info.get('method')
            if method in ['llm', 'cached', 'fallback']:
                print(f"✓ Valid generation method: {method}")
            else:
                print(f"✗ Unexpected generation method: {method}")
        else:
            print("✗ generation_info NOT found in response")
            print("Response keys:", list(result.keys()))

        # Check other expected fields
        if 'preview' in result:
            print(f"✓ Preview data included ({len(result['preview'])} rows)")
        if 'total_rows' in result:
            print(f"✓ Total rows: {result['total_rows']}")
        if 'column_names' in result:
            print(f"✓ Columns: {', '.join(result['column_names'])}")

    else:
        print(f"✗ Request failed with status {response.status_code}")
        print(f"Response: {response.text}")

def test_dictionary_generation():
    """Test generation with dictionary."""

    dictionary = {
        "columns": {
            "customer_id": {
                "type": "string",
                "format": "ID-XXXXX"
            },
            "amount": {
                "type": "float",
                "constraints": {
                    "min_value": 10.0,
                    "max_value": 1000.0
                }
            },
            "status": {
                "type": "string",
                "constraints": {
                    "allowed_values": ["pending", "approved", "rejected"]
                }
            }
        }
    }

    files = {
        'dictionary_file': ('dict.json', io.BytesIO(json.dumps(dictionary).encode()), 'application/json')
    }

    data = {
        'num_rows': 5,
        'output_format': 'json',
        'file_count': 1,
        'preview_only': True
    }

    print("\nTesting /generate-with-dictionary endpoint...")
    response = requests.post(f"{API_BASE}/generate-with-dictionary", files=files, data=data)

    if response.status_code == 200:
        result = response.json()
        print(f"✓ Request successful")

        # Check for generation_info
        if 'generation_info' in result:
            gen_info = result['generation_info']
            print(f"✓ generation_info found in response")
            print(f"  - Method: {gen_info.get('method', 'not specified')}")
        else:
            print("✗ generation_info NOT found in response")

        # Check dictionary_applied flag
        if result.get('dictionary_applied'):
            print(f"✓ Dictionary constraints applied")

    else:
        print(f"✗ Request failed with status {response.status_code}")

if __name__ == "__main__":
    print("=" * 50)
    print("Testing Generation Info in API Responses")
    print("=" * 50)

    try:
        # Test connection
        response = requests.get(f"{API_BASE}/health")
        if response.status_code == 200:
            print("✓ Server is running\n")
        else:
            print("✗ Server health check failed")
            exit(1)
    except requests.exceptions.ConnectionError:
        print("✗ Cannot connect to server at", API_BASE)
        print("Make sure the server is running: python main.py")
        exit(1)

    test_generation_with_sample_data()
    test_dictionary_generation()

    print("\n" + "=" * 50)
    print("Test complete!")