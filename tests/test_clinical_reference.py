"""Tests for clinical reference data library."""

import unittest
import pandas as pd
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.clinical_reference import ClinicalReferenceLibrary
from src.core.metadata_extractor import MetadataExtractor


class TestClinicalReferenceLibrary(unittest.TestCase):
    """Test clinical reference data functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.library = ClinicalReferenceLibrary()

    def test_medications_loaded(self):
        """Test that medications are properly loaded."""
        self.assertGreater(len(self.library.medications), 50)
        self.assertIn('Metformin', self.library.medications)
        self.assertIn('Aspirin', self.library.medications)
        self.assertIn('Lisinopril', self.library.medications)

    def test_lab_tests_loaded(self):
        """Test that lab tests are properly loaded."""
        self.assertGreater(len(self.library.lab_tests), 30)
        self.assertIn('WBC', self.library.lab_tests)
        self.assertIn('Glucose', self.library.lab_tests)
        self.assertIn('Hemoglobin', self.library.lab_tests)

    def test_units_loaded(self):
        """Test that units are properly loaded and categorized."""
        self.assertIn('weight', self.library.units)
        self.assertIn('volume', self.library.units)
        self.assertIn('mg', self.library.units['weight'])
        self.assertIn('mL', self.library.units['volume'])
        self.assertIn('mg/dL', self.library.units['concentration'])

    def test_diagnoses_loaded(self):
        """Test that diagnoses are properly loaded."""
        self.assertGreater(len(self.library.diagnoses), 20)
        self.assertIn('Hypertension', self.library.diagnoses)
        self.assertIn('Type 2 diabetes mellitus', self.library.diagnoses)

    def test_detect_medication_column(self):
        """Test detection of medication columns."""
        result = self.library.detect_clinical_column_type('medication_name')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'medication')
        self.assertIn('suggested_values', result)
        # Check that values are from the medications list
        self.assertTrue(all(val in self.library.medications for val in result['suggested_values']))

    def test_detect_lab_test_column(self):
        """Test detection of lab test columns."""
        result = self.library.detect_clinical_column_type('lab_test_name')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'lab_test')

        # Also test specific lab names
        result = self.library.detect_clinical_column_type('wbc_count')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'lab_test')

    def test_detect_unit_column(self):
        """Test detection of unit columns."""
        result = self.library.detect_clinical_column_type('dosage_unit')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'unit')

    def test_detect_diagnosis_column(self):
        """Test detection of diagnosis columns."""
        result = self.library.detect_clinical_column_type('primary_diagnosis')
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'diagnosis')

    def test_detect_non_clinical_column(self):
        """Test that non-clinical columns return None."""
        result = self.library.detect_clinical_column_type('customer_name')
        self.assertIsNone(result)

        result = self.library.detect_clinical_column_type('price')
        self.assertIsNone(result)

    def test_get_random_medications(self):
        """Test getting random medications."""
        meds = self.library.get_random_medications(5)
        self.assertEqual(len(meds), 5)
        self.assertTrue(all(med in self.library.medications for med in meds))

        # Test with more than available
        meds = self.library.get_random_medications(1000)
        self.assertEqual(len(meds), len(self.library.medications))

    def test_get_units_for_category(self):
        """Test getting units for specific category."""
        weight_units = self.library.get_units_for_category('weight')
        self.assertIn('mg', weight_units)
        self.assertIn('kg', weight_units)

        volume_units = self.library.get_units_for_category('volume')
        self.assertIn('mL', volume_units)
        self.assertIn('L', volume_units)

    def test_enhance_metadata_with_clinical_context(self):
        """Test enhancing metadata with clinical context."""
        metadata = {
            "statistics": {
                "medication_name": {
                    "type": "string",
                    "unique_values": 10
                },
                "lab_value": {
                    "type": "numeric",
                    "mean": 100
                },
                "patient_name": {
                    "type": "string",
                    "unique_values": 50
                }
            }
        }

        enhanced = self.library.enhance_metadata_with_clinical_context(metadata)

        # Check medication column was enhanced
        self.assertIn('clinical_context', enhanced['statistics']['medication_name'])
        self.assertIn('suggested_values', enhanced['statistics']['medication_name'])
        self.assertTrue(enhanced['statistics']['medication_name']['is_clinical'])

        # Check non-clinical column was not enhanced
        self.assertNotIn('clinical_context', enhanced['statistics']['patient_name'])

    def test_to_dataframe(self):
        """Test conversion to DataFrame."""
        df = self.library.to_dataframe()
        self.assertIsInstance(df, pd.DataFrame)
        self.assertIn('value', df.columns)
        self.assertIn('type', df.columns)

        # Check that all types are present
        types = df['type'].unique()
        self.assertIn('medication', types)
        self.assertIn('lab_test', types)
        self.assertIn('diagnosis', types)


class TestClinicalIntegration(unittest.TestCase):
    """Integration tests for clinical reference with metadata extraction."""

    def test_metadata_extractor_with_clinical_data(self):
        """Test that MetadataExtractor uses clinical reference properly."""
        df = pd.DataFrame({
            'patient_id': [1, 2, 3],
            'medication': ['Aspirin', 'Metformin', 'Lisinopril'],
            'dosage': [100, 500, 10],
            'unit': ['mg', 'mg', 'mg'],
            'lab_test': ['WBC', 'Glucose', 'Hemoglobin'],
            'lab_value': [7.5, 120, 14.5]
        })

        extractor = MetadataExtractor(use_clinical_reference=True)
        metadata = extractor.extract(df)

        # Check that medication column has clinical context
        if 'medication' in metadata['statistics']:
            med_stats = metadata['statistics']['medication']
            if 'clinical_context' in med_stats:
                self.assertEqual(med_stats['clinical_context']['type'], 'medication')
                self.assertTrue(med_stats.get('is_clinical', False))

        # Check that lab_test column has clinical context
        if 'lab_test' in metadata['statistics']:
            lab_stats = metadata['statistics']['lab_test']
            if 'clinical_context' in lab_stats:
                self.assertEqual(lab_stats['clinical_context']['type'], 'lab_test')

    def test_metadata_extractor_without_clinical_reference(self):
        """Test that MetadataExtractor works without clinical reference."""
        df = pd.DataFrame({
            'patient_id': [1, 2, 3],
            'medication': ['Aspirin', 'Metformin', 'Lisinopril'],
            'dosage': [100, 500, 10]
        })

        extractor = MetadataExtractor(use_clinical_reference=False)
        metadata = extractor.extract(df)

        # Check that clinical context is not added
        med_stats = metadata['statistics']['medication']
        self.assertNotIn('clinical_context', med_stats)
        self.assertNotIn('is_clinical', med_stats)


if __name__ == '__main__':
    unittest.main()