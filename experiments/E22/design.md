# E22

3 synthetic failure scenarios (logic / type / import error) injected via fake run_tests. Branch A runs full M3.6 meta-loop. Branch B is no-op baseline. Both should detect the gap; Branch A should attempt fix + roll back when test fails (since synthetic cannot be auto-fixed).
## еп╬щ
{
  "scenarios": [
    "logic_error",
    "type_error",
    "import_error"
  ],
  "branch_a_detected": 3,
  "branch_b_detected": 3,
  "consistency": true,
  "total_scenarios": 3,
  "branch_a_rolled_back_count": 3
}
