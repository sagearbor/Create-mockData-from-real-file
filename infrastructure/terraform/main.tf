# Terraform configuration for BYOD Synthetic Data Generator - Azure Infrastructure

terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
  required_version = ">= 1.0"
}

# Configure the Azure Provider
provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = true
    }
  }
}

# Variables
variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "rg-byod-synthetic-data"
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "East US"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "app_name" {
  description = "Application name"
  type        = string
  default     = "byod-synthetic"
}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  
  tags = {
    Environment = var.environment
    Application = var.app_name
    ManagedBy   = "Terraform"
  }
}

# Storage Account for file uploads
resource "azurerm_storage_account" "main" {
  name                     = "${replace(var.app_name, "-", "")}${var.environment}sa"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  
  blob_properties {
    versioning_enabled = true
    delete_retention_policy {
      days = 7
    }
  }
  
  tags = azurerm_resource_group.main.tags
}

# Storage Container for uploads
resource "azurerm_storage_container" "uploads" {
  name                  = "synthetic-data-uploads"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# Storage Container for cache
resource "azurerm_storage_container" "cache" {
  name                  = "generation-cache"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# App Service Plan
resource "azurerm_service_plan" "main" {
  name                = "${var.app_name}-${var.environment}-plan"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  os_type             = "Linux"
  sku_name            = var.environment == "prod" ? "P1v3" : "B1"
  
  tags = azurerm_resource_group.main.tags
}

# App Service for Web UI
resource "azurerm_linux_web_app" "main" {
  name                = "${var.app_name}-${var.environment}-app"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  service_plan_id     = azurerm_service_plan.main.id
  
  site_config {
    always_on = var.environment == "prod" ? true : false
    
    application_stack {
      python_version = "3.11"
    }
    
    app_command_line = "python main.py"
    
    cors {
      allowed_origins = ["*"]
    }
  }
  
  app_settings = {
    "AZURE_STORAGE_CONNECTION_STRING" = azurerm_storage_account.main.primary_connection_string
    "BLOB_STORAGE_CONTAINER_NAME"     = azurerm_storage_container.uploads.name
    "COSMOS_DB_ENDPOINT"              = azurerm_cosmosdb_account.main.endpoint
    "COSMOS_DB_KEY"                   = azurerm_cosmosdb_account.main.primary_key
    "COSMOS_DB_DATABASE_NAME"         = azurerm_cosmosdb_sql_database.main.name
    "COSMOS_DB_CONTAINER_NAME"        = azurerm_cosmosdb_sql_container.catalog.name
    "AZURE_SEARCH_ENDPOINT"           = "https://${azurerm_search_service.main.name}.search.windows.net"
    "AZURE_SEARCH_API_KEY"            = azurerm_search_service.main.primary_key
    "AZURE_SEARCH_INDEX_NAME"         = "program-vectors"
    "GENERATOR_VERSION"               = "1.0"
    "LOG_LEVEL"                       = var.environment == "prod" ? "INFO" : "DEBUG"
    "ENVIRONMENT"                     = var.environment
  }
  
  identity {
    type = "SystemAssigned"
  }
  
  tags = azurerm_resource_group.main.tags
}

# Function App for serverless processing
resource "azurerm_linux_function_app" "main" {
  name                = "${var.app_name}-${var.environment}-func"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  
  storage_account_name       = azurerm_storage_account.main.name
  storage_account_access_key = azurerm_storage_account.main.primary_access_key
  service_plan_id            = azurerm_service_plan.main.id
  
  site_config {
    python_version = "3.11"
    
    cors {
      allowed_origins = ["*"]
    }
  }
  
  app_settings = {
    "AzureWebJobsStorage"              = azurerm_storage_account.main.primary_connection_string
    "FUNCTIONS_WORKER_RUNTIME"         = "python"
    "AZURE_STORAGE_CONNECTION_STRING"  = azurerm_storage_account.main.primary_connection_string
    "COSMOS_DB_ENDPOINT"              = azurerm_cosmosdb_account.main.endpoint
    "COSMOS_DB_KEY"                   = azurerm_cosmosdb_account.main.primary_key
    "AZURE_OPENAI_ENDPOINT"           = var.azure_openai_endpoint
    "AZURE_OPENAI_API_KEY"            = var.azure_openai_api_key
  }
  
  identity {
    type = "SystemAssigned"
  }
  
  tags = azurerm_resource_group.main.tags
}

# Cosmos DB Account
resource "azurerm_cosmosdb_account" "main" {
  name                = "${var.app_name}-${var.environment}-cosmos"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  
  consistency_policy {
    consistency_level = "Session"
  }
  
  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }
  
  capabilities {
    name = "EnableServerless"
  }
  
  tags = azurerm_resource_group.main.tags
}

# Cosmos DB Database
resource "azurerm_cosmosdb_sql_database" "main" {
  name                = "SyntheticData"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
}

# Cosmos DB Container for Program Catalog
resource "azurerm_cosmosdb_sql_container" "catalog" {
  name                = "ProgramCatalog"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_path  = "/id"
  
  indexing_policy {
    indexing_mode = "consistent"
    
    included_path {
      path = "/*"
    }
  }
}

# Azure Cognitive Search
resource "azurerm_search_service" "main" {
  name                = "${var.app_name}-${var.environment}-search"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = var.environment == "prod" ? "standard" : "basic"
  
  tags = azurerm_resource_group.main.tags
}

# Key Vault for secrets
resource "azurerm_key_vault" "main" {
  name                = "${var.app_name}-${var.environment}-kv"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"
  
  purge_protection_enabled = var.environment == "prod" ? true : false
  
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id
    
    secret_permissions = [
      "Get",
      "List",
      "Set",
      "Delete",
      "Purge"
    ]
  }
  
  # Access policy for App Service
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = azurerm_linux_web_app.main.identity[0].principal_id
    
    secret_permissions = [
      "Get",
      "List"
    ]
  }
  
  # Access policy for Function App
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = azurerm_linux_function_app.main.identity[0].principal_id
    
    secret_permissions = [
      "Get",
      "List"
    ]
  }
  
  tags = azurerm_resource_group.main.tags
}

# Data source for current Azure subscription
data "azurerm_client_config" "current" {}

# Variables for sensitive data (should be provided via terraform.tfvars or environment variables)
variable "azure_openai_endpoint" {
  description = "Azure OpenAI endpoint"
  type        = string
  sensitive   = true
}

variable "azure_openai_api_key" {
  description = "Azure OpenAI API key"
  type        = string
  sensitive   = true
}

# Outputs
output "app_service_url" {
  value = "https://${azurerm_linux_web_app.main.default_hostname}"
}

output "function_app_url" {
  value = "https://${azurerm_linux_function_app.main.default_hostname}"
}

output "storage_account_name" {
  value = azurerm_storage_account.main.name
}

output "cosmos_db_endpoint" {
  value = azurerm_cosmosdb_account.main.endpoint
}

output "search_service_endpoint" {
  value = "https://${azurerm_search_service.main.name}.search.windows.net"
}