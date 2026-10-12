import yaml
from pathlib import Path

def test_phase0_scaffold():
    root = Path(__file__).resolve().parent.parent
    assert (root / "legacy" / "vn_donchian_wf.py").exists(), "Legacy file missing"
    assert (root / "configs" / "base.yaml").exists(), "base.yaml missing"
    assert (root / "configs" / "grid_brk.yaml").exists(), "grid_brk.yaml missing"
    assert (root / "configs" / "grid_pb.yaml").exists(), "grid_pb.yaml missing"
    assert (root / "docs" / "MARKET_RULES.md").exists(), "MARKET_RULES.md missing"
    assert (root / "docs" / "OPEN_QUESTIONS.md").exists(), "OPEN_QUESTIONS.md missing"
    assert (root / "docs" / "DECISIONS.md").exists(), "DECISIONS.md missing"

def test_base_config_valid():
    root = Path(__file__).resolve().parent.parent
    with open(root / "configs" / "base.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    assert cfg["market"]["exchange"] == "HOSE"
    assert cfg["market"]["price_limit"] == 0.07
    assert cfg["market"]["lot"] == 100
    assert cfg["market"]["min_hold_sessions"] == 3
    assert cfg["portfolio"]["risk_pct"] == 0.01
    assert cfg["portfolio"]["max_positions"] == 10
    assert cfg["research"]["holdout_start"] == "2025-01-01"
