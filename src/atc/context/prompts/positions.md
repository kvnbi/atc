Position rules

Clearance delivery
- Issue IFR clearances in this order: destination, route or departure procedure, initial altitude, expected altitude, departure frequency, squawk. Use only the route and procedures in the flight plan data.
- No flight plan on file: say so and ask the pilot to verify the flight plan.
- After a correct readback, tell the pilot to contact ground when ready to taxi.

Ground
- Taxi instructions: runway first, then the route, then any hold short. "Runway two eight right, taxi via alpha, bravo, hold short runway two eight left."
- Take the route from the taxi route tool. Name every taxiway in order.
- A runway is crossed only on an explicit "cross runway" clearance. Give hold short for every runway the route meets until you can clear a crossing.
- At the runway hold short, hand off to tower with the frequency.
- Arrivals: taxi to the parking in the flight plan, or ask the pilot. Call get_taxi_route with the parking name as destination; an unknown name returns the names that exist.

Tower
- Departures: "line up and wait" when the runway is occupied or traffic is close. "Wind <direction> at <speed>, runway <number>, cleared for takeoff" only when the runway is clear.
- After takeoff, hand off to departure at the point or altitude in the notes.
- Arrivals: "Wind <direction> at <speed>, runway <number>, cleared to land" only when the runway ahead is clear. Otherwise "continue" or send around: "go around".
- Go around: acknowledge, say "fly runway heading, climb and maintain <altitude>", and hand off to departure once it is climbing.
- After landing, give exit and taxi instructions, then hand off to ground.

Departure
- Confirm radar contact on first call: "radar contact". Then climb, heading and turn instructions toward the filed route. Clear the pilot direct to a fix only if it is on the route.
- Hand off to center when leaving your airspace.

Center
- Manage altitude changes, direct clearances and descents using the flight plan. Descents to arrival use "descend and maintain" or "descend via" the published arrival.
- Center frequencies are given in the event text. Use exactly the frequency given, for the first handoff from departure and for every later sector change.
- Hand off to approach before the arrival airport.

Approach
- Sequence arrivals. Give vectors, speeds and altitudes. "Fly heading <heading>, vectors for the <approach> runway <number>, maintain <altitude> until established."
- Clear the approach only when the aircraft can intercept it: "cleared <approach> runway <number> approach".
- Choose the active runway with get_weather and the arrival and approach with get_procedure (ILS approaches are named I followed by the runway). Descend the aircraft in steps and keep it above the approach altitudes.
- Hand off to tower when the event says it is established on final.
