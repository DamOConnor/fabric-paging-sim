"""Tests for the Strategy registry."""
from pagination import STRATEGIES, STRATEGY_BY_NAME, Strategy


class TestRegistry:
    def test_all_strategies_registered(self):
        names = {s.name for s in STRATEGIES}
        expected = {
            "nextlink", "header", "offset", "pagenumber",
            "cursor", "bookmark", "range", "pagemeta",
        }
        assert names == expected

    def test_names_are_unique(self):
        names = [s.name for s in STRATEGIES]
        assert len(names) == len(set(names))

    def test_routes_are_unique(self):
        routes = [s.route for s in STRATEGIES]
        assert len(routes) == len(set(routes))

    def test_by_name_index_matches_list(self):
        for s in STRATEGIES:
            assert STRATEGY_BY_NAME[s.name] is s

    def test_every_strategy_has_description_and_params(self):
        for s in STRATEGIES:
            assert s.description, f"{s.name} has no description"
            assert s.params, f"{s.name} has no params"
            assert s.pagination_rule, f"{s.name} has no pagination_rule"

    def test_only_header_returns_headers(self):
        header_strategies = [s.name for s in STRATEGIES if s.returns_headers]
        assert header_strategies == ["header"]


class TestStrategyInvoke:
    def test_invoke_normalises_two_tuple(self, make_req):
        strategy = STRATEGY_BY_NAME["nextlink"]
        body, delay, headers = strategy.invoke(
            make_req({"totalRecords": "10", "pageSize": "5"}), "http://x"
        )
        assert isinstance(body, dict)
        assert isinstance(delay, int)
        assert headers == {}

    def test_invoke_normalises_three_tuple(self, make_req):
        strategy = STRATEGY_BY_NAME["header"]
        body, delay, headers = strategy.invoke(
            make_req({"totalRecords": "30", "pageSize": "10", "page": "2"}),
            "http://x",
        )
        assert isinstance(body, dict)
        assert isinstance(delay, int)
        assert "Link" in headers
