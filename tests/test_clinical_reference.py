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
        """Columns matching no reference category return None."""
        for column in ('price', 'widget_sku', 'order_total'):
            self.assertIsNone(
                self.library.detect_clinical_column_type(column),
                f"{column} should not match any reference category",
            )

    def test_person_name_column_is_personal_not_clinical(self):
        """Name columns are recognised, but as personal reference data."""
        result = self.library.detect_clinical_column_type('customer_name')

        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'full_name')
        self.assertEqual(result['category'], 'personal')

    def test_clinical_name_columns_beat_the_generic_name_keyword(self):
        """'<clinical>_name' must resolve to the clinical type, not a person.

        The generic 'name' keyword used to be checked first, so a
        medication_name / diagnosis_name / procedure_name column was filled
        with people's names.
        """
        expected = {
            'medication_name': 'medication',
            'lab_test_name': 'lab_test',
            'diagnosis_name': 'diagnosis',
            'procedure_name': 'procedure',
        }
        for column, expected_type in expected.items():
            result = self.library.detect_clinical_column_type(column)
            self.assertIsNotNone(result, f"{column} was not detected")
            self.assertEqual(result['type'], expected_type, f"for column {column}")
            self.assertEqual(result['category'], 'clinical', f"for column {column}")

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

        # A person-name column is reference data, but it is not clinical
        patient_name = enhanced['statistics']['patient_name']
        self.assertNotIn('clinical_context', patient_name)
        self.assertFalse(patient_name.get('is_clinical', False))
        # ...it still gets values so the generator can produce realistic names
        self.assertIn('suggested_values', patient_name)

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