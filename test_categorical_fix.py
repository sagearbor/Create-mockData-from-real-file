#!/usr/bin/env python3
"""Test script to verify categorical value preservation."""

import requests
import pandas as pd
import io
import json

# API endpoint
BASE_URL = "http://localhost:8201"

# Sample medical data with gender column
medical_data = """patient_id,age,gender,diagnosis,medication
P001,45,M,Hypertension,Lisinopril
P002,62,F,Diabetes Type 2,Metformin
P003,38,M,Anxiety,Sertraline
P004,55,F,Hypertension,Amlodipine
P005,29,M,Depression,Fluoxetine
P006,71,F,Arthritis,Ibuprofen
P007,42,M,Asthma,Albuterol
P008,58,F,COPD,Tiotropium
P009,33,M,Migraine,Sumatriptan
P010,49,F,Hypothyroidism,Levothyroxine"""

def test_categorical_preservation():
    """Test that categorical values like M/F are preserved in synthetic data."""

    print("=" * 60)
    print("Testing Categorical Value Preservation")
    print("=" * 60)

    # Step 1: Upload the data and extract metadata
    print("\n1. Uploading sample medical data...")

    # Create a file-like object from the CSV string
    files = {
        'file': ('medical_data.csv', medical_data, 'text/csv')
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

    # Check the gender column metadata
    gender_stats = metadata['statistics'].get('gender', {})
    print(f"\n2. Gender column metadata:")
    print(f"   - Type: {gender_stats.get('type')}")
    print(f"   - Unique values: {gender_stats.get('unique_values')}")
    print(f"   - Is categorical: {gender_stats.get('is_categorical')}")
    print(f"   - Preserve values: {gender_stats.get('preserve_values', False)}")

    # Check the actual values
    most_common = gender_stats.get('most_common_values', {})
    print(f"   - Most common values: {most_common}")

    # Step 2: Generate synthetic data
    print("\n3. Generating synthetic data...")

    files = {
        'file': ('medical_data.csv', medical_data, 'text/csv')
    }
    data = {
        'num_rows': 10,
        'preview_only': 'true',
        'output_format': 'csv'
    }

    response = requests.post(f"{BASE_URL}/generate", files=files, data=data)

    if response.status_code != 200:
        print(f"Error generating data: {response.status_code}")
        print(response.text)
        return

    result = response.json()
    preview_data = result['preview']

    # Check the generated gender values
    print(f"\n4. Generated synthetic data preview:")
    print(f"   Total rows: {result['total_rows']}")
    print(f"   Column names: {result['column_names']}")

    # Extract gender values from preview
    gender_values = [row.get('gender', 'N/A') for row in preview_data]
    print(f"\n5. Generated gender values: {gender_values}")

    # Verify the values are M/F and not Category_0/Category_1
    unique_genders = set(gender_values)
    print(f"   Unique values: {unique_genders}")

    if unique_genders.issubset({'M', 'F'}):
        print("\n✅ SUCCESS: Gender values are preserved correctly (M/F)")
    else:
        print("\n❌ FAILURE: Gender values were not preserved correctly")
        print(f"   Expected: M, F")
        print(f"   Got: {unique_genders}")

    # Also check medications
    print("\n6. Checking medication values...")
    medication_values = [row.get('medication', 'N/A') for row in preview_data]
    print(f"   Sample medications: {medication_values[:3]}")

    # Check if medications look realistic
    generic_pattern = any('Category' in med or 'value' in med.lower() for med in medication_values)
    if not generic_pattern:
        print("   ✅ Medications appear realistic")
    else:
        print("   ❌ Medications appear generic")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    test_categorical_preservation()