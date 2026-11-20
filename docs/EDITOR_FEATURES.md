# Data Editor Features

You can view and edit data in the browser before generating synthetic data.

When you generate, the edited table is sent to the server and analysed there, the same as an uploaded file. Do not load real study data or patient identifiers: this release has not been approved for them. The demo datasets are examples built into the page.

## 📝 How to Use the New Data Editor

### 1. Start the Application
```bash
cd Create-mockData-from-real-file
python3 main.py
```

### 2. Open in Browser
Navigate to: **http://localhost:8201**

### 3. Load Data
- Choose a demo dataset (e.g., "🏥 Medical")
- Or upload your own CSV/JSON file
- **The data will appear in an editable table!**

## 🛠️ Editor Features

### Basic Editing
- **Click any cell** to edit it directly
- **Press Enter** to save changes
- **Press Escape** to cancel editing
- Modified cells are highlighted in yellow

### Data Manipulation Tools
- **➕ Add Row** - Adds a new empty row
- **➕ Add Column** - Prompts for column name and adds it
- **🗑️ Delete Row** - Click row numbers to select, then delete
- **🗑️ Delete Column** - Click column headers to select, then delete
- **🎲 Randomize Values** - Randomizes selected cells intelligently
- **↺ Reset** - Restores original data

### 🧪 Experimental Features (The Fun Part!)
- **💥 Corrupt Random Data** - Adds errors, reversals, and blanks to 10% of cells
- **📋 Duplicate Random Rows** - Creates duplicates of 20% of rows
- **❓ Add Random Nulls** - Makes 15% of cells empty
- **🔀 Scramble Column** - Shuffles all values within a column
- **📈 Generate Outliers** - Creates extreme values (99999999 or -99999999)

## 🎯 Workflow Example

1. **Load Medical Data**
   - Choose the "🏥 Medical" demo dataset
   - Data appears in editable table

2. **Edit in Weird Ways**
   - Change patient names to "ANONYMOUS"
   - Click "💥 Corrupt Random Data" to add errors
   - Click "📈 Generate Outliers" to add extreme ages like 99999999
   - Click "🔀 Scramble Column" and scramble the diagnosis column

3. **Generate Synthetic Data**
   - Click "🚀 Generate Synthetic Data"
   - The generator will use YOUR EDITED data as the source
   - See how it handles the weird modifications!

4. **View Results**
   - Click "👁️ View Synthetic Data" to see the generated data
   - Compare with your edited version
   - Download the results

## 🔥 Cool Experiments to Try

### Placeholder Test
- Edit all patient names to "XXXXX"
- Generate synthetic data
- Check if it still creates diverse names

### Outlier Handling
- Add extreme values (999999) to numeric columns
- See if synthetic data normalizes them

### Missing Data Test
- Click "❓ Add Random Nulls" multiple times
- Generate synthetic data with 50% missing values
- See how it handles sparse data

### Correlation Breaking
- Scramble related columns (e.g., diagnosis and medication)
- Check if synthetic data recreates logical relationships

### Data Quality Stress Test
1. Click "💥 Corrupt Random Data"
2. Click "📋 Duplicate Random Rows"
3. Click "❓ Add Random Nulls"
4. Click "📈 Generate Outliers"
5. Generate synthetic data from this mess!
6. See if it produces clean, usable data

## 📊 What Happens Behind the Scenes

When you edit data and generate synthetic:
1. Your edited data is sent to the server as CSV
2. The server builds a description from YOUR VERSION (not the original)
3. The description (not the rows) is sent to the AI model, which writes a script
4. The server runs the script to make synthetic data
5. The result shows how the generator handles data quality issues

## 🎨 Visual Indicators

- **Yellow cells** = Modified data
- **Red cells** = Corrupted data
- **Purple cells** = Outlier values
- **Green rows** = Duplicated rows
- **Italic gray** = Null values

## 🚀 Ready to Test!

The editor is fully functional. Try breaking the data in creative ways and see how the synthetic generator handles it!

**Remember**: The whole point is to edit data in weird ways and see how the mock file turns out. Have fun experimenting!

