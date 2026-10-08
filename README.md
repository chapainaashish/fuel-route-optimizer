# Fuel Route Optimizer

A Django REST API that takes a start and a finish location in the contiguous US and returns the driving route along with the cheapest places to refuel on the way.

The vehicle has a 500-mile range and gets 10 MPG, so a full tank is 50 gallons. The API finds fuel stations within 10 miles of the route, then picks where to stop and how much to buy so the total fuel cost is as low as possible.

## Technologies Used

| Area                | Technology                     | Used for                                                                |
| :------------------ | :----------------------------- | :---------------------------------------------------------------------- |
| Language            | Python 3.12+                   | Everything                                                              |
| Web framework       | Django                         | Project structure, ORM, management commands                             |
| API layer           | Django REST Framework          | Request validation (serializers), views, error responses                |
| Database            | SQLite                         | Storing the deduplicated fuel stations                                  |
| Numerics            | NumPy                          | Vectorized haversine distances, route resampling, coordinate conversion |
| Spatial search      | SciPy (`cKDTree`)              | Fast nearest-neighbor search between stations and route points          |
| Routing & geocoding | OpenRouteService (ORS)         | Driving directions and address geocoding                                |
| HTTP client         | `requests` (`Session`)         | Calls to ORS with connection reuse                                      |
| Station coordinates | SimpleMaps US Cities, GeoNames | Offline geocoding of the raw fuel price dataset                         |

## Performance & API Efficiency

- **External Call Minimization**:
  - Direct coordinate requests: **0 geocode calls, 1 route call**.
  - Text address requests: **2 geocode calls (cached for 30 days), 1 route call (cached for 24 hours)**.
- **Spatial Search Speed**:
  - Bounding box database pre-filtering reduces search scope from 6,600+ stations to a few hundred.
  - SciPy `cKDTree` performs nearest-neighbor lookups in \(O(\log N)\) time, completing corridor searches in under 50ms even for transcontinental routes.
- **Connection Reuse**:
  - Persistent HTTP connection pooling through `requests.Session()` reduces TLS handshake latency to external services.

## How to Setup

### Prerequisites

