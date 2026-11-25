"""Theme 4: how much of a data center's electricity is renewable, slot by slot.

Three ways of counting the same year, on the 30-minute supply-and-demand records that Hokkaido
Electric Power Network publishes for its area. See docs/formulations/matching.md.

    records     the published records: download, read and check
    score       yearly volume, slot-by-slot matching, storage and shifting within the day
    system      what an added load and added solar and wind change in the area's records
    portfolio   the cheapest mix of solar, wind and storage for a target share of matched slots (LP)
"""
