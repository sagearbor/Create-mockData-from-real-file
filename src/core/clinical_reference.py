"""Clinical reference data library for generating meaningful mock medical data."""

import pandas as pd
from typing import Dict, List, Any, Optional
import random
from pathlib import Path
import json

class ClinicalReferenceLibrary:
    """Provides clinical reference data for realistic synthetic data generation."""

    def __init__(self):
        """Initialize with common clinical reference data."""
        self.medications = self._load_medications()
        self.lab_tests = self._load_lab_tests()
        self.units = self._load_units()
        self.diagnoses = self._load_diagnoses()
        self.procedures = self._load_procedures()
        self.body_sites = self._load_body_sites()
        self.clinical_terms = self._load_clinical_terms()

    def _load_medications(self) -> List[str]:
        """Load common medication names."""
        return [
            # Pain relievers
            "Acetaminophen", "Ibuprofen", "Aspirin", "Naproxen", "Morphine",
            "Oxycodone", "Tramadol", "Codeine", "Gabapentin", "Pregabalin",

            # Antibiotics
            "Amoxicillin", "Azithromycin", "Ciprofloxacin", "Doxycycline",
            "Cephalexin", "Metronidazole", "Clindamycin", "Levofloxacin",
            "Penicillin", "Vancomycin",

            # Cardiovascular
            "Metoprolol", "Lisinopril", "Amlodipine", "Atorvastatin",
            "Simvastatin", "Losartan", "Hydrochlorothiazide", "Furosemide",
            "Warfarin", "Clopidogrel", "Aspirin", "Digoxin",

            # Diabetes
            "Metformin", "Insulin glargine", "Insulin lispro", "Glipizide",
            "Glyburide", "Sitagliptin", "Empagliflozin", "Liraglutide",

            # Mental health
            "Sertraline", "Escitalopram", "Fluoxetine", "Duloxetine",
            "Venlafaxine", "Bupropion", "Trazodone", "Alprazolam",
            "Lorazepam", "Clonazepam", "Diazepam", "Risperidone",

            # Gastrointestinal
            "Omeprazole", "Pantoprazole", "Ranitidine", "Famotidine",
            "Ondansetron", "Metoclopramide", "Loperamide", "Docusate",

            # Respiratory
            "Albuterol", "Budesonide", "Fluticasone", "Montelukast",
            "Prednisone", "Methylprednisolone", "Dexamethasone",

            # Other common
            "Levothyroxine", "Vitamin D", "Folic acid", "Iron sulfate",
            "Potassium chloride", "Calcium carbonate", "Magnesium oxide"
        ]

    def _load_lab_tests(self) -> List[str]:
        """Load common laboratory test names."""
        return [
            # Blood counts
            "WBC", "RBC", "Hemoglobin", "Hematocrit", "Platelet count",
            "Neutrophils", "Lymphocytes", "Monocytes", "Eosinophils", "Basophils",

            # Chemistry panel
            "Glucose", "BUN", "Creatinine", "eGFR", "Sodium", "Potassium",
            "Chloride", "CO2", "Calcium", "Total protein", "Albumin",
            "Total bilirubin", "ALT", "AST", "Alkaline phosphatase",

            # Lipid panel
            "Total cholesterol", "LDL cholesterol", "HDL cholesterol", "Triglycerides",

            # Cardiac markers
            "Troponin", "BNP", "CK-MB", "Myoglobin", "D-dimer",

            # Thyroid
            "TSH", "Free T4", "Free T3", "Total T4", "Total T3",

            # Diabetes
            "HbA1c", "Fasting glucose", "Random glucose", "C-peptide",

            # Inflammation
            "CRP", "ESR", "Ferritin", "Procalcitonin",

            # Vitamins and minerals
            "Vitamin B12", "Vitamin D", "Folate", "Iron", "TIBC",

            # Urinalysis
            "Urine protein", "Urine glucose", "Urine specific gravity",
            "Urine pH", "Urine ketones", "Urine blood",

            # Coagulation
            "PT", "PTT", "INR", "Fibrinogen"
        ]

    def _load_units(self) -> Dict[str, List[str]]:
        """Load common medical units grouped by category."""
        return {
            "weight": ["mg", "g", "kg", "mcg", "lb", "oz"],
            "volume": ["mL", "L", "dL", "mcL", "cc"],
            "concentration": ["mg/dL", "g/dL", "mmol/L", "mEq/L", "ng/mL", "pg/mL", "mcg/mL", "IU/mL"],
            "rate": ["mg/hr", "mL/hr", "mcg/min", "units/hr", "gtt/min"],
            "count": ["cells/mcL", "x10^9/L", "x10^6/mcL", "/hpf", "/lpf"],
            "percentage": ["%", "percent"],
            "time": ["seconds", "minutes", "hours", "days", "weeks", "months", "years"],
            "temperature": ["°C", "°F", "Celsius", "Fahrenheit"],
            "pressure": ["mmHg", "cmH2O", "kPa"],
            "dosage": ["tablet", "capsule", "mL", "mg", "mcg", "units", "puffs", "drops"],
            "frequency": ["daily", "BID", "TID", "QID", "q4h", "q6h", "q8h", "q12h", "PRN", "weekly", "monthly"]
        }

    def _load_diagnoses(self) -> List[str]:
        """Load common diagnosis codes and descriptions."""
        return [
            # Cardiovascular
            "Hypertension", "Hyperlipidemia", "Coronary artery disease",
            "Atrial fibrillation", "Heart failure", "Myocardial infarction",

            # Respiratory
            "Asthma", "COPD", "Pneumonia", "Bronchitis", "Upper respiratory infection",
            "COVID-19", "Influenza", "Sleep apnea",

            # Endocrine
            "Type 2 diabetes mellitus", "Type 1 diabetes mellitus",
            "Hypothyroidism", "Hyperthyroidism", "Obesity",

            # Gastrointestinal
            "GERD", "Peptic ulcer disease", "Irritable bowel syndrome",
            "Crohn's disease", "Ulcerative colitis", "Gastroenteritis",

            # Neurological
            "Migraine", "Seizure disorder", "Stroke", "Parkinson's disease",
            "Alzheimer's disease", "Multiple sclerosis",

            # Psychiatric
            "Major depressive disorder", "Anxiety disorder", "Bipolar disorder",
            "PTSD", "ADHD", "Schizophrenia",

            # Musculoskeletal
            "Osteoarthritis", "Rheumatoid arthritis", "Osteoporosis",
            "Lower back pain", "Fibromyalgia",

            # Renal
            "Chronic kidney disease", "Acute kidney injury", "UTI",

            # Other
            "Anemia", "Cancer", "Pregnancy", "Allergic rhinitis"
        ]

    def _load_procedures(self) -> List[str]:
        """Load common medical procedures."""
        return [
            "Physical examination", "Blood draw", "IV insertion",
            "ECG", "Chest X-ray", "CT scan", "MRI", "Ultrasound",
            "Colonoscopy", "Endoscopy", "Bronchoscopy", "Biopsy",
            "Cardiac catheterization", "Angioplasty", "CABG",
            "Appendectomy", "Cholecystectomy", "Hernia repair",
            "Joint replacement", "Fracture repair", "Wound care",
            "Dialysis", "Chemotherapy", "Radiation therapy",
            "Vaccination", "Injection", "Infusion", "Transfusion"
        ]

    def _load_body_sites(self) -> List[str]:
        """Load common body sites/anatomical locations."""
        return [
            "Head", "Neck", "Chest", "Abdomen", "Back", "Pelvis",
            "Right arm", "Left arm", "Right leg", "Left leg",
            "Right hand", "Left hand", "Right foot", "Left foot",
            "Heart", "Lungs", "Liver", "Kidneys", "Brain", "Spine",
            "Stomach", "Intestines", "Bladder", "Skin"
        ]

    def _load_clinical_terms(self) -> Dict[str, List[str]]:
        """Load various clinical terminology."""
        return {
            "severity": ["Mild", "Moderate", "Severe", "Critical"],
            "status": ["Active", "Resolved", "Chronic", "Acute", "Stable", "Unstable"],
            "admission_type": ["Emergency", "Elective", "Urgent", "Routine"],
            "discharge_disposition": ["Home", "SNF", "Rehab", "AMA", "Expired", "Transfer"],
            "gender": ["Male", "Female", "Other", "Unknown"],
            "blood_type": ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"],
            "allergy_severity": ["Mild", "Moderate", "Severe", "Life-threatening"],
            "pain_scale": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
            "glasgow_coma": ["3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15"]
        }

    def get_random_medications(self, n: int = 1) -> List[str]:
        """Get random medication names."""
        return random.sample(self.medications, min(n, len(self.medications)))

    def get_random_lab_tests(self, n: int = 1) -> List[str]:
        """Get random lab test names."""
        return random.sample(self.lab_tests, min(n, len(self.lab_tests)))

    def get_random_diagnoses(self, n: int = 1) -> List[str]:
        """Get random diagnosis names."""
        return random.sample(self.diagnoses, min(n, len(self.diagnoses)))

    def get_units_for_category(self, category: str) -> List[str]:
        """Get units for a specific category."""
        return self.units.get(category, [])

    def get_random_units(self, category: Optional[str] = None) -> str:
        """Get a random unit, optionally from a specific category."""
        if category and category in self.units:
            return random.choice(self.units[category])
        all_units = [unit for units in self.units.values() for unit in units]
        return random.choice(all_units)

    def detect_clinical_column_type(self, column_name: str) -> Optional[Dict[str, Any]]:
        """
        Detect if a column name represents clinical data and suggest appropriate values.

        Args:
            column_name: Name of the column

        Returns:
            Dictionary with detected type and suggested values, or None if not clinical
        """
        col_lower = column_name.lower()

        # Medication-related
        medication_keywords = ['medication', 'drug', 'medicine', 'rx', 'prescription', 'med']
        if any(keyword in col_lower for keyword in medication_keywords):
            return {
                "type": "medication",
                "suggested_values": self.get_random_medications(20),
                "category": "clinical"
            }

        # Lab test-related
        lab_keywords = ['lab', 'test', 'wbc', 'rbc', 'glucose', 'creatinine', 'hemoglobin']
        if any(keyword in col_lower for keyword in lab_keywords):
            return {
                "type": "lab_test",
                "suggested_values": self.get_random_lab_tests(20),
                "category": "clinical"
            }

        # Unit-related
        unit_keywords = ['unit', 'dose', 'dosage', 'amount', 'concentration']
        if any(keyword in col_lower for keyword in unit_keywords):
            return {
                "type": "unit",
                "suggested_values": self.get_random_units(),
                "category": "clinical"
            }

        # Diagnosis-related
        diagnosis_keywords = ['diagnosis', 'disease', 'condition', 'disorder', 'icd']
        if any(keyword in col_lower for keyword in diagnosis_keywords):
            return {
                "type": "diagnosis",
                "suggested_values": self.get_random_diagnoses(20),
                "category": "clinical"
            }

        # Procedure-related
        procedure_keywords = ['procedure', 'surgery', 'operation', 'treatment']
        if any(keyword in col_lower for keyword in procedure_keywords):
            return {
                "type": "procedure",
                "suggested_values": random.sample(self.procedures, min(20, len(self.procedures))),
                "category": "clinical"
            }

        # Body site-related
        site_keywords = ['site', 'location', 'anatomy', 'body_part']
        if any(keyword in col_lower for keyword in site_keywords):
            return {
                "type": "body_site",
                "suggested_values": random.sample(self.body_sites, min(10, len(self.body_sites))),
                "category": "clinical"
            }

        # Check specific clinical terms
        for term_type, values in self.clinical_terms.items():
            if term_type in col_lower:
                return {
                    "type": term_type,
                    "suggested_values": values,
                    "category": "clinical"
                }

        return None

    def enhance_metadata_with_clinical_context(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enhance metadata with clinical context for better synthetic data generation.

        Args:
            metadata: Original metadata dictionary

        Returns:
            Enhanced metadata with clinical suggestions
        """
        if "statistics" in metadata:
            for column_name, column_stats in metadata["statistics"].items():
                clinical_context = self.detect_clinical_column_type(column_name)
                if clinical_context:
                    column_stats["clinical_context"] = clinical_context
                    # Add to metadata for LLM to use
                    if column_stats.get("type") == "string" and clinical_context.get("suggested_values"):
                        column_stats["suggested_values"] = clinical_context["suggested_values"][:10]
                        column_stats["is_clinical"] = True

        return metadata

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert reference library to a DataFrame for analysis.

        Returns:
            DataFrame with all reference data
        """
        data = {
            "medications": pd.DataFrame({"value": self.medications, "type": "medication"}),
            "lab_tests": pd.DataFrame({"value": self.lab_tests, "type": "lab_test"}),
            "diagnoses": pd.DataFrame({"value": self.diagnoses, "type": "diagnosis"}),
            "procedures": pd.DataFrame({"value": self.procedures, "type": "procedure"}),
            "body_sites": pd.DataFrame({"value": self.body_sites, "type": "body_site"})
        }

        # Combine all DataFrames
        combined_df = pd.concat(data.values(), ignore_index=True)
        return combined_df

    def save_to_json(self, file_path: Path):
        """Save reference library to JSON file."""
        data = {
            "medications": self.medications,
            "lab_tests": self.lab_tests,
            "units": self.units,
            "diagnoses": self.diagnoses,
            "procedures": self.procedures,
            "body_sites": self.body_sites,
            "clinical_terms": self.clinical_terms
        }
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

    def load_from_json(self, file_path: Path):
        """Load reference library from JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        self.medications = data.get("medications", [])
        self.lab_tests = data.get("lab_tests", [])
        self.units = data.get("units", {})
        self.diagnoses = data.get("diagnoses", [])
        self.procedures = data.get("procedures", [])
        self.body_sites = data.get("body_sites", [])
        self.clinical_terms = data.get("clinical_terms", {})