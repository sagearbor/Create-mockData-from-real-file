#!/usr/bin/env python3
"""Test script to verify enhanced pattern detection for customer data."""

import requests
import pandas as pd
import json

import pytest

# Drives the HTTP API; skipped by tests/conftest.py when no server is up.
pytestmark = pytest.mark.requires_server

# API endpoint
BASE_URL = "http://localhost:8201"

# Sample customer data
customer_data = """customer_id,name,email,phone,city,registration_date,status
C001,John Smith,john.smith@email.com,555-0101,New York,2023-01-15,Active
C002,Jane Doe,jane.doe@email.com,555-0102,Los Angeles,2023-02-20,Active
C003,Bob Johnson,bob.j@email.com,555-0103,Chicago,2023-03-10,Inactive
C004,Alice Brown,alice.b@email.com,555-0104,Houston,2023-04-05,Active
C005,Charlie Wilson,charlie.w@email.com,555-0105,Phoenix,2023-05-12,Active"""

def test_customer_data_patterns():
    """Test that customer data patterns are properly detected and generated."""

    print("=" * 70)
    print("Testing Enhanced Pattern Detection for Customer Data")
    print("=" * 70)

    # Step 1: Upload the data and extract metadata
    print("\n1. Uploading customer data...")

    files = {
        'file': ('customer_data.csv', customer_data, 'text/csv')
    }
    data = {
        'extract_metadata_only': 'true'
    }

    response = requests.post(f"{BASE_URL}/upload", files=files, data=data)

    if response.status_code != 200:
        print(f"Error uploading file: {response.status_code}")
        print(response.text)
        return

    metadata = response.json()['metadata']

    # Check patterns for each column
    print("\n2. Checking detected patterns:")

    for col_name in ['customer_id', 'name', 'email', 'phone', 'city']:
        print(f"\n   {col_name}:")
        col_stats = metadata['statistics'].get(col_name, {})
        patterns = metadata.get('patterns', {}).get(col_name, {})

        # Check specific detections
        if col_name == 'customer_id':
            if patterns.get('id_pattern'):
                print(f"     ✅ ID pattern detected: {patterns['id_pattern']}")
            else:
                print(f"     ❌ No ID pattern detected")
                print(f"     Patterns: {patterns}")

        elif col_name == 'email':
            if col_stats.get('detected_type') == 'email' or col_stats.get('is_email_like'):
                print(f"     ✅ Email pattern detected")
            else:
                print(f"     ❌ Email not detected")

        elif col_name == 'phone':
            if col_stats.get('detected_type') == 'phone' or col_stats.get('is_phone_like'):
                print(f"     ✅ Phone pattern detected (format: {col_stats.get('phone_format', 'unknown')})")
            else:
                print(f"     ❌ Phone not detected")

        elif col_name == 'city':
            if col_stats.get('clinical_context', {}).get('type') == 'city':
                print(f"     ✅ City column detected")
            else:
                print(f"     ℹ️  City detection via column name")

        elif col_name == 'name':
            if col_stats.get('clinical_context', {}).get('type') in ['full_name', 'first_name', 'last_name']:
                print(f"     ✅ Name column detected: {col_stats['clinical_context']['type']}")
            else:
                print(f"     ℹ️  Name detection via column name")

    # Step 3: Generate synthetic data
    print("\n3. Generating synthetic data...")

    files = {
        'file': ('customer_data.csv', customer_data, 'text/csv')
    }
    data = {
        'num_rows': 10,
        'preview_only': 'true'
    }

    response = requests.post(f"{BASE_URL}/generate", files=files, data=data)

    if response.status_code != 200:
        print(f"Error generating data: {response.status_code}")
        print(response.text)
        return

    result = response.json()
    preview_data = result['preview']

    # Check the generated data quality
    print(f"\n4. Generated synthetic data preview:")
    print(f"   Total rows: {result['total_rows']}")

    # Sample the first 3 rows
    print(f"\n   Sample data (first 3 rows):")
    for i, row in enumerate(preview_data[:3]):
        print(f"   Row {i+1}:")
        for key in ['customer_id', 'name', 'email', 'phone', 'city']:
            if key in row:
                print(f"     {key}: {row[key]}")

    # Verify patterns
    print(f"\n5. Verifying generated patterns:")

    # Check customer_id pattern (should start with C)
    customer_ids = [row.get('customer_id', '') for row in preview_data]
    if all(id.startswith('C') for id in customer_ids if id):
        print(f"   ✅ Customer IDs maintain 'C' prefix: {customer_ids[:3]}")
    else:
        print(f"   ❌ Customer IDs don't maintain pattern: {customer_ids[:3]}")

    # Check email format
    emails = [row.get('email', '') for row in preview_data]
    if all('@' in email and '.' in email.split('@')[1] for email in emails if email):
        print(f"   ✅ Emails are properly formatted: {emails[:2]}")
    else:
        print(f"   ❌ Emails are not properly formatted: {emails[:2]}")

    # Check phone format (should be XXX-XXXX format)
    phones = [row.get('phone', '') for row in preview_data]
    if all('-' in phone for phone in phones if phone):
        print(f"   ✅ Phone numbers maintain format: {phones[:2]}")
    else:
        print(f"   ❌ Phone numbers don't maintain format: {phones[:2]}")

    # Check if cities look realistic (not random strings)
    cities = [row.get('city', '') for row in preview_data]
    # Check if they're not just random alphanumeric strings
    realistic_cities = [c for c in cities if c and not (len(c) == 10 and c.isalnum())]
    if len(realistic_cities) > len(cities) * 0.5:
        print(f"   ✅ Cities appear realistic: {cities[:3]}")
    else:
        print(f"   ❌ Cities appear to be random strings: {cities[:3]}")

    # Check if names look realistic
    names = [row.get('name', '') for row in preview_data]
    # Names should have spaces (first + last) and not be random strings
    realistic_names = [n for n in names if n and ' ' in n]
    if len(realistic_names) > len(names) * 0.5:
        print(f"   ✅ Names appear realistic: {names[:2]}")
    else:
        print(f"   ❌ Names appear to be random strings: {names[:2]}")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    test_customer_data_patterns()