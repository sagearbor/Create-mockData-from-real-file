// Data Editor Module for BYOD Synthetic Data Generator

let currentData = [];
let originalData = [];
let selectedRows = new Set();
let selectedCols = new Set();
let editHistory = [];
let syntheticData = null;

// Data Editor Initialization
function initDataEditor() {
    // Button event listeners
    document.getElementById('addRowBtn')?.addEventListener('click', addRow);
    document.getElementById('addColBtn')?.addEventListener('click', showAddColumnModal);
    document.getElementById('deleteRowBtn')?.addEventListener('click', deleteSelectedRows);
    document.getElementById('deleteColBtn')?.addEventListener('click', deleteSelectedColumns);
    document.getElementById('randomizeBtn')?.addEventListener('click', randomizeSelectedCells);
    document.getElementById('resetDataBtn')?.addEventListener('click', resetData);
    document.getElementById('saveChangesBtn')?.addEventListener('click', saveChanges);
    document.getElementById('discardChangesBtn')?.addEventListener('click', discardChanges);
    
    // Experimental features
    document.getElementById('corruptDataBtn')?.addEventListener('click', corruptRandomData);
    document.getElementById('duplicateRowsBtn')?.addEventListener('click', duplicateRandomRows);
    document.getElementById('addNullsBtn')?.addEventListener('click', addRandomNulls);
    document.getElementById('scrambleColBtn')?.addEventListener('click', scrambleColumn);
    document.getElementById('generateOutliersBtn')?.addEventListener('click', generateOutliers);
    
    // Synthetic data viewer
    document.getElementById('viewSyntheticBtn')?.addEventListener('click', viewSyntheticData);
    document.getElementById('downloadSyntheticBtn')?.addEventListener('click', downloadSyntheticData);
    document.getElementById('regenerateBtn')?.addEventListener('click', () => {
        document.getElementById('syntheticViewerSection').style.display = 'none';
        generateSyntheticData();
    });
}

// Parse CSV data
function parseCSV(text) {
    const lines = text.trim().split('\n');
    if (lines.length === 0) return [];
    
    const headers = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
    const data = [];
    
    for (let i = 1; i < lines.length; i++) {
        const values = lines[i].split(',').map(v => v.trim().replace(/^"|"$/g, ''));
        const row = {};
        headers.forEach((header, index) => {
            row[header] = values[index] || '';
        });
        data.push(row);
    }
    
    return data;
}

// Parse JSON data
function parseJSON(text) {
    try {
        const json = JSON.parse(text);
        if (Array.isArray(json)) {
            return json;
        } else if (typeof json === 'object') {
            // Handle nested JSON
            if (json.data && Array.isArray(json.data)) {
                return json.data;
            }
            // Convert single object to array
            return [json];
        }
    } catch (e) {
        console.error('Error parsing JSON:', e);
        return [];
    }
}

// Display data in editable table
function displayDataTable(data) {
    if (!data || data.length === 0) return;
    
    currentData = JSON.parse(JSON.stringify(data)); // Deep copy
    originalData = JSON.parse(JSON.stringify(data)); // Keep original
    
    const dataEditorSection = document.getElementById('dataEditorSection');
    const tableHead = document.getElementById('tableHead');
    const tableBody = document.getElementById('tableBody');
    
    // Clear existing content
    tableHead.innerHTML = '';
    tableBody.innerHTML = '';
    selectedRows.clear();
    selectedCols.clear();
    
    // Get headers
    const headers = Object.keys(data[0]);
    
    // Create header row
    const headerRow = document.createElement('tr');
    
    // Add row number header
    const thRowNum = document.createElement('th');
    thRowNum.textContent = '#';
    thRowNum.className = 'row-number';
    headerRow.appendChild(thRowNum);
    
    // Add data headers
    headers.forEach((header, colIndex) => {
        const th = document.createElement('th');
        th.textContent = header;
        th.dataset.colIndex = colIndex;
        th.onclick = () => selectColumn(colIndex);
        
        // Add column actions
        const colActions = document.createElement('span');
        colActions.className = 'column-actions';
        colActions.innerHTML = `<button class="col-delete-btn" onclick="deleteColumn(${colIndex})">×</button>`;
        th.appendChild(colActions);
        
        headerRow.appendChild(th);
    });
    
    tableHead.appendChild(headerRow);
    
    // Create data rows
    data.forEach((row, rowIndex) => {
        const tr = document.createElement('tr');
        tr.dataset.rowIndex = rowIndex;
        
        // Add row number
        const tdRowNum = document.createElement('td');
        tdRowNum.className = 'row-number';
        tdRowNum.textContent = rowIndex + 1;
        tdRowNum.onclick = () => selectRow(rowIndex);
        tr.appendChild(tdRowNum);
        
        // Add data cells
        headers.forEach((header, colIndex) => {
            const td = document.createElement('td');
            td.className = 'cell-editable';
            td.dataset.rowIndex = rowIndex;
            td.dataset.colIndex = colIndex;
            td.dataset.header = header;
            
            const value = row[header];
            if (value === null || value === undefined || value === '') {
                td.innerHTML = '<span class="cell-null">null</span>';
            } else {
                td.textContent = value;
            }
            
            td.onclick = (e) => editCell(e, rowIndex, colIndex, header);
            tr.appendChild(td);
        });
        
        tableBody.appendChild(tr);
    });
    
    // Update stats
    updateDataStats();
    
    // Show the editor section
    dataEditorSection.style.display = 'block';
    document.getElementById('configSection').style.display = 'block';
}

