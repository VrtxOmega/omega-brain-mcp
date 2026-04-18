import json
from veritas_build_gates import run_pipeline

claim = {
    "project": "omega-brain-mcp",
    "version": "1.0.1",
    "commit": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
    "primitives": [
        {
            "name": "CAPEX_USD",
            "domain": {"low": 0, "high": 200000, "inclusive_low": True, "inclusive_high": True},
            "units": "USD"
        }
    ],
    "boundaries": [
        {
            "name": "budget",
            "constraint": {"left": "CAPEX_USD", "op": "<=", "right": 100000.0}
        }
    ],
    "evidence": [
        {
            "id": "e1",
            "variable": "CAPEX_USD",
            "value": {"x": 97000, "units": "USD", "uncertainty": 2000, "kind": "point"},
            "timestamp": "2026-04-12T10:00:00Z",
            "method": {"protocol": "invoice", "parameters": {}, "repeatable": True},
            "provenance": {"source_id": "S1", "acquisition": "purchase", "tier": "B"},
            "dependencies": []
        },
        {
            "id": "e2",
            "variable": "CAPEX_USD",
            "value": {"x": 98000, "units": "USD", "uncertainty": 1500, "kind": "point"},
            "timestamp": "2026-04-12T10:05:00Z",
            "method": {"protocol": "quote", "parameters": {}, "repeatable": True},
            "provenance": {"source_id": "S2", "acquisition": "purchase", "tier": "B"},
            "dependencies": []
        }
    ]
}

result = run_pipeline(claim)
print(json.dumps(result, indent=2))
