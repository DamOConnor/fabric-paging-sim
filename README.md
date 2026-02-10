# Fabric Paging Simulator

A Python Azure Function app that simulates REST API pagination patterns for testing **Microsoft Fabric Data Pipeline Copy Activity** pagination rules.

## Pagination Endpoints

| Endpoint | Pattern | Key Response Field |
|---|---|---|
| `GET /api/paging/nextlink` | OData `@odata.nextLink` in body | `$.@odata.nextLink` |
| `GET /api/paging/header` | `Link` header with `rel="next"` | `Link` response header |
| `GET /api/paging/offset` | Offset / Limit query params | `$.nextUrl`, `$.nextOffset` |
| `GET /api/paging/pagenumber` | Page number query param | `$.pagination.nextPageUrl` |
| `GET /api/paging/cursor` | Cursor / continuation token | `$.continuationToken` |
| `GET /api/paging/bookmark` | ERP-style XML bookmark | `$.Bookmark`, `$.MoreRowsExist` |
| `GET /api/info` | API documentation | — |

## Common Query Parameters

All pagination endpoints accept:

| Parameter | Default | Max | Description |
|---|---|---|---|
| `totalRecords` | 100 | 10,000 | Total number of records in the simulated dataset |
| `pageSize` / `limit` | 10 | 500 | Number of records returned per page |
| `delay` | 0 | 5,000 | Simulated response delay in milliseconds |

Plus endpoint-specific params like `$skip`, `page`, `offset`, `cursor`.

## Prerequisites

- **Python 3.9+**
- **Azure Functions Core Tools v4** (`npm install -g azure-functions-core-tools@4`)

## Running Locally

```bash
# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate     # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Start the function app
func start
```

The API will be available at `http://localhost:7071`.

## Example Requests

```bash
# First page of 50 records, 10 per page (OData style)
curl http://localhost:7071/api/paging/nextlink?totalRecords=50&pageSize=10

# Page 2 with Link header pagination
curl -i http://localhost:7071/api/paging/header?totalRecords=50&pageSize=10&page=2

# Offset pagination with 500ms delay
curl http://localhost:7071/api/paging/offset?totalRecords=100&limit=25&offset=0&delay=500

# Start cursor-based pagination
curl http://localhost:7071/api/paging/cursor?totalRecords=50&pageSize=10

# Start bookmark-style pagination
curl http://localhost:7071/api/paging/bookmark?totalRecords=50&pageSize=10

# API documentation
curl http://localhost:7071/api/info
```

## Configuring Fabric Copy Activity

### 1. NextLink (OData) Pattern
In your Copy Activity **Source** settings:
- **Pagination rules**:
  - `AbsoluteUrl` = `$['@odata.nextLink']`

### 2. Link Header Pattern (RFC 5988)
- **Pagination rules**:
  - `SupportRFC5988` = `true`

### 3. Offset/Limit Pattern
- **Pagination rules**:
  - `AbsoluteUrl` = `$.nextUrl`
  - Or use `QueryParameters.offset` = `$.nextOffset`

### 4. Page Number Pattern
- **Pagination rules**:
  - `AbsoluteUrl` = `$.pagination.nextPageUrl`
  - Or use `QueryParameters.page` = `{iteration + 1}` with end condition `$.pagination.hasNextPage` = `false`

### 5. Cursor/Continuation Token Pattern
- **Pagination rules**:
  - `QueryParameters.cursor` = `$.continuationToken`
  - End condition: `$.hasMore` = `false`

### 6. Bookmark (ERP-style) Pattern
- **Pagination rules**:
  - `QueryParameters.bookmark` = `$.Bookmark`
  - End condition: `$.MoreRowsExist` = `false`

## Example Responses

### NextLink
```json
{
  "@odata.context": "http://localhost:7071/api/paging/nextlink/$metadata",
  "@odata.count": 50,
  "value": [
    { "id": 1, "firstName": "James", "lastName": "Smith", ... },
    ...
  ],
  "@odata.nextLink": "http://localhost:7071/api/paging/nextlink?totalRecords=50&pageSize=10&$skip=10"
}
```

### Cursor
```json
{
  "data": [
    { "id": 1, "firstName": "James", "lastName": "Smith", ... },
    ...
  ],
  "pageSize": 10,
  "totalRecords": 50,
  "hasMore": true,
  "continuationToken": "eyJvZmZzZXQiOiAxMCwgInRzIjogIjIwMjUtMDEtMDFUMDA6MDA6MDBaIn0=",
  "nextUrl": "http://localhost:7071/api/paging/cursor?..."
}
```

## Generated Data Schema

Each record contains:

| Field | Type | Example |
|---|---|---|
| `id` | int | `1` |
| `firstName` | string | `"James"` |
| `lastName` | string | `"Smith"` |
| `email` | string | `"james.smith@contoso.com"` |
| `department` | string | `"Engineering"` |
| `city` | string | `"Seattle"` |
| `salary` | float | `125000.50` |
| `hireDate` | string (date) | `"2021-03-15"` |
| `isActive` | boolean | `true` |

Data is deterministically generated — the same record ID always produces the same data, ensuring consistent results across pages and requests.

## Deploy to Azure

```bash
# Create resource group
az group create -n rg-fabric-paging-sim -l uksouth

# Deploy infrastructure (storage, identity, function app)
az deployment group create -g rg-fabric-paging-sim -f bicep/main.bicep -p bicep/main.bicepparam

# Publish the function code
func azure functionapp publish fabric-paging-sim
```

## Project Structure

```
fabric-paging-sim/
├── function_app.py       # HTTP trigger endpoints
├── pagination.py         # 5 pagination strategy implementations
├── data_generator.py     # Deterministic fake record generator
├── host.json             # Azure Functions host config
├── requirements.txt      # Python dependencies
├── bicep/
│   ├── main.bicep        # Infrastructure-as-code (Flex Consumption)
│   └── main.bicepparam   # Default parameters
└── README.md
```

## Links

- https://learn.microsoft.com/en-us/azure/data-factory/connector-rest?tabs=data-factory#pagination-support
- https://techcommunity.microsoft.com/blog/fasttrackforazureblog/implementing-pagination-with-the-copy-activity-in-microsoft-fabric/3914977