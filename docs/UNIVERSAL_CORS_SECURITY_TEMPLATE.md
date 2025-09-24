# Universal CORS Security Template for All Tech Stacks

## 🎯 Purpose
This template provides copy-paste CORS security configurations for different programming languages and frameworks. Use this when setting up ANY new repository to ensure consistent security across all applications.

## 🔐 Core Security Principles

1. **Never use wildcard (`*`) origins in production**
2. **Use environment variables for configuration**
3. **Different settings per environment (local/dev/val/prod)**
4. **Minimal HTTP methods (only what's needed)**
5. **Always validate origins against a whitelist**

## 📋 Quick Setup Checklist

For ANY new repository:
- [ ] Add `ENVIRONMENT` variable to `.env.example`
- [ ] Add `ALLOWED_ORIGINS` variable to `.env.example`
- [ ] Copy appropriate code snippet below for your tech stack
- [ ] Configure Azure App Service environment variables
- [ ] Test CORS in each environment

## 🚀 Environment Variables Template

Add to your `.env.example` (ANY language):
```bash
# Environment Configuration (REQUIRED)
ENVIRONMENT="local"  # Options: local, development, validation, production

# CORS Security Settings (REQUIRED)
# Local development:
ALLOWED_ORIGINS="http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000"

# Development environment:
# ALLOWED_ORIGINS="https://your-app-dev.azurewebsites.net"

# Validation environment:
# ALLOWED_ORIGINS="https://your-app-val.azurewebsites.net"

# Production (RESTRICTIVE):
# ALLOWED_ORIGINS="https://your-app.azurewebsites.net,https://yourdomain.com"
```

---

## 💻 Language-Specific Implementations

### Python (FastAPI)
```python
# main.py or app.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

def get_allowed_origins():
    """Get allowed origins from environment or use defaults."""
    origins_env = os.getenv("ALLOWED_ORIGINS", "")
    if origins_env:
        return [origin.strip() for origin in origins_env.split(",")]

    environment = os.getenv("ENVIRONMENT", "local")
    if environment == "production":
        return ["https://your-app.azurewebsites.net"]
    elif environment == "validation":
        return ["https://your-app-val.azurewebsites.net"]
    elif environment == "development":
        return ["https://your-app-dev.azurewebsites.net", "http://localhost:3000"]
    else:  # local
        return ["http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Add PUT, DELETE only if needed
    allow_headers=["*"],
    max_age=3600,
)
```

### Python (Flask)
```python
# app.py
from flask import Flask
from flask_cors import CORS
import os

app = Flask(__name__)

def get_allowed_origins():
    origins_env = os.getenv("ALLOWED_ORIGINS", "")
    if origins_env:
        return origins_env.split(",")

    environment = os.getenv("ENVIRONMENT", "local")
    if environment == "production":
        return ["https://your-app.azurewebsites.net"]
    else:
        return ["http://localhost:3000", "http://localhost:8080"]

CORS(app,
     origins=get_allowed_origins(),
     supports_credentials=True,
     methods=["GET", "POST", "OPTIONS"])
```

### Node.js (Express)
```javascript
// app.js or server.js
const express = require('express');
const cors = require('cors');
require('dotenv').config();

const app = express();

function getAllowedOrigins() {
    const originsEnv = process.env.ALLOWED_ORIGINS;
    if (originsEnv) {
        return originsEnv.split(',').map(origin => origin.trim());
    }

    const environment = process.env.ENVIRONMENT || 'local';
    switch(environment) {
        case 'production':
            return ['https://your-app.azurewebsites.net'];
        case 'validation':
            return ['https://your-app-val.azurewebsites.net'];
        case 'development':
            return ['https://your-app-dev.azurewebsites.net', 'http://localhost:3000'];
        default: // local
            return ['http://localhost:3000', 'http://localhost:8080', 'http://127.0.0.1:3000'];
    }
}

const corsOptions = {
    origin: function (origin, callback) {
        const allowedOrigins = getAllowedOrigins();
        if (!origin || allowedOrigins.indexOf(origin) !== -1) {
            callback(null, true);
        } else {
            callback(new Error('Not allowed by CORS'));
        }
    },
    credentials: true,
    methods: ['GET', 'POST', 'OPTIONS'],
    maxAge: 3600
};

app.use(cors(corsOptions));
```

### C# / ASP.NET Core
```csharp
// Program.cs (NET 6+) or Startup.cs
var builder = WebApplication.CreateBuilder(args);

// Add CORS services
builder.Services.AddCors(options =>
{
    options.AddPolicy("SecurePolicy", policy =>
    {
        var allowedOrigins = GetAllowedOrigins(builder.Configuration);
        policy.WithOrigins(allowedOrigins)
              .AllowCredentials()
              .WithMethods("GET", "POST", "OPTIONS")
              .WithHeaders("*")
              .SetPreflightMaxAge(TimeSpan.FromSeconds(3600));
    });
});

var app = builder.Build();

// Use CORS
app.UseCors("SecurePolicy");

// Helper method
string[] GetAllowedOrigins(IConfiguration configuration)
{
    var originsConfig = configuration["ALLOWED_ORIGINS"];
    if (!string.IsNullOrEmpty(originsConfig))
    {
        return originsConfig.Split(',').Select(o => o.Trim()).ToArray();
    }

    var environment = configuration["ENVIRONMENT"] ?? "local";
    return environment switch
    {
        "production" => new[] { "https://your-app.azurewebsites.net" },
        "validation" => new[] { "https://your-app-val.azurewebsites.net" },
        "development" => new[] { "https://your-app-dev.azurewebsites.net", "http://localhost:3000" },
        _ => new[] { "http://localhost:3000", "http://localhost:5000", "http://127.0.0.1:3000" }
    };
}
```

### Java (Spring Boot)
```java
// WebConfig.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

@Configuration
public class WebConfig {

    @Value("${ALLOWED_ORIGINS:}")
    private String allowedOriginsEnv;

    @Value("${ENVIRONMENT:local}")
    private String environment;

    @Bean
    public CorsFilter corsFilter() {
        CorsConfiguration config = new CorsConfiguration();

        // Get allowed origins
        String[] origins = getAllowedOrigins();
        for (String origin : origins) {
            config.addAllowedOrigin(origin);
        }

        config.setAllowCredentials(true);
        config.addAllowedMethod("GET");
        config.addAllowedMethod("POST");
        config.addAllowedMethod("OPTIONS");
        config.addAllowedHeader("*");
        config.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);

        return new CorsFilter(source);
    }

    private String[] getAllowedOrigins() {
        if (!allowedOriginsEnv.isEmpty()) {
            return allowedOriginsEnv.split(",");
        }

        switch (environment) {
            case "production":
                return new String[]{"https://your-app.azurewebsites.net"};
            case "validation":
                return new String[]{"https://your-app-val.azurewebsites.net"};
            case "development":
                return new String[]{"https://your-app-dev.azurewebsites.net", "http://localhost:3000"};
            default: // local
                return new String[]{"http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000"};
        }
    }
}
```

### Go (Gin)
```go
// main.go
package main

import (
    "os"
    "strings"
    "github.com/gin-gonic/gin"
    "github.com/gin-contrib/cors"
)

func getAllowedOrigins() []string {
    originsEnv := os.Getenv("ALLOWED_ORIGINS")
    if originsEnv != "" {
        origins := strings.Split(originsEnv, ",")
        for i, origin := range origins {
            origins[i] = strings.TrimSpace(origin)
        }
        return origins
    }

    environment := os.Getenv("ENVIRONMENT")
    if environment == "" {
        environment = "local"
    }

    switch environment {
    case "production":
        return []string{"https://your-app.azurewebsites.net"}
    case "validation":
        return []string{"https://your-app-val.azurewebsites.net"}
    case "development":
        return []string{"https://your-app-dev.azurewebsites.net", "http://localhost:3000"}
    default:
        return []string{"http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:3000"}
    }
}

func main() {
    router := gin.Default()

    config := cors.Config{
        AllowOrigins:     getAllowedOrigins(),
        AllowMethods:     []string{"GET", "POST", "OPTIONS"},
        AllowHeaders:     []string{"*"},
        AllowCredentials: true,
        MaxAge:           3600,
    }

    router.Use(cors.New(config))

    // Your routes here
    router.Run(":8080")
}
```

### Ruby (Rails)
```ruby
# config/initializers/cors.rb
Rails.application.config.middleware.insert_before 0, Rack::Cors do
  allow do
    origins get_allowed_origins

    resource '*',
      headers: :any,
      methods: [:get, :post, :options],
      credentials: true,
      max_age: 3600
  end
end

def get_allowed_origins
  origins_env = ENV['ALLOWED_ORIGINS']
  return origins_env.split(',').map(&:strip) if origins_env.present?

  case ENV['ENVIRONMENT'] || 'local'
  when 'production'
    ['https://your-app.azurewebsites.net']
  when 'validation'
    ['https://your-app-val.azurewebsites.net']
  when 'development'
    ['https://your-app-dev.azurewebsites.net', 'http://localhost:3000']
  else # local
    ['http://localhost:3000', 'http://localhost:8080', 'http://127.0.0.1:3000']
  end
end
```

### PHP (Laravel)
```php
// config/cors.php
<?php

return [
    'paths' => ['api/*', 'sanctum/csrf-cookie'],
    'allowed_methods' => ['GET', 'POST', 'OPTIONS'],
    'allowed_origins' => function() {
        $originsEnv = env('ALLOWED_ORIGINS', '');
        if (!empty($originsEnv)) {
            return array_map('trim', explode(',', $originsEnv));
        }

        $environment = env('ENVIRONMENT', 'local');
        switch ($environment) {
            case 'production':
                return ['https://your-app.azurewebsites.net'];
            case 'validation':
                return ['https://your-app-val.azurewebsites.net'];
            case 'development':
                return ['https://your-app-dev.azurewebsites.net', 'http://localhost:3000'];
            default: // local
                return ['http://localhost:3000', 'http://localhost:8080', 'http://127.0.0.1:3000'];
        }
    }(),
    'allowed_origins_patterns' => [],
    'allowed_headers' => ['*'],
    'exposed_headers' => [],
    'max_age' => 3600,
    'supports_credentials' => true,
];
```

---

## 🧪 Testing CORS Configuration

### Test Script (Any Language)
```bash
#!/bin/bash
# test-cors.sh

echo "Testing CORS configuration..."

# Test from allowed origin
curl -H "Origin: http://localhost:3000" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type" \
     -X OPTIONS \
     -I http://localhost:8080/api/test

# Test from blocked origin (should fail)
curl -H "Origin: https://evil-site.com" \
     -H "Access-Control-Request-Method: POST" \
     -H "Access-Control-Request-Headers: Content-Type" \
     -X OPTIONS \
     -I http://localhost:8080/api/test
```

### Browser Console Test
```javascript
// Run in browser console to test CORS
fetch('http://your-api-url/test', {
    method: 'GET',
    credentials: 'include',
    headers: {
        'Content-Type': 'application/json',
    }
})
.then(response => console.log('CORS Success:', response))
.catch(error => console.error('CORS Failed:', error));
```

---

## 🔧 Azure App Service Configuration

Set these in Azure Portal > App Service > Configuration > Application Settings:

| Setting | Development | Validation | Production |
|---------|------------|------------|------------|
| `ENVIRONMENT` | `development` | `validation` | `production` |
| `ALLOWED_ORIGINS` | `https://app-dev.azurewebsites.net` | `https://app-val.azurewebsites.net` | `https://app.azurewebsites.net,https://yourdomain.com` |

---

## ⚠️ Common Mistakes to Avoid

1. **DON'T hardcode origins in code** - Always use environment variables
2. **DON'T use `allow_origins=["*"]`** in production
3. **DON'T forget OPTIONS method** - Required for preflight requests
4. **DON'T mix http/https** - Production should only use https
5. **DON'T forget to restart** app after changing environment variables

---

## 📚 Additional Resources

- [MDN CORS Documentation](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
- [OWASP CORS Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Origin_Resource_Sharing_Cheat_Sheet.html)
- [Azure App Service Environment Variables](https://docs.microsoft.com/en-us/azure/app-service/configure-common)

---

*Template Version: 1.0*
*Last Updated: 2025-09-21*
*Copy and adapt for your tech stack*