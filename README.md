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
| `GET /api/paging/range` | Range query param (`?range=0-99`) | `$.nextUrl`, `$.nextRange` |
| `GET /api/paging/pagemeta` | Page number with `{data, metadata:{page,size,total}}` shape; configurable overflow behaviour | `$.metadata.total`, `$.data` |
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

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Adding a New Pagination Strategy

The HTTP layer is driven by the `STRATEGIES` registry in [pagination.py](pagination.py). To add a 9th endpoint:

1. Write `paginate_myNewThing(req, base_url) -> (body, delay_ms)` in `pagination.py`.
2. Append a `Strategy(...)` entry to `STRATEGIES`.

The route, error handling, and `/api/info` documentation are generated automatically. No edits to `function_app.py` required.

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

# Range-based pagination (records 0-24)
curl http://localhost:7071/api/paging/range?totalRecords=100&range=0-24

# Page-meta (SO-style). 10 records, 3 per page -> 4 pages
curl http://localhost:7071/api/paging/pagemeta?totalRecords=10&pageSize=3&page=1

# Simulate the broken-API overflow (HTTP 500 'Invalid URL')
curl -i http://localhost:7071/api/paging/pagemeta?totalRecords=10&pageSize=3&page=5&overflow=error

# Well-behaved variant: empty data on overflow
curl http://localhost:7071/api/paging/pagemeta?totalRecords=10&pageSize=3&page=5&overflow=empty

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

### 7. Range Pattern
- **Pagination rules** (choose one approach):
  - `AbsoluteUrl` = `$.nextUrl` (simplest)
  - `QueryParameters.range` = `$.nextRange` with end condition `$.hasMore` = `false`
  - `QueryParameters.start` = `$.nextStart` + `QueryParameters.stop` = `$.nextStop` with end condition `$.hasMore` = `false`

### 8. Page-Meta Pattern (SO-style, no `hasNext` field)

Response shape:
```json
{
  "data": [ /* records */ ],
  "metadata": { "page": 1, "size": 3, "total": 10 }
}
```

This endpoint reproduces the common real-world scenario (see [this Stack Overflow question](https://stackoverflow.com/questions/79926567/pagination-in-azure-data-factory-with-page)) where the API exposes `total` in metadata but provides **no** `hasNext` / `nextUrl` field, and may misbehave on out-of-range pages. Use the `overflow` query parameter to pick the bad behaviour:

| `overflow` | Status | Body on overflow | Use case |
|---|---|---|---|
| `error` (default) | 500 | `{"error": "Invalid URL", ...}` | Repros the SO bug |
| `empty` | 200 | `{"data": [], "metadata": {...}}` | Well-behaved API |
| `clamp` | 200 | Last valid page (silent) | Hardest to detect |
| `notfound` | 404 | `{"error": "Not Found", ...}` | Structured end-of-data |

**Fabric Copy Activity strategies:**

- **`overflow=empty`** (easy case): `QueryParameters.page` = `RANGE:1:9999`, end condition `$.data` = `Empty`.
- **`overflow=error`** (SO scenario — can't be solved by end conditions alone):
  1. Add a **Lookup** activity calling page 1 to read `$.metadata.total` and `$.metadata.size`.
  2. **Set Variable** `maxPage` = `@int(div(add(sub(total, 1), size), size))` (ceiling division, or use `divide` + `ceiling`).
  3. In Copy: `QueryParameters.page` = `RANGE:1:@{variables('maxPage')}`, or set `MaxRequestNumber = @{variables('maxPage')}`.
- **`overflow=clamp`**: never terminates on end-condition (the data keeps flowing duplicated). You **must** use `MaxRequestNumber` with a computed cap.

Example (your test case — 10 records, page size 3 → 4 valid pages):
```
GET /api/paging/pagemeta?totalRecords=10&pageSize=3&page=1    # 3 rows
GET /api/paging/pagemeta?totalRecords=10&pageSize=3&page=4    # 1 row (last page)
GET /api/paging/pagemeta?totalRecords=10&pageSize=3&page=5&overflow=error   # HTTP 500
GET /api/paging/pagemeta?totalRecords=10&pageSize=3&page=5&overflow=empty   # 200, data:[]
```

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
├── function_app.py       # HTTP layer: generic handler + /api/info (driven by registry)
├── pagination.py         # 8 pagination strategies + Strategy registry
├── data_generator.py     # Deterministic fake record generator
├── host.json             # Azure Functions host config
├── requirements.txt      # Python runtime dependencies
├── requirements-dev.txt  # pytest
├── pytest.ini            # pytest config
├── tests/                # Unit tests (49 tests, pure-Python, no Azure runtime)
├── bicep/
│   ├── main.bicep        # Infrastructure-as-code (Flex Consumption)
│   └── main.bicepparam   # Default parameters
└── README.md
```

## Links

- https://learn.microsoft.com/en-us/azure/data-factory/connector-rest?tabs=data-factory#pagination-support
- https://techcommunity.microsoft.com/blog/fasttrackforazureblog/implementing-pagination-with-the-copy-activity-in-microsoft-fabric/3914977