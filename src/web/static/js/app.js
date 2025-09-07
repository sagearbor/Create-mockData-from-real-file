// BYOD Synthetic Data Generator - Frontend Application

// Use the current origin (works with any port)
const API_BASE = window.location.origin;
let currentFile = null;
let currentMetadata = null;

// DOM Elements
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const fileStats = document.getElementById('fileStats');
const configSection = document.getElementById('configSection');
const resultsSection = document.getElementById('resultsSection');
const resultsContent = document.getElementById('resultsContent');
const metadataSection = document.getElementById('metadataSection');
const metadataContent = document.getElementById('metadataContent');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingMessage = document.getElementById('loadingMessage');
const errorModal = document.getElementById('errorModal');
const errorMessage = document.getElementById('errorMessage');

// Buttons
const generateBtn = document.getElementById('generateBtn');
const extractMetadataBtn = document.getElementById('extractMetadataBtn');
const downloadBtn = document.getElementById('downloadBtn');
const resetBtn = document.getElementById('resetBtn');

// Form inputs
const numRows = document.getElementById('numRows');
const matchThreshold = document.getElementById('matchThreshold');
const thresholdValue = document.getElementById('thresholdValue');
const outputFormat = document.getElementById('outputFormat');
const useCache = document.getElementById('useCache');

// Initialize event listeners
function init() {
    // File upload
    uploadArea.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileSelect);
    
    // Drag and drop
    uploadArea.addEventListener('dragover', handleDragOver);
    uploadArea.addEventListener('dragleave', handleDragLeave);
    uploadArea.addEventListener('drop', handleDrop);
    
    // Threshold slider
    matchThreshold.addEventListener('input', (e) => {
        thresholdValue.textContent = `${e.target.value}%`;
    });
    
    // Buttons
    generateBtn.addEventListener('click', generateSyntheticData);
    extractMetadataBtn.addEventListener('click', extractMetadata);
    resetBtn.addEventListener('click', reset);
    
    // Demo buttons
    document.querySelectorAll('.demo-btn').forEach(btn => {
        btn.addEventListener('click', loadDemoData);
    });
}

// File handling
function handleFileSelect(e) {
    const file = e.target.files[0];
    if (file) {
        processFile(file);
    }
}

function handleDragOver(e) {
    e.preventDefault();
    uploadArea.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
}

function handleDrop(e) {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    
    const file = e.dataTransfer.files[0];
    if (file) {
        processFile(file);
    }
}

function processFile(file) {
    currentFile = file;
    fileName.textContent = file.name;
    fileStats.textContent = `Size: ${formatFileSize(file.size)} | Type: ${file.type || 'Unknown'}`;
    
    fileInfo.style.display = 'block';
    configSection.style.display = 'block';
    resultsSection.style.display = 'none';
    metadataSection.style.display = 'none';
}

// API calls
async function generateSyntheticData() {
    if (!currentFile && !window.currentEditedData) {
        showError('Please upload a file first');
        return;
    }
    
    showLoading('Generating synthetic data...');
    
    const formData = new FormData();
    
    // If data was edited, send the edited version as CSV
    if (window.currentEditedData) {
        const csv = convertToCSV(window.currentEditedData);
        formData.append('edited_data', csv);
    } else {
        formData.append('file', currentFile);
    }
    
    formData.append('num_rows', numRows.value || '');
    formData.append('match_threshold', matchThreshold.value / 100);
    formData.append('output_format', outputFormat.value);
    formData.append('use_cache', useCache.checked);
    
    try {
        const response = await fetch(`${API_BASE}/generate`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Generation failed');
        }
        
        // Handle different response types
        const contentType = response.headers.get('content-type');
        
        if (contentType.includes('application/json')) {
            const data = await response.json();
            displayResults(data);
        } else {
            // File download
            const blob = await response.blob();
            downloadFile(blob, `synthetic_data.${outputFormat.value}`);
            displayResults({
                status: 'success',
                message: 'Synthetic data generated successfully!'
            });
        }
        
    } catch (error) {
        const errorMsg = error.message || (typeof error === 'object' ? JSON.stringify(error) : String(error));
        showError(errorMsg || 'An unexpected error occurred');
    } finally {
        hideLoading();
    }
}

