# Usage Dashboard Documentation

## Overview

The Usage Dashboard provides real-time insights into the BYOD Synthetic Data Generator's performance, usage patterns, and cache efficiency. Access it at `http://localhost:8201/dashboard`.

## Dashboard Components

### 1. Performance Metrics Chart (Stacked Bar)

Shows response times broken down by source:
- **Cached Time** (green): Time spent retrieving from cache
- **LLM Time** (blue): Time spent calling Azure OpenAI

This visualization helps identify:
- Cache effectiveness
- Performance bottlenecks
- Cost savings from caching

### 2. Usage Over Time Chart (Line)

Tracks the number of generation requests over time with:
- **Time Granularity Control**: Switch between Hourly, Daily, Weekly, or Monthly views
- **Interactive tooltips**: Hover to see exact counts
- **Auto-refresh**: Updates every 30 seconds

### 3. Generation Methods Distribution (Pie Chart)

Visualizes the breakdown of generation methods:
- **Cache hits**: Requests served from cache
- **LLM calls**: New generations via Azure OpenAI
- **Fallback**: Local generation when LLM fails

### 4. Cache Statistics Section

Real-time cache metrics including:
- **Cached Programs**: Total number of cached generation scripts
- **Unique Formats**: Number of distinct data structures
- **Cache Size**: Total disk space used by cache
- **Clear Cache Button**: Remove old cache entries

### 5. Recent Cache Patterns Table

Lists recently cached data patterns showing:
- Timestamp of caching
- Column names and structure
- Format and full hash identifiers

## Features

### Time Range Selection

Use the date pickers to filter data:
- **Start Date**: Beginning of analysis period
- **End Date**: End of analysis period
- **Apply Filter**: Update all charts with selected range

### Auto-Refresh

All dashboard components automatically refresh every 30 seconds to show the latest data.

### Export Capabilities

Charts can be exported as images:
1. Right-click on any chart
2. Select "Save image as..."
3. Choose your preferred format (PNG recommended)

## Navigation

Access the dashboard via:
1. **Direct URL**: `http://localhost:8201/dashboard`
2. **Navigation Menu**: Click "Info" dropdown → "Usage Dashboard"

## API Endpoints Used

The dashboard fetches data from:
- `/api/usage-logs`: Historical usage data
- `/api/cache-info`: Cache statistics and entries
- `/api/cache/clear`: Cache management endpoint

## Understanding the Metrics

### Response Time Analysis
- **< 1 second**: Excellent (usually cache hits)
- **1-3 seconds**: Good (simple LLM generations)
- **3-5 seconds**: Average (complex data structures)
- **> 5 seconds**: May indicate issues or very complex schemas

### Cache Hit Rate
- **> 80%**: Excellent cache utilization
- **50-80%**: Good, but room for improvement
- **< 50%**: Consider adjusting cache settings

### Usage Patterns
- **Peaks**: Identify high-usage periods
- **Trends**: Monitor growth or decline in usage
- **Anomalies**: Spot unusual activity

## Configuration

### Dashboard Settings

Configure via environment variables:
```bash
DASHBOARD_REFRESH_INTERVAL=30000  # Milliseconds
DASHBOARD_DEFAULT_RANGE_DAYS=7    # Default time range
DASHBOARD_MAX_CACHE_ENTRIES=100   # Max entries in cache table
```

### Chart Customization

Modify chart appearance in `dashboard.html`:
```javascript
// Chart.js configuration
const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: { position: 'top' },
        tooltip: { enabled: true }
    }
};
```

## Troubleshooting

### Dashboard Not Loading
1. Verify server is running on port 8201
2. Check browser console for JavaScript errors
3. Ensure Chart.js CDN is accessible
4. Clear browser cache

### No Data Displayed
1. Check if usage logs exist in `logs/usage/`
2. Verify date range includes data
3. Check API endpoints are responding
4. Look for errors in server logs

### Charts Not Updating
1. Check auto-refresh is enabled
2. Verify API endpoints return valid data
3. Check browser developer tools for errors
4. Ensure sufficient system resources

## Performance Optimization

### For Large Datasets
1. Use appropriate time granularity (daily/weekly for long ranges)
2. Limit the date range to relevant periods
3. Clear old cache entries regularly
4. Archive old usage logs monthly

### Browser Performance
1. Close unused dashboard tabs
2. Use modern browsers (Chrome, Firefox, Edge)
3. Disable browser extensions that might interfere
4. Ensure adequate client-side memory

## Security Considerations

The dashboard is designed for local/development use. For production:
1. Add authentication/authorization
2. Use HTTPS for secure connections
3. Implement rate limiting
4. Sanitize all user inputs
5. Restrict API access to authorized users

## Future Enhancements

Planned improvements include:
- Export data to CSV/Excel
- Custom alert thresholds
- Comparative analysis tools
- Performance predictions
- Cost tracking and projections
- User session analytics