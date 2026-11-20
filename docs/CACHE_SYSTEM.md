# Cache System Documentation

## Overview

The generator saves each script the AI model writes, together with the description of the data it was written for, in a folder on the server's disk. A later request with a similar description reuses the script instead of calling the AI model.

The description holds column names, data types, counts and summary statistics, and under the rules of the chosen safety mode some real values (repeated short category labels; the smallest and largest values of ordinary number columns). It does not hold rows. The uploaded file is not written to the cache.

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

- **`off`**: No cached script is looked up by the route. Send `use_cache=false` as well to make sure nothing is read or written
- **`structure`**: Match based on column names and types only
- **`structure_stats`**: Match based on structure AND statistical properties

### Similarity

When the structure matches, the system:
1. Builds a list of 128 numbers from the description (row and column counts, and per column mean, spread, range or text length). No embedding model is called
2. Compares it with the list stored for each cached script
3. Reuses the closest one at or above the request's match threshold (default: 0.8)

A script is reused only for the number of rows, the AI model and the safety mode it was written for. A cached script that fails to run is removed.

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
  "num_rows": 100,
  "version": "1.1"
}
```

The metadata file holds the description, including the column names. `GET /api/cache-info` returns those column names, and the usage dashboard shows them.

## Performance Benefits

- **Speed**: A cache hit skips the call to the AI model
- **Cost**: Fewer Azure OpenAI calls

## Cache Management

### API Endpoints

- **GET `/api/cache-info`**: Returns cache statistics and entries
- **DELETE `/api/cache/clear`** and **DELETE `/cache`**: Clear cache with optional age filter
  - Query param: `older_than_days` (optional)

### Cleanup

Nothing is removed automatically, and there is no size limit. Entries stay until one of the clear routes is called, or until `GENERATOR_VERSION` is raised (older entries are then no longer matched). The service has no sign-in (tracked as ADP-60).

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
LOCAL_CACHE_PATH=./data/cache   # Folder for cached descriptions and scripts
GENERATOR_VERSION=1.1           # Part of every cache key; raising it retires every cached script
```

### Per request
- `use_cache` (true/false): false neither reads nor writes the cache
- `cache_mode` (`off`, `structure`, `structure_stats`) on the form routes: which cached scripts may be reused
- `match_threshold` (0 to 1): how close a cached description must be

## Best Practices

1. **Use `structure_stats` mode** when the statistics should match closely
2. **Use `structure` mode** when statistical properties can vary
3. **Use `use_cache=false`** when the description must not be stored, or when you need newly written code
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
2. Check the request did not send `use_cache=false`
3. Check logs for cache-related errors
4. Ensure cache_index.json is valid JSON

### Poor Cache Performance
1. Lower the match threshold for more aggressive caching
2. Use `structure` mode instead of `structure_stats`
3. Check if embeddings are being generated correctly
4. Monitor cache size - very large caches can slow searches

### Data Not Varying
1. Seed injection only changes scripts that set a random seed
2. Check if generated code uses random functions
3. Verify the LLM is generating randomized code, not static values