#!/usr/bin/env python3
"""Test script to verify financial data improvements."""

import requests
import json

import pytest

# Drives the HTTP API; skipped by tests/conftest.py when no server is up.
pytestmark = pytest.mark.requires_server

# API endpoint
BASE_URL = "http://localhost:8201"

# Sample financial data with timestamps and currency amounts
financial_data = """transaction_id,date,account_from,account_to,amount,currency,type,status
T001,2024-01-15 09:30:00,ACC001,ACC002,1500.00,USD,Transfer,Completed
T002,2024-01-15 10:15:00,ACC003,ACC001,250.50,USD,Payment,Completed
T003,2024-01-15 11:00:00,ACC002,ACC004,3200.00,USD,Wire,Pending
T004,2024-01-15 14:30:00,ACC005,ACC003,750.25,USD,Transfer,Completed
T005,2024-01-16 08:45:00,ACC001,ACC005,425.00,USD,Payment,Failed"""

def test_financial_patterns():
    """Test datetime, currency, and categorical detection in financial data."""

    print("=" * 70)
    print("Testing Financial Data Pattern Detection")
    print("=" * 70)

    # Test with different safety modes
    for safety_mode in ["strict", "balanced", "permissive"]:
        print(f"\n{'='*30} {safety_mode.upper()} MODE {'='*30}")

        files = {
            'file': ('financial_data.csv', financial_data, 'text/csv')
        }
        data = {
            'num_rows': 10,
            'preview_only': 'true',
            'safety_mode': safety_mode
        }

        response = requests.post(f"{BASE_URL}/generate", files=files, data=data)

        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            continue

        result = response.json()
        preview_data = result['preview']

        print(f"\nGenerated {len(preview_data)} rows")

        # Check first 2 rows
        for i, row in enumerate(preview_data[:2]):
            print(f"\nRow {i+1}:")

            # Check date field
            date_val = row.get('date', 'N/A')
            has_time = ':' in str(date_val)
            print(f"  date: {date_val} {'✅ Has time' if has_time else '❌ No time component'}")

            # Check amount field
            amount_val = row.get('amount', 'N/A')
            # Check if it has proper decimal places (should be 2 for currency)
            if isinstance(amount_val, (int, float)):
                decimal_str = f"{amount_val:.10f}"
                if '.' in decimal_str:
                    decimal_part = decimal_str.split('.')[1].rstrip('0')
                    if len(decimal_part) <= 2:
                        print(f"  amount: {amount_val:.2f} ✅ Proper currency format")
                    else:
                        print(f"  amount: {amount_val} ❌ Too many decimals")
                else:
                    print(f"  amount: {amount_val} ✅ Whole dollar amount")

            # Check type field
            type_val = row.get('type', 'N/A')
            if type_val in ['Transfer', 'Payment', 'Wire']:
                print(f"  type: {type_val} ✅ Preserved categorical value")
            else:
                print(f"  type: {type_val} ❌ Not preserved")

            # Check status field
            status_val = row.get('status', 'N/A')
            if status_val in ['Completed', 'Pending', 'Failed']:
                print(f"  status: {status_val} ✅ Preserved categorical value")
            else:
                print(f"  status: {status_val} ❌ Not preserved")

    print("\n" + "=" * 70)

if __name__ == "__main__":
    test_financial_patterns()