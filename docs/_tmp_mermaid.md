# temporary: mermaid rendering test

## V1 control

```mermaid
flowchart LR
  REC["Area supply and demand records<br/>30-minute values from the operator"] --> CHK["Read and check<br/>no gaps, supply equals demand"]
  LOAD["Data-center load<br/>constant, an assumption"] --> CNT["Three counts<br/>by the year, by the slot, on the grid"]
  CHK --> CNT
  CHK --> RPL["Replay of the records<br/>added load, added solar and wind"]
  CHK --> LP["Linear program (HiGHS / Gurobi)<br/>cheapest contract and battery<br/>for a target match"]
  PRC["Published generation costs<br/>and battery prices"] --> LP
  CNT --> APP4["App page, figure<br/>and document"]
  RPL --> APP4
  LP --> APP4
```

## V2 LOAD renamed

```mermaid
flowchart LR
  REC["Area supply and demand records<br/>30-minute values from the operator"] --> CHK["Read and check<br/>no gaps, supply equals demand"]
  DCLOAD["Data-center load<br/>constant, an assumption"] --> CNT["Three counts<br/>by the year, by the slot, on the grid"]
  CHK --> CNT
  CHK --> RPL["Replay of the records<br/>added load, added solar and wind"]
  CHK --> LP["Linear program (HiGHS / Gurobi)<br/>cheapest contract and battery<br/>for a target match"]
  PRC["Published generation costs<br/>and battery prices"] --> LP
  CNT --> APP4["App page, figure<br/>and document"]
  RPL --> APP4
  LP --> APP4
```

## V3 REC renamed

```mermaid
flowchart LR
  RECORDS["Area supply and demand records<br/>30-minute values from the operator"] --> CHK["Read and check<br/>no gaps, supply equals demand"]
  LOAD["Data-center load<br/>constant, an assumption"] --> CNT["Three counts<br/>by the year, by the slot, on the grid"]
  CHK --> CNT
  CHK --> RPL["Replay of the records<br/>added load, added solar and wind"]
  CHK --> LP["Linear program (HiGHS / Gurobi)<br/>cheapest contract and battery<br/>for a target match"]
  PRC["Published generation costs<br/>and battery prices"] --> LP
  CNT --> APP4["App page, figure<br/>and document"]
  RPL --> APP4
  LP --> APP4
```

## V4 CNT renamed

```mermaid
flowchart LR
  REC["Area supply and demand records<br/>30-minute values from the operator"] --> CHK["Read and check<br/>no gaps, supply equals demand"]
  LOAD["Data-center load<br/>constant, an assumption"] --> COUNTS["Three counts<br/>by the year, by the slot, on the grid"]
  CHK --> COUNTS
  CHK --> RPL["Replay of the records<br/>added load, added solar and wind"]
  CHK --> LP["Linear program (HiGHS / Gurobi)<br/>cheapest contract and battery<br/>for a target match"]
  PRC["Published generation costs<br/>and battery prices"] --> LP
  COUNTS --> APP4["App page, figure<br/>and document"]
  RPL --> APP4
  LP --> APP4
```

## V5 LP renamed

```mermaid
flowchart LR
  REC["Area supply and demand records<br/>30-minute values from the operator"] --> CHK["Read and check<br/>no gaps, supply equals demand"]
  LOAD["Data-center load<br/>constant, an assumption"] --> CNT["Three counts<br/>by the year, by the slot, on the grid"]
  CHK --> CNT
  CHK --> RPL["Replay of the records<br/>added load, added solar and wind"]
  CHK --> LPROG["Linear program (HiGHS / Gurobi)<br/>cheapest contract and battery<br/>for a target match"]
  PRC["Published generation costs<br/>and battery prices"] --> LPROG
  CNT --> APP4["App page, figure<br/>and document"]
  RPL --> APP4
  LPROG --> APP4
```

## V6 RPL PRC CHK renamed

```mermaid
flowchart LR
  REC["Area supply and demand records<br/>30-minute values from the operator"] --> CHECK["Read and check<br/>no gaps, supply equals demand"]
  LOAD["Data-center load<br/>constant, an assumption"] --> CNT["Three counts<br/>by the year, by the slot, on the grid"]
  CHECK --> CNT
  CHECK --> REPLAY["Replay of the records<br/>added load, added solar and wind"]
  CHECK --> LP["Linear program (HiGHS / Gurobi)<br/>cheapest contract and battery<br/>for a target match"]
  PRICES["Published generation costs<br/>and battery prices"] --> LP
  CNT --> APP4["App page, figure<br/>and document"]
  REPLAY --> APP4
  LP --> APP4
```

## V7 all renamed

```mermaid
flowchart LR
  RECORDS["Area supply and demand records<br/>30-minute values from the operator"] --> CHECK["Read and check<br/>no gaps, supply equals demand"]
  DCLOAD["Data-center load<br/>constant, an assumption"] --> COUNTS["Three counts<br/>by the year, by the slot, on the grid"]
  CHECK --> COUNTS
  CHECK --> REPLAY["Replay of the records<br/>added load, added solar and wind"]
  CHECK --> LPROG["Linear program (HiGHS / Gurobi)<br/>cheapest contract and battery<br/>for a target match"]
  PRICES["Published generation costs<br/>and battery prices"] --> LPROG
  COUNTS --> APP4["App page, figure<br/>and document"]
  REPLAY --> APP4
  LPROG --> APP4
```

## V8 no labels with brackets in LP

```mermaid
flowchart LR
  REC["Area supply and demand records<br/>30-minute values from the operator"] --> CHK["Read and check<br/>no gaps, supply equals demand"]
  LOAD["Data-center load<br/>constant, an assumption"] --> CNT["Three counts<br/>by the year, by the slot, on the grid"]
  CHK --> CNT
  CHK --> RPL["Replay of the records<br/>added load, added solar and wind"]
  CHK --> LP["Linear program"]
  PRC["Published generation costs<br/>and battery prices"] --> LP
  CNT --> APP4["App page, figure<br/>and document"]
  RPL --> APP4
  LP --> APP4
```
