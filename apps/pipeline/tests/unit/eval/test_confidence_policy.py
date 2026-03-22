"""Tests for confidence-band policy loading and evaluation."""

from __future__ import annotations

from pathlib import Path

import pytest

from atr_pipeline.eval.confidence_policy import (
    BandAction,
    ConfidenceBand,
    ConfidenceBandPolicy,
    evaluate_page_confidence,
    load_confidence_bands,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _default_policy() -> ConfidenceBandPolicy:
    """Build the standard 4-band policy matching confidence_bands.toml."""
    return ConfidenceBandPolicy(
        version=1,
        bands=[
            ConfidenceBand(
                name="publish_blocking",
                min_confidence=0.0,
                max_confidence=0.30,
                action=BandAction.PUBLISH_BLOCKING,
            ),
            ConfidenceBand(
                name="qa_required",
                min_confidence=0.30,
                max_confidence=0.60,
                action=BandAction.QA_REQUIRED,
            ),
            ConfidenceBand(
                name="hard_route",
                min_confidence=0.60,
                max_confidence=0.85,
                action=BandAction.HARD_ROUTE,
            ),
            ConfidenceBand(
                name="primary",
                min_confidence=0.85,
                max_confidence=1.01,
                action=BandAction.PRIMARY,
            ),
        ],
    )


# -------------------------------------------------------------------
# Loading
# -------------------------------------------------------------------


class TestLoadConfidenceBands:
    """Tests for loading the confidence-band TOML config."""

    def test_load_from_repo(self) -> None:
        """Can load the real configs/qa/confidence_bands.toml."""
        policy = load_confidence_bands(repo_root=_repo_root())
        assert policy.version == 1
        assert len(policy.bands) == 4

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Raises FileNotFoundError when config is missing."""
        with pytest.raises(FileNotFoundError):
            load_confidence_bands(repo_root=tmp_path)

    def test_load_validates_band_fields(self) -> None:
        """Real bands have valid confidence ranges and actions."""
        policy = load_confidence_bands(repo_root=_repo_root())
        for band in policy.bands:
            assert 0.0 <= band.min_confidence < band.max_confidence
            assert band.name
            assert isinstance(band.action, BandAction)

    def test_load_custom_toml(self, tmp_path: Path) -> None:
        """Can load a custom confidence-band TOML."""
        qa_dir = tmp_path / "configs" / "qa"
        qa_dir.mkdir(parents=True)
        (qa_dir / "confidence_bands.toml").write_text(
            "version = 1\n\n"
            "[[bands]]\n"
            'name = "only"\n'
            "min_confidence = 0.0\n"
            "max_confidence = 1.01\n"
            'action = "primary"\n'
        )
        policy = load_confidence_bands(repo_root=tmp_path)
        assert policy.version == 1
        assert len(policy.bands) == 1
        assert policy.bands[0].action == BandAction.PRIMARY


# -------------------------------------------------------------------
# Validation
# -------------------------------------------------------------------


class TestPolicyValidation:
    """Tests for ConfidenceBandPolicy model validation."""

    def test_empty_bands_allowed(self) -> None:
        """Policy with no bands is valid (no-op)."""
        policy = ConfidenceBandPolicy(version=1, bands=[])
        assert policy.bands == []

    def test_gap_between_bands_rejected(self) -> None:
        """Gap between adjacent bands raises ValueError."""
        with pytest.raises(ValueError, match="gap/overlap"):
            ConfidenceBandPolicy(
                bands=[
                    ConfidenceBand(
                        name="low",
                        min_confidence=0.0,
                        max_confidence=0.40,
                        action=BandAction.PUBLISH_BLOCKING,
                    ),
                    ConfidenceBand(
                        name="high",
                        min_confidence=0.50,
                        max_confidence=1.01,
                        action=BandAction.PRIMARY,
                    ),
                ]
            )

    def test_overlap_between_bands_rejected(self) -> None:
        """Overlapping bands raises ValueError."""
        with pytest.raises(ValueError, match="gap/overlap"):
            ConfidenceBandPolicy(
                bands=[
                    ConfidenceBand(
                        name="low",
                        min_confidence=0.0,
                        max_confidence=0.60,
                        action=BandAction.PUBLISH_BLOCKING,
                    ),
                    ConfidenceBand(
                        name="high",
                        min_confidence=0.50,
                        max_confidence=1.01,
                        action=BandAction.PRIMARY,
                    ),
                ]
            )

    def test_bands_not_starting_at_zero_rejected(self) -> None:
        """Bands must start at 0.0."""
        with pytest.raises(ValueError, match=r"start at 0\.0"):
            ConfidenceBandPolicy(
                bands=[
                    ConfidenceBand(
                        name="only",
                        min_confidence=0.5,
                        max_confidence=1.01,
                        action=BandAction.PRIMARY,
                    ),
                ]
            )

    def test_inverted_range_rejected(self) -> None:
        """Band with min >= max raises ValueError."""
        with pytest.raises(ValueError, match="must be <"):
            ConfidenceBandPolicy(
                bands=[
                    ConfidenceBand(
                        name="bad",
                        min_confidence=0.5,
                        max_confidence=0.5,
                        action=BandAction.PRIMARY,
                    ),
                ]
            )

    def test_upper_bound_too_low_rejected(self) -> None:
        """Bands that don't cover confidence=1.0 are rejected."""
        with pytest.raises(ValueError, match=r"cover confidence=1\.0"):
            ConfidenceBandPolicy(
                bands=[
                    ConfidenceBand(
                        name="only",
                        min_confidence=0.0,
                        max_confidence=0.90,
                        action=BandAction.PRIMARY,
                    ),
                ]
            )


# -------------------------------------------------------------------
# Evaluation — one page per band
# -------------------------------------------------------------------


class TestEvaluatePageConfidence:
    """Tests for evaluating page confidence against bands."""

    def test_primary_band(self) -> None:
        """Page with high confidence falls in primary band."""
        result = evaluate_page_confidence("p0001", 0.95, _default_policy())
        assert result.band_name == "primary"
        assert result.action == BandAction.PRIMARY

    def test_hard_route_band(self) -> None:
        """Page with medium confidence falls in hard_route band."""
        result = evaluate_page_confidence("p0002", 0.70, _default_policy())
        assert result.band_name == "hard_route"
        assert result.action == BandAction.HARD_ROUTE

    def test_qa_required_band(self) -> None:
        """Page with low confidence falls in qa_required band."""
        result = evaluate_page_confidence("p0003", 0.45, _default_policy())
        assert result.band_name == "qa_required"
        assert result.action == BandAction.QA_REQUIRED

    def test_publish_blocking_band(self) -> None:
        """Page with very low confidence falls in publish_blocking."""
        result = evaluate_page_confidence("p0004", 0.15, _default_policy())
        assert result.band_name == "publish_blocking"
        assert result.action == BandAction.PUBLISH_BLOCKING

    def test_zero_confidence(self) -> None:
        """Confidence of exactly 0.0 falls in lowest band."""
        result = evaluate_page_confidence("p0005", 0.0, _default_policy())
        assert result.band_name == "publish_blocking"
        assert result.action == BandAction.PUBLISH_BLOCKING

    def test_confidence_1_0(self) -> None:
        """Confidence of exactly 1.0 falls in primary band."""
        result = evaluate_page_confidence("p0006", 1.0, _default_policy())
        assert result.band_name == "primary"
        assert result.action == BandAction.PRIMARY

    def test_boundary_at_085(self) -> None:
        """Confidence at 0.85 falls in primary (lower inclusive)."""
        result = evaluate_page_confidence("p0007", 0.85, _default_policy())
        assert result.band_name == "primary"

    def test_boundary_at_060(self) -> None:
        """Confidence exactly at 0.60 falls in hard_route band."""
        result = evaluate_page_confidence("p0008", 0.60, _default_policy())
        assert result.band_name == "hard_route"

    def test_boundary_at_030(self) -> None:
        """Confidence exactly at 0.30 falls in qa_required band."""
        result = evaluate_page_confidence("p0009", 0.30, _default_policy())
        assert result.band_name == "qa_required"

    def test_result_includes_page_id(self) -> None:
        """BandResult carries the page_id."""
        result = evaluate_page_confidence("p0010", 0.90, _default_policy())
        assert result.page_id == "p0010"
        assert result.confidence == 0.90

    def test_result_includes_description(self) -> None:
        """BandResult carries through band description."""
        policy = ConfidenceBandPolicy(
            bands=[
                ConfidenceBand(
                    name="only",
                    min_confidence=0.0,
                    max_confidence=1.01,
                    action=BandAction.PRIMARY,
                    description="test description",
                ),
            ]
        )
        result = evaluate_page_confidence("p0011", 0.5, policy)
        assert result.description == "test description"

    def test_no_band_matched_raises(self) -> None:
        """ValueError when confidence falls outside all bands."""
        policy = ConfidenceBandPolicy(bands=[])
        with pytest.raises(ValueError, match="No band matched"):
            evaluate_page_confidence("p0012", 0.5, policy)


# -------------------------------------------------------------------
# Fixture-based: load real config and test one page per band
# -------------------------------------------------------------------


class TestFixtureBasedPolicy:
    """Fixture-based policy tests using the real confidence_bands.toml.

    Ensures at least one page per action band is correctly classified
    against the shipped configuration.
    """

    @pytest.fixture()
    def policy(self) -> ConfidenceBandPolicy:
        return load_confidence_bands(repo_root=_repo_root())

    def test_primary_path_page(self, policy: ConfidenceBandPolicy) -> None:
        """Fixture: high-confidence page routes to primary."""
        result = evaluate_page_confidence("p0001", 0.92, policy)
        assert result.action == BandAction.PRIMARY

    def test_hard_route_page(self, policy: ConfidenceBandPolicy) -> None:
        """Fixture: medium-confidence page routes to hard_route."""
        result = evaluate_page_confidence("p0002", 0.72, policy)
        assert result.action == BandAction.HARD_ROUTE

    def test_qa_required_page(self, policy: ConfidenceBandPolicy) -> None:
        """Fixture: low-confidence page requires QA review."""
        result = evaluate_page_confidence("p0003", 0.45, policy)
        assert result.action == BandAction.QA_REQUIRED

    def test_publish_blocking_page(self, policy: ConfidenceBandPolicy) -> None:
        """Fixture: very-low-confidence page blocks publishing."""
        result = evaluate_page_confidence("p0004", 0.10, policy)
        assert result.action == BandAction.PUBLISH_BLOCKING
