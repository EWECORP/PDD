from pdd_backend.scope_rules import load_scope_exclusion_policy


def test_internal_supplies_are_excluded() -> None:
    policy = load_scope_exclusion_policy()
    categories = {
        (rule["c_rubro"], rule["c_subrubro_1"])
        for rule in policy["rules"]
    }
    assert policy["version"] == 1
    assert categories == {(13, 3818), (13, 3838)}
    assert all("rubro_name" not in rule for rule in policy["rules"])
    assert all("subrubro_1_name" not in rule for rule in policy["rules"])
