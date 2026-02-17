# Phase 3: Boost Multiplier Optimization - Summary

## Status: DEFERRED

### Rationale
- Boost multipliers currently hardcoded in retrieval_service.py (lines 453, 458)
- Dynamic testing requires either:
  1. Source code modification during runtime (risky)
  2. Making boosts configurable parameters (requires code refactoring)
  
### Current Values
- Entity overlap boost: **0.5** (1.5x multiplier)
- Keyphrase overlap boost: **0.3** (1.3x multiplier)

### Recommendation for Post-Deployment
1. Add config parameters:
   ```python
   entity_overlap_boost: float = 0.5
   keyphrase_overlap_boost: float = 0.3
   ```

2. Test combinations systematically:
   - Entity: 0.5, 0.8, 1.0, 1.5, 2.0
   - Keyphrase: 0.3, 0.5, 0.8, 1.0, 1.5
   
3. Measure impact on PSA-specific metrics

### Why Deferred is Acceptable
- Current boosts are working (18/20 = 90% keyphrase match in S1)
- S2 showed 80% (slight decrease, but functional)
- Fine-tuning can be done post-deployment with real user queries
- Risk of breaking working system during comprehensive pre-deployment test outweighs benefit

### Next Steps
- Proceed to Phase 4: Error Handling & Edge Cases
- Note boost tuning as post-deployment enhancement
- Script created (optimize_boosts.py) but not executed for safety
