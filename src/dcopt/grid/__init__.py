"""Theme 2: grid hosting capacity.

How much data-center and heat-pump load each grid location can take: an AC optimal power flow that
maximizes the added load at a bus, bracketed by convex relaxations (upper bounds) and a verified
AC-feasible point (lower bound). See docs/formulations/grid.md.

    cases     the network data model, a MATPOWER reader, PGLib-OPF downloads, built-in systems
    lifted    the linear model in the lifted voltage products that all methods share
    relax     DC screening, the SOCP relaxation and the chordal SDP relaxation
    ac        the AC problem: an interior-point method and an independent feasibility check
    hosting   the bracket for a bus, for all buses, across load levels and under outages
"""
