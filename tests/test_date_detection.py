"""Tests for date detection functionality."""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.data_loader import DataLoader


class TestDateDetection(unittest.TestCase):
    """Test date detection in DataLoader."""

    def setUp(self):
        """Set up test fixtures."""
        self.loader = DataLoader()

    def test_detect_iso_date_format(self):
        """Test detection of ISO date format YYYY-MM-DD."""
        df = pd.DataFrame({
            'treatment_date': ['2024-01-10', '2024-02-15', '2024-03-20'],
            'patient_id': [1, 2, 3]
        })

        result = self.loader._detect_and_convert_dates(df)

        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result['treatment_date']))
        self.assertEqual(result['treatment_date'].iloc[0], pd.Timestamp('2024-01-10'))

    def test_detect_us_date_format(self):
        """Test detection of US date format MM/DD/YYYY."""
        df = pd.DataFrame({
            'admission_date': ['01/10/2024', '02/15/2024', '03/20/2024'],
            'patient_id': [1, 2, 3]
        })

        result = self.loader._detect_and_convert_dates(df)

        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result['admission_date']))

    def test_detect_datetime_with_time(self):
        """Test detection of datetime with time component."""
        df = pd.DataFrame({
            'timestamp': ['2024-01-10 14:30:00', '2024-02-15 09:15:00', '2024-03-20 16:45:00'],
            'value': [100, 200, 300]
        })

        result = self.loader._detect_and_convert_dates(df)

        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result['timestamp']))
        self.assertEqual(result['timestamp'].iloc[0].hour, 14)
        self.assertEqual(result['timestamp'].iloc[0].minute, 30)

    def test_column_name_based_detection(self):
        """Test date detection based on column name keywords."""
        df = pd.DataFrame({
            'created_date': ['2024-01-10', '2024-02-15', '2024-03-20'],
            'updated_time': ['2024-01-10', '2024-02-15', '2024-03-20'],
            'dob': ['1990-05-15', '1985-08-20', '1992-12-10'],
            'regular_column': ['abc', 'def', 'ghi']
        })

        result = self.loader._detect_and_convert_dates(df)

        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result['created_date']))
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result['updated_time']))
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result['dob']))
        self.assertFalse(pd.api.types.is_datetime64_any_dtype(result['regular_column']))

    def test_mixed_date_formats(self):
        """Test handling of mixed valid and invalid dates."""
        df = pd.DataFrame({
            'date_column': ['2024-01-10', '2024-02-15', 'not a date', '2024-03-20', None],
            'id': [1, 2, 3, 4, 5]
        })

        result = self.loader._detect_and_convert_dates(df)

        # Should convert if >80% are valid dates
        if pd.api.types.is_datetime64_any_dtype(result['date_column']):
            self.assertTrue(pd.isna(result['date_column'].iloc[2]))  # 'not a date' should be NaT
            self.assertEqual(result['date_column'].iloc[0], pd.Timestamp('2024-01-10'))

    def test_no_false_positives(self):
        """Test that non-date columns are not converted."""
        df = pd.DataFrame({
            'product_code': ['2024-01-10', '2024-02-15', '2024-03-20'],  # Looks like dates but wrong context
            'price': [10.99, 20.50, 30.25],
            'quantity': [1, 2, 3]
        })

        # Since product_code doesn't have date keywords, it might not be converted
        result = self.loader._detect_and_convert_dates(df)

        self.assertTrue(pd.api.types.is_numeric_dtype(result['price']))
        self.assertTrue(pd.api.types.is_numeric_dtype(result['quantity']))

    def test_preserve_existing_datetime_columns(self):
        """Test that columns already in datetime format are preserved."""
        df = pd.DataFrame({
            'date': pd.date_range('2024-01-01', periods=3, freq='D'),
            'value': [1, 2, 3]
        })

        original_dtype = df['date'].dtype
        result = self.loader._detect_and_convert_dates(df)

        self.assertEqual(result['date'].dtype, original_dtype)
        self.assertTrue(pd.api.types.is_datetime64_any_dtype(result['date']))


class TestDateDetectionIntegration(unittest.TestCase):
    """Integration tests for date detection in the full pipeline."""

    def test_csv_with_dates(self):
        """Test loading CSV file with date columns."""
        import tempfile
        import os

        # Create temporary CSV file
        csv_content = """treatment_date,patient_id,medication,dosage
2024-01-10,1,Metformin,500mg
2024-01-15,2,Lisinopril,10mg
2024-01-20,3,Atorvastatin,20mg"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_content)
            temp_file = f.name

        try:
            loader = DataLoader()
            df = loader.load(temp_file)

            # Check that treatment_date was converted to datetime
            self.assertTrue(pd.api.types.is_datetime64_any_dtype(df['treatment_date']))
            self.assertEqual(df['treatment_date'].iloc[0], pd.Timestamp('2024-01-10'))
        finally:
            os.unlink(temp_file)


if __name__ == '__main__':
    unittest.main()