async function extractMetadata() {
    if (!currentFile) {
        showError('Please upload a file first');
        return;
    }
    
    showLoading('Extracting metadata...');
    
    const formData = new FormData();
    formData.append('file', currentFile);
    
    try {
        const response = await fetch(`${API_BASE}/metadata`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Metadata extraction failed');
        }
        
        const data = await response.json();
        currentMetadata = data.metadata;
        displayMetadata(data.metadata);
        
    } catch (error) {
        const errorMsg = error.message || (typeof error === 'object' ? JSON.stringify(error) : String(error));
        showError(errorMsg || 'An unexpected error occurred');
    } finally {
        hideLoading();
    }
}

// Display functions
function displayResults(data) {
    resultsSection.style.display = 'block';
    
    if (data.status === 'success') {
        let html = '<div class="success-message">';
        html += '<h3>✅ Synthetic Data Generated Successfully!</h3>';
        
        if (data.shape) {
            html += `<p>Generated ${data.shape[0]} rows × ${data.shape[1]} columns</p>`;
        }
        
        if (data.columns) {
            html += '<h4>Columns:</h4>';
            html += '<ul>';
            data.columns.forEach(col => {
                html += `<li>${col}</li>`;
            });
            html += '</ul>';
        }
        
        if (data.data) {
            html += '<h4>Preview (first 5 rows):</h4>';
            html += '<div style="overflow-x: auto;">';
            html += createTableFromJSON(data.data.slice(0, 5));
            html += '</div>';
        }
        
        html += '</div>';
        resultsContent.innerHTML = html;
        
        if (data.data) {
            // Enable download for JSON data
            downloadBtn.style.display = 'block';
            downloadBtn.onclick = () => {
                const blob = new Blob([JSON.stringify(data.data, null, 2)], {type: 'application/json'});
                downloadFile(blob, 'synthetic_data.json');
            };
        }
    } else {
        resultsContent.innerHTML = `<p>${data.message || 'Generation completed'}</p>`;
    }
}

function displayMetadata(metadata) {
    metadataSection.style.display = 'block';
    metadataContent.textContent = JSON.stringify(metadata, null, 2);
    
    // Also show summary in results
    resultsSection.style.display = 'block';
    
    let html = '<div class="metadata-summary">';
    html += '<h3>📊 Metadata Extracted</h3>';
    html += `<p><strong>Rows:</strong> ${metadata.structure.shape.rows}</p>`;
    html += `<p><strong>Columns:</strong> ${metadata.structure.shape.columns}</p>`;
    html += '<h4>Column Details:</h4>';
    html += '<ul>';
    
    metadata.structure.columns.forEach(col => {
        html += `<li><strong>${col.name}</strong>: ${col.python_type} (${col.unique_count} unique values)</li>`;
    });
    
    html += '</ul>';
    html += '</div>';
    
    resultsContent.innerHTML = html;
}

// Demo data
async function loadDemoData(e) {
    const demoType = e.target.dataset.demo;
    
    showLoading(`Loading ${demoType} demo data...`);
    
    // Create sample data based on type
    const demoData = generateDemoData(demoType);
    const blob = new Blob([demoData], {type: 'text/csv'});
    const file = new File([blob], `${demoType}_demo.csv`, {type: 'text/csv'});
    
    processFile(file);
    hideLoading();
}

