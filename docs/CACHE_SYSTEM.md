# Cache System Documentation

## Overview

The BYOD Synthetic Data Generator implements an intelligent caching system that significantly improves performance by reusing previously generated code for similar data structures.

## How It Works

### Two-Level Hashing

The cache system uses a two-level hashing approach:

1. **Format Hash**: Based on column names and data types only
   - Example: `format_8a89c90ef4d58da2`
   - Used for structure-only matching

2. **Full Hash**: Includes statistical properties (mean, std, correlations)
   - Example: `full_ca64349e26ada071`
   - Used for precise statistical matching

### Cache Modes

Users can configure caching behavior via the `cache_mode` parameter:

- **`off`**: No caching, always generate new code via LLM
- **`structure`**: Match based on column names and types only
- **`structure_stats`**: Match based on structure AND statistical properties

### Vector Similarity Search

For intelligent matching, the system:
1. Generates 128-dimensional embeddings for each cached pattern
2. Uses cosine similarity to find similar patterns
3. Applies a configurable match threshold (default: 0.8)

## Cache Storage

### Directory Structure
```
data/cache/
├── cache_index.json                # Main index file
├── format_xxx_full_yyy_timestamp_code.py      # Generated Python code
├── format_xxx_full_yyy_timestamp_metadata.json # Metadata
└── format_xxx_full_yyy_timestamp_embedding.npy # Vector embedding
```

### Cache Entry Format
```json
{
  "cache_key": "format_xxx_full_yyy_timestamp",
  "format_hash": "format_xxx",
  "full_hash": "full_yyy",
  "timestamp": "2025-09-23T16:28:19.651851",
  "columns": ["col1", "col2", "..."],
  "version": "1.0"
}
```

## Performance Benefits

- **Speed**: Cache hits are typically 5-10x faster than LLM generation
- **Cost**: Reduces Azure OpenAI API calls and costs
- **Consistency**: Ensures similar data structures get consistent treatment

## Cache Management

### API Endpoints

- **GET `/api/cache-info`**: Returns cache statistics and entries
- **DELETE `/api/cache/clear`**: Clear cache with optional age filter
  - Query param: `older_than_days` (optional)

### Automatic Cleanup

The system includes:
- Configurable cache size limits
- Age-based expiration (default: 30 days)
- Automatic index rebuilding if corrupted

## Seed Injection for Variety

Even when using cached code, the system injects random seeds to ensure data variety:

```python
# Original cached code
np.random.seed(42)

# After seed injection
np.random.seed(66486)  # New random seed
```

This ensures that cached code produces different results each time while maintaining the same statistical properties.

## Configuration

### Environment Variables
```bash
CACHE_ENABLED=true           # Enable/disable caching
CACHE_MAX_SIZE_MB=500        # Maximum cache size
CACHE_MATCH_THRESHOLD=0.8    # Similarity threshold for matches
CACHE_TTL_DAYS=30           # Cache time-to-live in days
```

### Programmatic Configuration
```python
generator = SyntheticDataGenerator(
    cache_enabled=True,
    cache_match_threshold=0.8
)
```

## Best Practices

1. **Use `structure_stats` mode** for production to ensure statistical consistency
2. **Use `structure` mode** when statistical properties can vary
3. **Use `off` mode** only for debugging or when you need completely fresh generation
4. **Monitor cache size** and clear old entries periodically
5. **Review cache hits** in logs to ensure quality matches

## Monitoring

### Log Messages
```
INFO - Found similar cache match with similarity: 0.95
INFO - Cache hit! Using cached code (check took 0.001s)
INFO - No suitable cache match found
INFO - Cached generation with key: format_xxx_full_yyy_timestamp
```

### Dashboard Metrics
- Total cached programs
- Unique data formats
- Cache size (MB)
- Cache hit rate
- Average response time (cached vs LLM)

## Troubleshooting

### Cache Not Working
1. Check if `data/cache/` directory exists and is writable
2. Verify cache is enabled in configuration
3. Check logs for cache-related errors
4. Ensure cache_index.json is valid JSON

### Poor Cache Performance
1. Lower the match threshold for more aggressive caching
2. Use `structure` mode instead of `structure_stats`
3. Check if embeddings are being generated correctly
4. Monitor cache size - very large caches can slow searches

### Data Not Varying
1. Ensure seed injection is enabled (default: true)
2. Check if generated code uses random functions
3. Verify the LLM is generating randomized code, not static values