"""Theme 3: siting the next data center.

A first screen: where the waste heat of a new data center is worth most (theme 1), and what the
grid connection costs there (distances on the public map, until theme 2 has a network model of
the area). See docs/formulations/siting.md.

    candidates   candidate sites: a grid over the municipality, snapped to roads
    heat_value   the value of a new data center's waste heat at a site, from the heat-network model
    gridmap      transmission lines and substations from OpenStreetMap, and distances to them
    model        the location model that picks sites
"""