// Edit cell
function editCell(event, rowIndex, colIndex, header) {
    const cell = event.target;
    if (cell.querySelector('input')) return; // Already editing
    
    const currentValue = currentData[rowIndex][header] || '';
    
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentValue;
    input.onblur = () => saveCell(input, rowIndex, header);
    input.onkeydown = (e) => {
        if (e.key === 'Enter') saveCell(input, rowIndex, header);
        if (e.key === 'Escape') cancelEdit(cell, currentValue);
    };
    
    cell.innerHTML = '';
    cell.classList.add('editing');
    cell.appendChild(input);
    input.focus();
    input.select();
}

// Save cell value
function saveCell(input, rowIndex, header) {
    const newValue = input.value;
    const cell = input.parentElement;
    
    currentData[rowIndex][header] = newValue;
    
    cell.classList.remove('editing');
    cell.classList.add('cell-modified');
    
    if (newValue === '') {
        cell.innerHTML = '<span class="cell-null">null</span>';
    } else {
        cell.textContent = newValue;
    }
    
    updateDataStats();
}

// Cancel cell edit
function cancelEdit(cell, originalValue) {
    cell.classList.remove('editing');
    if (originalValue === '') {
        cell.innerHTML = '<span class="cell-null">null</span>';
    } else {
        cell.textContent = originalValue;
    }
}

// Select row
function selectRow(rowIndex) {
    const row = document.querySelector(`tr[data-row-index="${rowIndex}"]`);
    const rowNum = row?.querySelector('.row-number');
    
    if (selectedRows.has(rowIndex)) {
        selectedRows.delete(rowIndex);
        row?.classList.remove('selected');
        rowNum?.classList.remove('selected');
    } else {
        selectedRows.add(rowIndex);
        row?.classList.add('selected');
        rowNum?.classList.add('selected');
    }
}

// Select column
function selectColumn(colIndex) {
    const header = document.querySelector(`th[data-col-index="${colIndex}"]`);
    
    if (selectedCols.has(colIndex)) {
        selectedCols.delete(colIndex);
        header?.classList.remove('selected');
    } else {
        selectedCols.add(colIndex);
        header?.classList.add('selected');
    }
    
    // Highlight column cells
    document.querySelectorAll(`td[data-col-index="${colIndex}"]`).forEach(cell => {
        if (selectedCols.has(colIndex)) {
            cell.style.background = '#f0f9ff';
        } else {
            cell.style.background = '';
        }
    });
}

// Add new row
function addRow() {
    const headers = Object.keys(currentData[0] || {});
    const newRow = {};
    headers.forEach(header => {
        newRow[header] = '';
    });
    currentData.push(newRow);
    displayDataTable(currentData);
}

// Show add column modal
function showAddColumnModal() {
    const columnName = prompt('Enter new column name:');
    if (columnName && columnName.trim()) {
        addColumn(columnName.trim());
    }
}

// Add new column
function addColumn(columnName) {
    currentData.forEach(row => {
        row[columnName] = '';
    });
    displayDataTable(currentData);
}

// Delete selected rows
function deleteSelectedRows() {
    if (selectedRows.size === 0) {
        alert('Please select rows to delete');
        return;
    }
    
    if (!confirm(`Delete ${selectedRows.size} selected rows?`)) return;
    
    const rowsToDelete = Array.from(selectedRows).sort((a, b) => b - a);
    rowsToDelete.forEach(index => {
        currentData.splice(index, 1);
    });
    
    selectedRows.clear();
    displayDataTable(currentData);
}

// Delete column
function deleteColumn(colIndex) {
    const headers = Object.keys(currentData[0] || {});
    const columnName = headers[colIndex];
    
    if (!confirm(`Delete column "${columnName}"?`)) return;
    
    currentData.forEach(row => {
        delete row[columnName];
    });
    
    displayDataTable(currentData);
}