- Python 3.12 or newer
- `pip`
- A free OpenRouteService API key from [openrouteservice.org](https://openrouteservice.org/)

### Steps

1. **Clone the repository**

   ```bash
   git clone <repository-url>
   cd fuel-route-optimizer
   ```

2. **Create and activate a virtual environment**

   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**

   Create a `.env` file in the project root (see `.env_example`):

   ```env
   SECRET_KEY=your-django-secret-key-here
   ORS_API_KEY=your-openrouteservice-api-key-here
   ```

5. **Start the development server**

   ```bash
   python manage.py runserver
   ```

   The API is now available at `http://127.0.0.1:8000/api/route/`.

## Assumptions

**Starting fuel**

- The vehicle leaves the starting point with a **full tank** (500-mile range, 50 gallons).
- **Initial tank fuel is not billed to the trip.** Only fuel bought at truck stops along the route counts toward `total_fuel_cost`.

**Vehicle**

- Maximum range is **500 miles** on a full tank.
- Fuel economy is a constant **10 MPG**.
- Tank capacity is **50 gallons** (500 miles / 10 MPG).
- Fuel consumption is **linear** with distance.

**Station data**

- The original source dataset (`fuel-prices-for-be-assessment.csv`) has station names, highway addresses and cities, but **no coordinates**.
- Geocoding 8,000+ stations at request time would be too slow and would exceed external API rate limits, so station locations are resolved **offline to city-level center coordinates** using SimpleMaps US Cities and GeoNames (see [`docs/Coordinates.md`](docs/Coordinates.md)).
- Several stations share the same `OPIS Truckstop ID` across fuel racks or pricing tiers. During import, duplicates are resolved by keeping the **lowest retail price** for each truck stop.

**Search corridor**

- A station is a refueling candidate if it is within **10 miles** of the driving route (`radius_miles = 10.0`).

**Geographic scope**

- Only the **contiguous United States** (lower 48 states plus Washington, D.C.) is supported.
- Canadian stations in the raw dataset are excluded, and coordinates outside the bounding box (24.4 ≤ lat ≤ 49.6, -125.0 ≤ lon ≤ -66.9) are rejected during validation.

**External API usage**

- Free routing tiers have tight rate limits, so the system makes **one routing API call** per unique route.
- Address geocoding is cached for **30 days** and full routes for **24 hours**.
- When coordinates are supplied directly, **no geocoding calls** are made.

## Algorithm

The request goes through six stages. The last two do the real optimization.

### Step 1: Validate the request

Both `start` and `finish` must be either an address or a `"lat,lon"` string. They are cleaned, checked against the contiguous US bounds, and rejected if they are identical or if the body has unknown fields.

### Step 2: Resolve locations and fetch the route

Addresses are geocoded through OpenRouteService (cached for 30 days). Coordinates skip this step. A single driving-directions call then returns the route geometry, total distance and duration (cached for 24 hours).

### Step 3: Narrow down the stations with a bounding box

The route's bounding box, padded by the 10-mile corridor radius, is used to query SQLite. This removes most stations in the country before any spatial math runs.

### Step 4: Measure the route and place each station on it

1. Calculate the cumulative distance along the route using the haversine formula.
2. Rescale it so the total matches the distance reported by the router.
3. Resample the route every **0.25 miles**, giving evenly spaced points with a mile marker each.
4. Convert latitude/longitude to 3D coordinates on a sphere.
5. Build a `cKDTree` from the route points and find each station's nearest route point.
6. Keep stations within 10 miles. Each one gets a `mile_marker` (how far along the route it is) and a `distance_to_route_miles`.

### Step 5: Prepare the optimizer's input

Stations are sorted by `mile_marker`. The destination is added as a final node at `total_miles` with a price of **$0.00**, so the algorithm treats reaching the destination like reaching a free station and no special end-of-trip logic is needed.

### Step 6: Walk the route with the greedy algorithm

Start at mile 0 with a full tank, then repeat:

1. **Find everything reachable.** Build the list of stations ahead that fit within range. At the start that's the starting fuel. At a station it's a full tank. If the list is empty, raise `NoFeasiblePlan`.
2. **At the start,** buy nothing. Go straight to the destination if it's reachable, otherwise to the cheapest reachable station.
3. **At a station, look for a cheaper one ahead.**
   - **If a cheaper station is in range,** go to the first one and buy only the shortfall: `max(0, distance to it - fuel on hand)`. If you already have enough, buy nothing.
   - **If nothing cheaper is in range,** this is the best price within a full tank. Fill up (`max_range - fuel`) and head for the cheapest station in range, using the closer one on ties.
4. **Record the purchase.** Gallons = miles bought / 10, cost = gallons × the station's price.
5. **Drive to the next stop** and update the fuel on hand.
6. **Stop when the destination is reached.** Return the stops, total gallons and total cost.

Because the destination costs $0, it counts as "cheaper" than any real station as soon as it's within reach. That's why the final leg only buys enough fuel to arrive.

## Core Files

### 1. Request Validation (`routeplanner/serializers.py`)

- **`LocationField`**: A custom DRF field that accepts either:
  - Human-readable address / city strings (e.g., `"New York, NY"`, `"Austin, TX"`), or
  - Direct coordinates in `"lat,lon"` format (e.g., `"32.79,-96.77"`).
- **Validation Rules**:
  - Validates coordinate inputs against the contiguous US bounding box (`LAT_MIN = 24.4, LAT_MAX = 49.6, LON_MIN = -125.0, LON_MAX = -66.9`).
  - Strips invisible control characters, normalizes whitespace, and enforces length limits (2 to 120 characters).
  - Ensures `start` and `finish` locations are not identical.
  - Rejects unrecognized request body fields to prevent parameter injection.

### 2. Routing & Geocoding Service (`routeplanner/services/routing.py`)

- **OpenRouteService (ORS) Integration**:
  - Connects to the OpenRouteService API for geocoding and driving car directions.
  - Reuses an underlying `requests.Session()` to avoid TCP/TLS handshake overhead across requests.
- **Smart Caching**:
  - `geocode_location()` caches coordinates for **30 days** (`geo:<query>`).
  - `get_route()` caches detailed route geometry, distance, and duration for **24 hours** (`route:<start_lat,start_lon>:<end_lat,end_lon>`).
- **Zero-to-Few API Overhead**:
  - Coordinate inputs bypass the geocoder entirely.
  - Only a single call to the directions endpoint (`/v2/directions/driving-car/geojson`) is performed for new routes.

### 3. Spatial Station Corridor Discovery (`routeplanner/services/stations.py`)

Finding which of the 6,600+ stations are near an 800+ mile route in sub-second time is accomplished through a multi-stage spatial pipeline:

1. **Bounding Box DB Pre-Filter**: Queries SQLite with `lat__gte`, `lat__lte`, `lon__gte`, `lon__lte` using the route's bounding box expanded by the 10-mile corridor radius. This instantly eliminates ~95% of irrelevant stations nationwide at the database layer.
2. **Haversine Distance & Resampling**: Calculates cumulative driving distances along the route geometry. It resamples the driving route every **0.25 miles** (`ROUTE_SAMPLE_STEP_MILES = 0.25`) to produce an evenly spaced trajectory with exact mile markers.
3. **Spherical 3D Projection (`_to_xyz`)**: Converts latitude and longitude angles into 3D Cartesian coordinates \((x, y, z)\) on Earth's sphere (\(R = 3958.8\text{ miles}\)):
   \[
   x = R \cos(\text{lat}) \cos(\text{lon}), \quad y = R \cos(\text{lat}) \sin(\text{lon}), \quad z = R \sin(\text{lat})
   \]
4. **SciPy `cKDTree` Nearest Neighbor Search**: Builds a k-d tree from the resampled route points. Candidate stations are queried against the tree with an upper distance bound of 10 miles (`distance_upper_bound = 10.0`).
5. **Mile Marker Assignment**: Associates each nearby station with its projected distance along the trip (`mile_marker`) and its lateral distance from the highway (`distance_to_route_miles`).

### 4. Greedy Fuel Purchase Optimizer (`routeplanner/services/optimizer.py`)

The fueling decision is solved using an optimal **Greedy Lookahead Strategy**:

1. **Station Sorting**: All candidate stations along the route are sorted chronologically by their `mile_marker`. The destination is appended as the final node at `marker = total_miles` with a price of `$0.00`.
2. **Reachable Window Scan**: From the current location and fuel level, the optimizer scans all stations within reach (up to `max_range = 500 miles` ahead).
3. **Purchase Strategy**:
   - **Case A: A cheaper station exists ahead within range**: The vehicle buys **only enough fuel** at the current station to safely reach that first cheaper station:
     \[
     \text{buy_miles} = \max(0, \text{cheaper_marker} - \text{current_marker} - \text{current_fuel})
     \]
     This prevents purchasing expensive fuel when cheaper fuel is just ahead.
   - **Case B: No cheaper station exists ahead within range**: The current station is the cheapest in the entire 500-mile horizon! The vehicle **fills the tank completely** to capacity:
     \[
     \text{buy_miles} = \text{max_range} - \text{current_fuel}
     \]
4. **Feasibility Validation**: If at any point the next reachable station or destination is farther than the vehicle's remaining range, a `NoFeasiblePlan` exception is raised (mapped to HTTP 422).

### 5. Data Pipeline & Management (`routeplanner/management/commands/load_stations.py`)

- Imports preprocessed station data from `data/fuel_prices_with_coords.csv`.
- Filters invalid rows, strips whitespace, standardizes two-letter state codes.
- Deduplicates stations on `OPIS Truckstop ID` by retaining the record with the minimum retail price.
- Performs bulk creation (`FuelStation.objects.bulk_create`) for efficient database loading.

## API Documentation

**Endpoint:** `POST /api/route/`

**Body** (`application/json`):

- `start` (string, required): Departure address or `"lat,lon"` within the contiguous US.
- `finish` (string, required): Destination address or `"lat,lon"` within the contiguous US.

### 1. Using City / State Names (cURL)

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{
    "start": "New York, NY",
    "finish": "Atlanta, GA"
  }'
```

#### 2. Using Direct GPS Coordinates (cURL)

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{
    "start": "40.7128,-74.0060",
    "finish": "33.7490,-84.3880"
  }'
```

### Example Response

A trip from **New York, NY** to **Atlanta, GA** (~882 miles):

```json
{
  "start": {
    "query": "New York, NY",
    "lat": 40.68295,
    "lon": -73.9708
  },
  "finish": {
    "query": "Atlanta, GA",
    "lat": 33.769805,
    "lon": -84.414581
  },
  "distance_miles": 882.14,
  "duration_seconds": 56645,
  "geometry_points": 8102,
  "geometry": [
    [40.682947, -73.970825],
    [40.682981, -73.970832],
    [40.683329, -73.9709],
    "..."
  ],
  "fuel_plan": {
    "max_range_miles": 500.0,
    "mpg": 10.0,
    "tank_gallons": 50.0,
    "total_gallons_purchased": 38.21,
    "total_fuel_cost": 109.06,
    "stops": [
      {
        "opis_id": 63516,
        "name": "SHEETZ #701",
        "address": "I-81, EXIT 273",
        "city": "Mount Jackson",
        "state": "VA",
        "lat": 38.739,
        "lon": -78.651,
        "mile_marker": 327.46,
        "distance_to_route_miles": 0.12,
        "price_per_gallon": 2.874,
        "gallons_purchased": 5.42,
        "cost": 15.57
      },
      {
        "opis_id": 72706,
        "name": "Sheetz #790",
        "address": "I-77 EXIT 100",
        "city": "Mount Airy",
        "state": "NC",
        "lat": 36.5083,
        "lon": -80.6155,
        "mile_marker": 554.18,
        "distance_to_route_miles": 7.04,
        "price_per_gallon": 2.859,
        "gallons_purchased": 5.22,
        "cost": 14.94
      },
      {
        "opis_id": 69964,
        "name": "SHEETZ #621",
        "address": "I-77 & US-70, Exit 49A",
        "city": "Statesville",
        "state": "NC",
        "lat": 35.7842,
        "lon": -80.8713,
        "mile_marker": 606.42,
        "distance_to_route_miles": 0.45,
        "price_per_gallon": 2.849,
        "gallons_purchased": 27.57,
        "cost": 78.55
      }
    ]
  },
  "total_fuel_cost": 109.06,
  "stations_near_route_count": 257,
  "stations_near_route": [
    {
      "opis_id": 72087,
      "name": "DELTA",
      "address": "US-9",
      "city": "Jersey City",
      "state": "NJ",
      "price": 3.239,
      "lat": 40.7184,
      "lon": -74.0686,
      "mile_marker": 6.25,
      "distance_to_route_miles": 1.26
    },
    "..."
  ]
}
```

#### Field Explanations

- **`start` / `finish`**: The resolved location with normalized query and latitude/longitude.
- **`distance_miles`**: Total driving distance along the route.
- **`duration_seconds`**: Driving time estimate in seconds from ORS.
- **`geometry`**: Ordered `[lat, lon]` coordinates representing the complete route line for mapping libraries (Leaflet, Mapbox, Google Maps).
- **`fuel_plan`**:
  - `tank_gallons`: Tank capacity (50 gal).
  - `total_gallons_purchased`: Total gallons bought at intermediate stops.
  - `total_fuel_cost`: Total dollar amount spent on fuel during the journey.
  - `stops`: Sequence of optimal refueling stops with exact mile markers, distance from highway, station metadata, gallons bought, and purchase cost.
- **`stations_near_route`**: All candidate stations discovered within the 10-mile corridor.

### Error Responses

| Status                     | When it happens                                                                                                     | Example                                                       |
| :------------------------- | :------------------------------------------------------------------------------------------------------------------ | :------------------------------------------------------------ |
| `400 Bad Request`          | Invalid input: coordinates outside the US, same start and finish, unknown fields, or a location that can't be found | `{"error": "Could not find location: 'InvalidPlace'"}`        |
| `422 Unprocessable Entity` | No feasible plan: the gap between reachable stations is longer than 500 miles                                       | `{"error": "No fuel station within range after mile 482.3."}` |
| `502 Bad Gateway`          | OpenRouteService returned an error or timed out                                                                     | `{"error": "Routing service failed: ..."}`                    |
