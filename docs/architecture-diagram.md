# BYOD Synthetic Data Generator - Architecture Flow

## How It Works

```mermaid
graph TB
    subgraph "User Space"
        A[Upload Data File<br/>CSV/JSON/Excel] --> B[Data Loader ✅]
        DD[Data Dictionary Upload<br/>🚧 PLANNED] -.-> VAL[Dictionary Validation<br/>🚧 PLANNED]
    end

    subgraph "Metadata Extraction - No PHI Exposure"
        B --> C[Metadata Extractor ✅]
        C --> D[Statistical Analysis ⚠️<br/>- Column Types 🔧<br/>- Distributions ✅<br/>- Correlations ⚠️<br/>- Patterns ⚠️]
        D --> E[Secure JSON Metadata ✅<br/>NO actual data values]
        VAL -.-> C
    end

    subgraph "LLM Generation - Privacy Safe"
        E --> F{Cache Check ⚠️}
        F -->|Cache Hit| G[Reuse Existing<br/>Generation Script ⚠️]
        F -->|Cache Miss| H[Send Metadata to LLM ✅<br/>ONLY statistics, NO PHI]
        H --> I[LLM Creates Python Code ⚠️<br/>Needs Domain Knowledge]
        REF[Clinical Reference Library<br/>🚧 PLANNED] -.-> I
    end

    subgraph "Synthetic Data Creation"
        G --> J[Execute Python Code ✅]
        I --> J
        J --> K[Generate Synthetic Data ⚠️<br/>Date Issues Present]
        K --> L[Validate Against<br/>Original Metadata 🚧]
        L -->|Valid| M[Return Synthetic Data ✅<br/>Multi-file ZIP Support ✅]
        L -->|Invalid| N[Regenerate with<br/>Stricter Parameters ⚠️]
        N --> J
    end

    %% Color coding for development status
    style A fill:#90EE90
    style B fill:#90EE90
    style C fill:#90EE90
    style E fill:#90EE90
    style H fill:#90EE90
    style J fill:#90EE90
    style M fill:#90EE90

    style D fill:#FFE4B5
    style F fill:#FFE4B5
    style G fill:#FFE4B5
    style I fill:#FFE4B5
    style K fill:#FFE4B5
    style N fill:#FFE4B5

    style DD fill:#FFB6C1
    style VAL fill:#FFB6C1
    style REF fill:#FFB6C1
    style L fill:#FFB6C1

    %% Legend
    subgraph "Legend"
        L1[✅ Complete - Green]
        L2[⚠️ Partial/Issues - Yellow]
        L3[🚧 Planned - Pink]
    end
```

## Privacy Protection

**THE LLM NEVER SEES YOUR ACTUAL DATA**

1. **Metadata Extraction**: Analyzes your data locally to extract only statistical properties:
   - Column names and data types
   - Statistical distributions (mean, std, min, max)
   - Correlation patterns between columns
   - Value patterns (e.g., date formats, string patterns)
   - NO actual data values are extracted

2. **LLM Role**: The LLM receives only the metadata and creates Python code to generate synthetic data that matches the statistical properties. It never sees any actual data values.

3. **Synthetic Generation**: The Python code runs locally to create new synthetic data matching the patterns.

## Column Type Detection

The system detects column types through:
- Pandas dtype inference
- Pattern matching (dates, emails, phones)
- Statistical analysis (numeric distributions)
- Value frequency analysis (categorical detection)

## Caching Mechanism

When you upload a file:
1. A hash is created from the metadata structure
2. Similar metadata patterns are searched in the cache
3. If found (based on match threshold), existing generation code is reused
4. This ensures consistent results for similar data structures

## Known Limitations

- **Date Detection**: Currently relies on pandas inference which may miss custom date formats
- **Semantic Understanding**: The system doesn't understand domain context (e.g., "medication" columns)
- **Complex Relationships**: Multi-column dependencies may not be fully preserved

## Future Improvements

- Domain-specific value lists (medications, diagnoses, etc.)
- Better date/time format detection
- Semantic column understanding
- Multi-column relationship preservation