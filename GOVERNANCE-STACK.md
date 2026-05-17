# Agent Governance Stack

This repo is one layer of a three-part agent coordination suite:

| Layer | Repo | Responsibility |
|-------|------|----------------|
| Dispatch | [contract-net-router](https://github.com/M00C1FER/contract-net-router) | Formal bid/award/audit for task assignment (FIPA CNP) |
| Coordination | [common-operating-picture](https://github.com/M00C1FER/common-operating-picture) | Cross-agent lock attestation and collision avoidance |
| Verification | [cli-parity-validator](https://github.com/M00C1FER/cli-parity-validator) | Behavioral parity checking across CLI environments |

Use all three together for fully governed multi-agent pipelines.
See contract-net-router for end-to-end integration examples.
