from dataclasses import dataclass

from routeplanner.exceptions import NoFeasiblePlan

MAX_RANGE_MILES = 500.0
MPG = 10.0
EPS = 1e-9  # to avoid tiny floating point rounding errors during operation


@dataclass
class _Node:
    marker: float
    price: float  # $/gallon
    item: dict | None  # a stations_near_route() entry; None for the destination


def plan_fuel_stops(
    nearby,
    total_miles: float,
    max_range: float = MAX_RANGE_MILES,
    mpg: float = MPG,
    start_fuel_miles: float | None = None,
):
    """
    Cheapest fueling plan. Assumes the vehicle starts with `start_fuel_miles`
    of range (default: a full tank) and that initial fuel is not charged to
    the trip; only fuel bought along the route is counted.
    """
    fuel = max_range if start_fuel_miles is None else start_fuel_miles

    # Only create a node if the station's mile marker is within the actual route
    nodes = [
        _Node(n["mile_marker"], float(n["station"].price), n)
        for n in nearby
        if 0 <= n["mile_marker"] < total_miles
    ]
    nodes.sort(key=lambda n: n.marker)
    nodes.append(
        _Node(total_miles, 0.0, None)
    )  # destination(we don't buy fuel at destination so it's 0)
    last = len(nodes) - 1

    cur_pos, cur_node, k = 0.0, None, 0
    stops, total_cost, total_gallons = [], 0.0, 0.0

    while True:
        # How far we could possibly get from this point
        reach = max_range if cur_node else fuel
        window = []
        j = k

        # Get all the reachable stations from one point
        while j <= last and nodes[j].marker - cur_pos <= reach + EPS:
            window.append(j)
            j += 1
        if not window:
            raise NoFeasiblePlan(
                f"No fuel station within range after mile {cur_pos:.1f}."
            )

        buy_miles = 0.0
        if cur_node is None:
            # At the start: nothing to buy, just head for the destination directly or get the cheapest station reachable on the current fuel
            target = (
                last
                if last in window
                else min(window, key=lambda i: (nodes[i].price, nodes[i].marker))
            )
        else:
            # get the cheaper point where the fuel price is cheaper than here
            cheaper = next((i for i in window if nodes[i].price < cur_node.price), None)

            # If a cheaper point is reachable, buy the minimum here, because you'll get cheaper fuel there
            if cheaper is not None:
                target = cheaper
                buy_miles = max(0.0, nodes[target].marker - cur_pos - fuel)

            # If not, buy the maximum here, because this is the cheapest fuel you'll see for a full tank
            else:
                target = min(window, key=lambda i: (nodes[i].price, nodes[i].marker))
                buy_miles = max_range - fuel  # fill up

        if buy_miles > EPS:
            gallons = buy_miles / mpg
            cost = gallons * cur_node.price
            s = cur_node.item
            stops.append(
                {
                    "opis_id": s["station"].opis_id,
                    "name": s["station"].name,
                    "address": s["station"].address,
                    "city": s["station"].city,
                    "state": s["station"].state,
                    "lat": s["station"].lat,
                    "lon": s["station"].lon,
                    "mile_marker": round(cur_node.marker, 2),
                    "distance_to_route_miles": round(s["distance_to_route_miles"], 2),
                    "price_per_gallon": round(cur_node.price, 3),
                    "gallons_purchased": round(gallons, 2),
                    "cost": round(cost, 2),
                }
            )
            total_cost += cost
            total_gallons += gallons

        travel = nodes[target].marker - cur_pos
        fuel = fuel + buy_miles - travel
        cur_pos = nodes[target].marker
        k = target + 1
        if target == last:
            break
        cur_node = nodes[target]

    return {
        "max_range_miles": max_range,
        "mpg": mpg,
        "tank_gallons": round(max_range / mpg, 2),
        "total_gallons_purchased": round(total_gallons, 2),
        "total_fuel_cost": round(total_cost, 2),
        "stops": stops,
    }
