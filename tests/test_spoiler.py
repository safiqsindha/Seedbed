import json

from seedbed.access import TIERS
from seedbed.cli import main
from seedbed.spoiler import build_spoiler_log, dumps
from seedbed.toyworld import build_world


def test_spoiler_log_is_reproducible_from_seed():
    world = build_world()
    logic = TIERS["standard"]
    a = build_spoiler_log(world, logic, seed=7)
    b = build_spoiler_log(world, logic, seed=7)
    assert a == b


def test_spoiler_log_contains_required_fields():
    world = build_world()
    logic = TIERS["hard"]
    log = build_spoiler_log(world, logic, seed=3)
    for key in (
        "seed",
        "tier",
        "placement",
        "rolls",
        "solvable",
        "uncheatable",
        "recovery_path",
        "difficulty",
    ):
        assert key in log
    assert log["solvable"] is True
    assert log["uncheatable"] is True


def test_dumps_is_valid_json():
    world = build_world()
    logic = TIERS["easy"]
    text = dumps(world, logic, seed=1)
    parsed = json.loads(text)
    assert parsed["seed"] == 1


def test_cli_runs_and_prints_json(capsys):
    rc = main(["--seed", "5", "--tier", "standard"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["seed"] == 5
    assert parsed["tier"] == "standard"
