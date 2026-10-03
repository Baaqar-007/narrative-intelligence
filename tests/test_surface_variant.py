import networkx as nx

from resolution.pronoun_filter import build_resolution_map
from resolution.surface_variant_merge import build_surface_variant_map, core_tokens


class TestCoreTokens:
    def test_strips_honorifics_and_articles(self):
        assert core_tokens("mrs. holt") == {"holt"}
        assert core_tokens("the count") == frozenset()
        assert core_tokens("count d'angiers") == {"d'angiers"}

    def test_bare_title_has_empty_core(self):
        assert core_tokens("the king") == frozenset()


class TestBuildSurfaceVariantMap:
    def test_does_not_merge_different_people_sharing_only_honorific(self):
        g = nx.MultiDiGraph()
        g.add_edge("harold", "mrs. transome", relation="child_of")
        g.add_edge("felix", "mrs. holt", relation="child_of")

        resolution_map = build_surface_variant_map(g)

        assert "mrs. holt" not in resolution_map
        assert "mrs. transome" not in resolution_map

    def test_does_not_merge_different_title_holders_across_stories(self):
        g = nx.MultiDiGraph()
        g.add_edge("count d'angiers", "lewes", relation="parent_father_of")
        g.add_edge("count isnard", "bertrand", relation="parent_father_of")

        resolution_map = build_surface_variant_map(g)

        assert "count d'angiers" not in resolution_map
        assert "count isnard" not in resolution_map

    def test_bare_title_alone_is_not_merge_candidate(self):
        g = nx.MultiDiGraph()
        g.add_edge("count", "lewes", relation="parent_father_of")
        g.add_edge("count d'angiers", "other_child", relation="parent_father_of")

        resolution_map = build_surface_variant_map(g)

        assert "count" not in resolution_map

    def test_pronoun_generic_nodes_excluded_from_candidacy(self):
        g = nx.MultiDiGraph()
        g.add_edge("her son", "x", relation="parent_father_of")
        g.add_edge("son", "y", relation="parent_father_of")
        pronoun_map = build_resolution_map(g)

        resolution_map = build_surface_variant_map(g, pronoun_generic_map=pronoun_map)

        assert "her son" not in resolution_map
        assert "son" not in resolution_map

    def test_distinguishing_suffix_never_merges(self):
        """Jacob / Jacob Jr. - the suffix exists to mark a DIFFERENT
        person, must never merge regardless of token overlap."""
        g = nx.MultiDiGraph()
        g.add_edge("jacob", "x", relation="parent_father_of")
        g.add_edge("jacob jr.", "y", relation="parent_father_of")

        resolution_map = build_surface_variant_map(g)

        assert "jacob" not in resolution_map

    def test_node_matching_multiple_candidates_is_ambiguous_not_merged(self):
        """"morel" matches both "walter morel" and "arthur morel" - two
        DIFFERENT first names, neither a distinguishing suffix - genuine,
        unresolvable ambiguity (could be either person's bare surname
        reference), correctly declined rather than guessed."""
        g = nx.MultiDiGraph()
        g.add_edge("morel", "x", relation="parent_father_of")
        g.add_edge("walter morel", "y", relation="parent_father_of")
        g.add_edge("arthur morel", "z", relation="parent_father_of")

        resolution_map = build_surface_variant_map(g)

        assert resolution_map["morel"].tier.value == "ambiguous_variant_candidate"
        assert resolution_map["morel"].canonical_form is None