import networkx as nx

from resolution.resolve import build_full_resolution_map, is_nameable, summarize
from resolution.pronoun_filter import ResolutionTier

class TestIsNameable:
    def test_rejects_pronoun_generic(self):
        assert is_nameable("her son") is False
        assert is_nameable("mother") is False

    def test_rejects_leading_function_word(self):
        assert is_nameable("the count") is False

    def test_rejects_social_role_generic(self):
        assert is_nameable("gentlewoman") is False

    def test_accepts_real_names(self):
        assert is_nameable("harold transome") is True
        assert is_nameable("taug") is True

    def test_rejects_overlong_phrase(self):
        assert is_nameable("my friend felix holt and his wife") is False


class TestBuildFullResolutionMap:
    def test_stage_ordering_pronoun_excluded_from_surface_candidacy(self):
        g = nx.MultiDiGraph()
        g.add_edge("her son", "jermyn", relation="parent_father_of")
        g.add_edge("son", "jermyn", relation="parent_father_of")

        resolution_map = build_full_resolution_map(g)

        assert resolution_map["her son"].tier == ResolutionTier.EXCLUDED_PRONOUN_GENERIC
        assert resolution_map["son"].tier == ResolutionTier.EXCLUDED_PRONOUN_GENERIC

    def test_merged_map_has_no_key_collisions(self):
        g = nx.MultiDiGraph()
        g.add_edge("her son", "jermyn", relation="parent_father_of")
        g.add_edge("mr. morel", "paul", relation="parent_father_of")
        g.add_edge("walter morel", "paul", relation="parent_father_of")

        resolution_map = build_full_resolution_map(g)

        assert resolution_map["her son"].tier == ResolutionTier.EXCLUDED_PRONOUN_GENERIC
        assert resolution_map["mr. morel"].tier == ResolutionTier.SURFACE_VARIANT
        assert resolution_map["mr. morel"].canonical_form == "walter morel"

    def test_known_risk_pair_stays_separate_through_full_pipeline(self):
        g = nx.MultiDiGraph()
        g.add_edge("harold", "mrs. transome", relation="child_of")
        g.add_edge("felix", "mrs. holt", relation="child_of")
        g.add_edge("mr. harold transome", "x", relation="enemy_of")

        resolution_map = build_full_resolution_map(g)

        holt = resolution_map.get("mrs. holt")
        transome = resolution_map.get("mrs. transome")
        holt_canon = holt.canonical_form if holt else "mrs. holt"
        transome_canon = transome.canonical_form if transome else "mrs. transome"
        assert holt_canon != transome_canon


class TestSummarize:
    def test_counts_add_up_to_total_minus_unresolved(self):
        g = nx.MultiDiGraph()
        g.add_edge("her son", "jermyn", relation="parent_father_of")
        g.add_edge("mr. morel", "paul", relation="parent_father_of")
        g.add_edge("walter morel", "paul", relation="parent_father_of")
        g.add_edge("taug", "tarzan", relation="companion_of")

        resolution_map = build_full_resolution_map(g)
        summary = summarize(g, resolution_map)

        assert summary.total_nodes == g.number_of_nodes()
        resolved = summary.pronoun_generic + summary.surface_variant + summary.ambiguous_variant_candidate
        assert resolved + summary.unresolved == summary.total_nodes