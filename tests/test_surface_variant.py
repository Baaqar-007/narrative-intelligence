import networkx as nx
import pytest

from resolution.pronoun_filter import ResolutionTier, build_resolution_map
from resolution.surface_variant_merge import build_surface_variant_map, core_tokens


class TestCoreTokens:
    def test_strips_honorifics_and_articles(self):
        assert core_tokens("mrs. holt") == {"holt"}
        assert core_tokens("the count") == frozenset()  # "the" and "count" both strip - empty core
        assert core_tokens("count d'angiers") == {"d'angiers"}

    def test_bare_title_has_empty_core(self):
        assert core_tokens("the king") == frozenset()


class TestBuildSurfaceVariantMap:
    def test_does_not_merge_different_people_sharing_only_honorific(self):
        """Regression test for the catch that motivated this module's
        design: Mrs. Holt and Mrs. Transome are different characters,
        sharing only the honorific 'mrs.' - must NOT be clustered."""
        g = nx.MultiDiGraph()
        g.add_edge("harold", "mrs. transome", relation="child_of")
        g.add_edge("felix", "mrs. holt", relation="child_of")

        resolution_map = build_surface_variant_map(g)

        assert "mrs. holt" not in resolution_map
        assert "mrs. transome" not in resolution_map

    def test_merges_real_surface_variants(self):
        g = nx.MultiDiGraph()
        for n in ("morel", "mr. morel", "walter morel"):
            g.add_edge(n, "paul", relation="parent_father_of")

        resolution_map = build_surface_variant_map(g)

        assert resolution_map["morel"].canonical_form == "walter morel"
        assert resolution_map["mr. morel"].canonical_form == "walter morel"
        assert "walter morel" not in resolution_map  # the canonical itself isn't flagged

    def test_bare_title_alone_is_not_merge_candidate(self):
        g = nx.MultiDiGraph()
        g.add_edge("count", "lewes", relation="parent_father_of")
        g.add_edge("count d'angiers", "other_child", relation="parent_father_of")

        resolution_map = build_surface_variant_map(g)

        assert "count" not in resolution_map  # empty core tokens, excluded by design

    def test_does_not_merge_different_title_holders_across_stories(self):
        """The Decameron corpus bundles ~100 novellas under one
        book_id - two different counts in different stories must not
        be merged just because they share the title "count"."""
        g = nx.MultiDiGraph()
        g.add_edge("count d'angiers", "lewes", relation="parent_father_of")
        g.add_edge("count isnard", "bertrand", relation="parent_father_of")

        resolution_map = build_surface_variant_map(g)

        assert "count d'angiers" not in resolution_map
        assert "count isnard" not in resolution_map

    def test_pronoun_generic_nodes_excluded_from_candidacy(self):
        g = nx.MultiDiGraph()
        g.add_edge("her son", "x", relation="parent_father_of")
        g.add_edge("son", "y", relation="parent_father_of")
        pronoun_map = build_resolution_map(g)

        resolution_map = build_surface_variant_map(g, pronoun_generic_map=pronoun_map)

        assert "her son" not in resolution_map
        assert "son" not in resolution_map