function generateDemoData(type) {
    const demos = {
        sales: `order_id,date,customer_id,product,quantity,price,total
1001,2024-01-15,C001,Widget A,5,29.99,149.95
1002,2024-01-15,C002,Widget B,3,39.99,119.97
1003,2024-01-16,C003,Widget C,2,49.99,99.98
1004,2024-01-16,C001,Widget A,1,29.99,29.99
1005,2024-01-17,C004,Widget D,4,59.99,239.96`,
        
        customer: `customer_id,name,email,phone,city,registration_date,status
C001,John Smith,john.smith@email.com,555-0101,New York,2023-01-15,Active
C002,Jane Doe,jane.doe@email.com,555-0102,Los Angeles,2023-02-20,Active
C003,Bob Johnson,bob.j@email.com,555-0103,Chicago,2023-03-10,Inactive
C004,Alice Brown,alice.b@email.com,555-0104,Houston,2023-04-05,Active
C005,Charlie Wilson,charlie.w@email.com,555-0105,Phoenix,2023-05-12,Active`,
        
        medical: `patient_id,age,gender,diagnosis,treatment_date,doctor_id,medication,dosage_mg
P001,45,M,Hypertension,2024-01-10,D101,Lisinopril,10
P002,62,F,Diabetes Type 2,2024-01-11,D102,Metformin,500
P003,38,M,Anxiety,2024-01-12,D103,Sertraline,50
P004,55,F,Hypertension,2024-01-13,D101,Amlodipine,5
P005,29,M,Depression,2024-01-14,D103,Fluoxetine,20`,
        
        financial: `transaction_id,date,account_from,account_to,amount,currency,type,status
T001,2024-01-15 09:30:00,ACC001,ACC002,1500.00,USD,Transfer,Completed
T002,2024-01-15 10:15:00,ACC003,ACC001,250.50,USD,Payment,Completed
T003,2024-01-15 11:00:00,ACC002,ACC004,3200.00,USD,Wire,Pending
T004,2024-01-15 14:30:00,ACC005,ACC003,750.25,USD,Transfer,Completed
T005,2024-01-16 08:45:00,ACC001,ACC005,425.00,USD,Payment,Failed`
    };
    
    return demos[type] || demos.sales;
}

// Utility functions
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

function createTableFromJSON(data) {
    if (!data || data.length === 0) return '<p>No data</p>';
    
    let html = '<table style="width: 100%; border-collapse: collapse;">';
    
    // Header
    html += '<thead><tr>';
    Object.keys(data[0]).forEach(key => {
        html += `<th style="border: 1px solid #ddd; padding: 8px; background: #f5f5f5;">${key}</th>`;
    });
    html += '</tr></thead>';
    
    // Body
    html += '<tbody>';
    data.forEach(row => {
        html += '<tr>';
        Object.values(row).forEach(value => {
            html += `<td style="border: 1px solid #ddd; padding: 8px;">${value}</td>`;
        });
        html += '</tr>';
    });
    html += '</tbody></table>';
    
    return html;
}

function downloadFile(blob, filename) {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

function showLoading(message = 'Processing...') {
    loadingMessage.textContent = message;
    loadingOverlay.style.display = 'flex';
}

function hideLoading() {
    loadingOverlay.style.display = 'none';
}

function showError(message) {
    // Handle both string and object messages
    const displayMessage = typeof message === 'object' 
        ? (message.message || JSON.stringify(message))
        : (message || 'An unexpected error occurred');
    errorMessage.textContent = displayMessage;
    errorModal.style.display = 'flex';
}

function closeError() {
    errorModal.style.display = 'none';
}

function reset() {
    currentFile = null;
    currentMetadata = null;
    fileInput.value = '';
    fileInfo.style.display = 'none';
    configSection.style.display = 'none';
    resultsSection.style.display = 'none';
    metadataSection.style.display = 'none';
    downloadBtn.style.display = 'none';
    numRows.value = '';
    matchThreshold.value = 80;
    thresholdValue.textContent = '80%';
    outputFormat.value = 'csv';
    useCache.checked = true;
}

// Helper function to convert data to CSV (if not defined in data-editor.js)
if (typeof convertToCSV === 'undefined') {
    window.convertToCSV = function(data) {
        if (!data || data.length === 0) return '';
        
        const headers = Object.keys(data[0]);
        const csv = [
            headers.join(','),
            ...data.map(row => headers.map(h => `"${row[h] || ''}"`).join(','))
        ].join('\n');
        
        return csv;
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', init);