// Delete selected columns
function deleteSelectedColumns() {
    if (selectedCols.size === 0) {
        alert('Please select columns to delete');
        return;
    }
    
    const headers = Object.keys(currentData[0] || {});
    const columnsToDelete = Array.from(selectedCols).map(i => headers[i]);
    
    if (!confirm(`Delete columns: ${columnsToDelete.join(', ')}?`)) return;
    
    currentData.forEach(row => {
        columnsToDelete.forEach(col => delete row[col]);
    });
    
    selectedCols.clear();
    displayDataTable(currentData);
}

// Randomize selected cells
function randomizeSelectedCells() {
    const headers = Object.keys(currentData[0] || {});
    
    currentData.forEach((row, rowIndex) => {
        headers.forEach((header, colIndex) => {
            if (selectedRows.size > 0 && !selectedRows.has(rowIndex)) return;
            if (selectedCols.size > 0 && !selectedCols.has(colIndex)) return;
            
            // Detect data type and randomize accordingly
            const originalValue = row[header];
            if (!isNaN(originalValue) && originalValue !== '') {
                // Numeric value
                row[header] = Math.floor(Math.random() * 1000);
            } else if (originalValue && originalValue.includes('@')) {
                // Email-like
                row[header] = `user${Math.floor(Math.random() * 1000)}@example.com`;
            } else if (originalValue && originalValue.match(/^\d{3}-\d{3}-\d{4}$/)) {
                // Phone-like
                row[header] = `555-${String(Math.floor(Math.random() * 900) + 100)}-${String(Math.floor(Math.random() * 9000) + 1000)}`;
            } else {
                // Generic string
                row[header] = `Random_${Math.random().toString(36).substring(7)}`;
            }
        });
    });
    
    displayDataTable(currentData);
}

// Corrupt random data
function corruptRandomData() {
    const corruptionRate = 0.1; // 10% of cells
    const headers = Object.keys(currentData[0] || {});
    
    currentData.forEach(row => {
        headers.forEach(header => {
            if (Math.random() < corruptionRate) {
                const corruption = Math.random();
                if (corruption < 0.3) {
                    row[header] = '###ERROR###';
                } else if (corruption < 0.6) {
                    row[header] = '';
                } else {
                    row[header] = String(row[header]).split('').reverse().join('');
                }
            }
        });
    });
    
    displayDataTable(currentData);
    alert('Added random corruption to 10% of cells!');
}

// Duplicate random rows
function duplicateRandomRows() {
    const duplicateCount = Math.floor(currentData.length * 0.2); // Duplicate 20% of rows
    const indicesToDuplicate = [];
    
    for (let i = 0; i < duplicateCount; i++) {
        indicesToDuplicate.push(Math.floor(Math.random() * currentData.length));
    }
    
    indicesToDuplicate.forEach(index => {
        const rowCopy = JSON.parse(JSON.stringify(currentData[index]));
        currentData.push(rowCopy);
    });
    
    displayDataTable(currentData);
    alert(`Duplicated ${duplicateCount} random rows!`);
}

// Add random nulls
function addRandomNulls() {
    const nullRate = 0.15; // 15% of cells
    const headers = Object.keys(currentData[0] || {});
    
    currentData.forEach(row => {
        headers.forEach(header => {
            if (Math.random() < nullRate) {
                row[header] = '';
            }
        });
    });
    
    displayDataTable(currentData);
    alert('Added random null values to 15% of cells!');
}

// Scramble column
function scrambleColumn() {
    const headers = Object.keys(currentData[0] || {});
    const columnName = prompt(`Which column to scramble? Options: ${headers.join(', ')}`);
    
    if (!columnName || !headers.includes(columnName)) {
        alert('Invalid column name');
        return;
    }
    
    // Extract all values from the column
    const values = currentData.map(row => row[columnName]);
    
    // Shuffle the values
    for (let i = values.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [values[i], values[j]] = [values[j], values[i]];
    }
    
    // Put shuffled values back
    currentData.forEach((row, index) => {
        row[columnName] = values[index];
    });
    
    displayDataTable(currentData);
    alert(`Scrambled column "${columnName}"!`);
}

