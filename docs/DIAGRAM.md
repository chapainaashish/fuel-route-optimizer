```
1. Accept source + destination
   │
   ├── coordinates?
   │       ↓
   │     use directly
   │
   └── address?
           ↓
       geocoding
           ↓
       lat/lon
           │
           ▼
2. Get driving route
   │
   │  1 routing API call
   ▼
3. Route geometry + distance
   │
   ▼
4. Find fuel stations near route
   │
   │  PostGIS / spatial index / KD-tree
   ▼
5. Candidate stations
   │
   ▼
6. Calculate each station's position
   │   along the route
   ▼
7. Fuel optimization
   │
   ├── 500 mile maximum range
   ├── 10 MPG
   ├── station prices
   └── distance between stations
   │
   ▼
8. Calculate fuel purchases
   │
   ▼
9. Calculate total cost
   │
   ▼
10. Return JSON
    │
    ├── route geometry
    ├── total distance
    ├── fuel stops
    ├── fuel prices
    ├── gallons purchased
    └── total fuel cost

```

```
START
  │
  │ position = 0
  │ fuel = 500
  │ current_price = ∞
  ▼
Find stations near route
  │
Compute mile markers
  │
Sort by mile marker
  │
Add destination
  │
  ▼
Find stations within next 500 miles
  │
  ├── Destination reachable?
  │       └── Yes → destination becomes possible target
  │
  ▼
Is there a cheaper station ahead?
  │
  ├── YES
  │    │
  │    ▼
  │  target = FIRST cheaper station
  │    │
  │    ▼
  │  buy enough to reach target
  │
  └── NO
       │
       ▼
     target = CHEAPEST station
     within next 500 miles
       │
       ▼
     fill tank
       │
       ▼
     drive to target
       │
       ▼
 update fuel/position/current_price
       │
       └──────► repeat
```

```
START
  │  position = 0, fuel = 500, current_price = ∞
  ▼
Find stations near route → compute mile markers → sort
Add destination (price 0, mile = total_dist)
  │
  ▼
┌─► Stations within (position, position + 500]?
│     NONE ──► ERROR
│     ▼
│   Any station in range with price < current_price?
│     │
│     ├── YES: target = FIRST cheaper (route order)
│     │        buy = max(0, distance_to_target − fuel)
│     │
│     └── NO:  target = CHEAPEST in range (earliest if tied)
│              buy = 500 − fuel   (fill the tank)
│     ▼
│   Pay: cost += (buy / 10) × current_price
│   Drive: fuel = fuel + buy − distance_to_target
│          position = target.mile
│          current_price = target.price
│     ▼
│   Target is destination?
│     NO ──► loop back
└─────┘
     YES ──► return stops, total cost

```
