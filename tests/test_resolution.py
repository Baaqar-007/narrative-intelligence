# tests/test_resolution.py
"""Tests for resolution/pronoun_filter.py - Week 8's mechanical
pronoun/generic pre-filter (Stage 0, ahead of Week 4's original
Stage A, per the day-4/5 re-sequencing decision).

Per the project's standing rule, passing these tests is NOT
sufficient to call this stage complete - a real-usage check (rerun
Module A / the yardstick with this filter wired into composition, and
confirm the 19.4% functional-step fragmentation number actually
drops) is still required.
"""

import networkx as nx
import pytest

from resolution.pronoun_filter import (
    ResolutionTier,
    build_resolution_map,
    is_excluded_from_composition,
    is_pronoun_generic,
)


class TestIsPronounGeneric:
    @pytest.mark.parametrize("entity", [
        "her", "his", "you", "she", "he", "they", "it",
        "mother", "father", "son", "daughter",
        "her son", "his mother", "your daughter", "my son",
        "her own son",
        "HER SON",
        "  her son  ",
    ])
    def test_flags_known_pronoun_generic_forms(self, entity):
        assert is_pronoun_generic(entity) is True

    @pytest.mark.parametrize("entity", [
        "harold", "harold transome", "mr. harold transome",
        "jermyn", "mrs. transome", "taug", "tarzan",
        "the king of camelot",
    ])
    def test_does_not_flag_real_names(self, entity):
        assert is_pronoun_generic(entity) is False

    def test_empty_string_does_not_crash(self):
        assert is_pronoun_generic("") is False

    def test_known_false_positive_risk_documented_not_fixed(self):
        """A real character literally named "Son" as a proper noun
        would be wrongly flagged - not observed in this corpus, not
        fixed pre-emptively (see module docstring). This documents
        current behavior rather than asserting it's ideal - a real
        hit on a genuine character name is the trigger to revisit."""
        assert is_pronoun_generic("Son") is True


def _map_from_pairs(pairs):
    g = nx.MultiDiGraph()
    for u, v in pairs:
        g.add_edge(u, v, relation="parent_father_of")
    return build_resolution_map(g)


class TestBuildResolutionMap:
    def test_flags_only_pronoun_generic_nodes(self):
        g = nx.MultiDiGraph()
        g.add_edge("mrs. transome", "harold", relation="parent_mother_of")
        g.add_edge("her son", "jermyn", relation="parent_father_of")
        g.add_edge("harold", "taug", relation="enemy_of")

        resolution_map = build_resolution_map(g)

        assert set(resolution_map) == {"her son"}
        assert resolution_map["her son"].tier == ResolutionTier.EXCLUDED_PRONOUN_GENERIC

    def test_does_not_mutate_graph(self):
        g = nx.MultiDiGraph()
        g.add_edge("her son", "jermyn", relation="parent_father_of")
        nodes_before, edges_before = set(g.nodes), list(g.edges(data=True))

        build_resolution_map(g)

        assert set(g.nodes) == nodes_before
        assert list(g.edges(data=True)) == edges_before

    def test_empty_graph_returns_empty_map(self):
        assert build_resolution_map(nx.MultiDiGraph()) == {}

    def test_real_harold_cluster_from_diagnostics(self):
        """Regression check against the exact 10-string cluster found
        for 'Mrs. Transome's son' during the day-4 frontier audit -
        confirms this module catches the pronoun/generic majority of
        it, and correctly leaves the rest (surface variants, and the
        unrelated 'esther') to other stages/bugs."""
        cluster = {
            "harold", "mr. harold transome", "harold transome", "mr. harold",
            "son", "her son", "my son", "her own son", "mother", "esther",
        }
        resolution_map = _map_from_pairs(("mrs. transome", n) for n in cluster)
        flagged = set(resolution_map)

        assert flagged == {"son", "her son", "my son", "her own son", "mother"}
        assert "harold" not in flagged            # Stage A's job, not this module's
        assert "mr. harold transome" not in flagged
        assert "esther" not in flagged             # Bug C territory, not this module's


class TestIsExcludedFromComposition:
    def test_excluded_entity_returns_true(self):
        resolution_map = _map_from_pairs([("her son", "x")])
        assert is_excluded_from_composition("her son", resolution_map) is True

    def test_non_excluded_entity_returns_false(self):
        resolution_map = _map_from_pairs([("her son", "x")])
        assert is_excluded_from_composition("harold", resolution_map) is False

class TestPluralAndMissingForms:
    @pytest.mark.parametrize("entity", [
        "daughter", "daughters", "her daughters", "sonnes", "children",
        "brothers", "sisters",
    ])
    def test_flags_plural_and_previously_missing_forms(self, entity):
        assert is_pronoun_generic(entity) is True

    def test_does_not_flag_real_name_ending_in_s(self):
        """Known, accepted false-positive risk (see module docstring)
        - a real character literally named with a plural-looking form
        of a listed word would be wrongly flagged. Not observed in
        this corpus."""
        assert is_pronoun_generic("perkins") is False  # "perkin" not in set - correctly NOT flagged