// Generate outliers
function generateOutliers() {
    const headers = Object.keys(currentData[0] || {});
    const outlierCount = Math.max(1, Math.floor(currentData.length * 0.05)); // 5% outliers
    
    for (let i = 0; i < outlierCount; i++) {
        const rowIndex = Math.floor(Math.random() * currentData.length);
        const row = currentData[rowIndex];
        
        headers.forEach(header => {
            const value = row[header];
            if (!isNaN(value) && value !== '') {
                // For numeric values, create extreme outliers
                const extreme = Math.random() > 0.5 ? 99999999 : -99999999;
                row[header] = extreme;
            } else if (value) {
                // For strings, make them very long
                row[header] = value.repeat(50);
            }
        });
    }
    
    displayDataTable(currentData);
    alert(`Generated ${outlierCount} outlier rows with extreme values!`);
}

// Reset data to original
function resetData() {
    if (!confirm('Reset all changes and restore original data?')) return;
    currentData = JSON.parse(JSON.stringify(originalData));
    displayDataTable(currentData);
}

// Save changes
function saveChanges() {
    // Update the current file with edited data
    window.currentEditedData = currentData;
    alert('Changes saved! The edited data will be used for generation.');
    
    // Hide save/discard buttons
    document.getElementById('saveChangesBtn').style.display = 'none';
    document.getElementById('discardChangesBtn').style.display = 'none';
}

// Discard changes
function discardChanges() {
    if (!confirm('Discard all changes?')) return;
    resetData();
}

// Update data statistics
function updateDataStats() {
    const rowCount = currentData.length;
    const colCount = Object.keys(currentData[0] || {}).length;
    const cellCount = rowCount * colCount;
    
    document.getElementById('rowCount').textContent = rowCount;
    document.getElementById('colCount').textContent = colCount;
    document.getElementById('cellCount').textContent = cellCount;
}

// View synthetic data
function viewSyntheticData() {
    if (!syntheticData) return;
    
    const section = document.getElementById('syntheticViewerSection');
    const tableHead = document.getElementById('syntheticHead');
    const tableBody = document.getElementById('syntheticBody');
    
    // Clear existing content
    tableHead.innerHTML = '';
    tableBody.innerHTML = '';
    
    // Display synthetic data
    if (Array.isArray(syntheticData) && syntheticData.length > 0) {
        // Create headers
        const headers = Object.keys(syntheticData[0]);
        const headerRow = document.createElement('tr');
        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });
        tableHead.appendChild(headerRow);
        
        // Create rows (limit to first 100 for performance)
        syntheticData.slice(0, 100).forEach(row => {
            const tr = document.createElement('tr');
            headers.forEach(header => {
                const td = document.createElement('td');
                td.textContent = row[header] || '';
                tr.appendChild(td);
            });
            tableBody.appendChild(tr);
        });
        
        section.style.display = 'block';
    }
}

// Download synthetic data
function downloadSyntheticData() {
    if (!syntheticData) return;
    
    const csv = convertToCSV(syntheticData);
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'synthetic_data_edited.csv';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
}

// Convert data to CSV
function convertToCSV(data) {
    if (!data || data.length === 0) return '';
    
    const headers = Object.keys(data[0]);
    const csv = [
        headers.join(','),
        ...data.map(row => headers.map(h => `"${row[h] || ''}"`).join(','))
    ].join('\n');
    
    return csv;
}

// Override the processFile function to show data editor
const originalProcessFile = window.processFile;
window.processFile = function(file) {
    originalProcessFile(file);
    
    // Read and display file content
    const reader = new FileReader();
    reader.onload = function(e) {
        const content = e.target.result;
        let data = [];
        
        if (file.name.endsWith('.csv') || file.name.endsWith('.txt')) {
            data = parseCSV(content);
        } else if (file.name.endsWith('.json')) {
            data = parseJSON(content);
        }
        
        if (data.length > 0) {
            displayDataTable(data);
        }
    };
    reader.readAsText(file);
};

// Override generate function to use edited data
const originalGenerateSyntheticData = window.generateSyntheticData;
window.generateSyntheticData = async function() {
    // If data was edited, convert it back to file format
    if (window.currentEditedData) {
        const csv = convertToCSV(window.currentEditedData);
        const blob = new Blob([csv], { type: 'text/csv' });
        const editedFile = new File([blob], currentFile.name, { type: 'text/csv' });
        
        // Temporarily replace current file
        const tempFile = currentFile;
        currentFile = editedFile;
        
        // Call original generate function
        await originalGenerateSyntheticData();
        
        // Restore original file reference
        currentFile = tempFile;
    } else {
        await originalGenerateSyntheticData();
    }
};

// Store synthetic data when generated
const originalDisplayResults = window.displayResults;
window.displayResults = function(data) {
    originalDisplayResults(data);
    
    if (data.data) {
        syntheticData = data.data;
        document.getElementById('viewSyntheticBtn').style.display = 'inline-block';
    }
};

// Initialize on load
document.addEventListener('DOMContentLoaded', function() {
    initDataEditor();
});