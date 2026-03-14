"""Tests for OSMFetcher — bbox lookup, validation, elevation, and caching."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from osm_fetcher import OSMFetcher


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------

@pytest.fixture
def tmp_cache(tmp_path):
    """Provide a temp directory as the OSM cache."""
    return str(tmp_path / "osm_cache")


@pytest.fixture
def fetcher(tmp_cache):
    return OSMFetcher(cache_dir=tmp_cache)


# ---------------------------------------------------------------
# validate_bbox
# ---------------------------------------------------------------

class TestValidateBbox:
    def test_valid_bbox(self):
        assert OSMFetcher.validate_bbox((43.7, 7.4, 43.75, 7.44)) is None

    def test_wrong_length(self):
        err = OSMFetcher.validate_bbox((1.0, 2.0, 3.0))
        assert err is not None
        assert "4 values" in err

    def test_lat_out_of_range(self):
        err = OSMFetcher.validate_bbox((-91.0, 0.0, 90.0, 1.0))
        assert err is not None
        assert "Latitude" in err

    def test_lon_out_of_range(self):
        err = OSMFetcher.validate_bbox((0.0, -181.0, 1.0, 1.0))
        assert err is not None
        assert "Longitude" in err

    def test_south_greater_than_north(self):
        err = OSMFetcher.validate_bbox((50.0, 0.0, 40.0, 1.0))
        assert err is not None
        assert "south" in err

    def test_antimeridian_warning(self, capsys):
        # west > east is valid but triggers a warning
        err = OSMFetcher.validate_bbox((0.0, 170.0, 1.0, -170.0))
        assert err is None
        assert "antimeridian" in capsys.readouterr().out


# ---------------------------------------------------------------
# fetch_city_bbox
# ---------------------------------------------------------------

class TestFetchCityBbox:
    @patch("osm_fetcher.requests.get")
    def test_success(self, mock_get, fetcher):
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {"boundingbox": ["43.7247", "43.7519", "7.4090", "7.4399"]}
        ]
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        bbox = fetcher.fetch_city_bbox("Monaco")
        assert bbox is not None
        south, west, north, east = bbox
        assert south == pytest.approx(43.7247)
        assert north == pytest.approx(43.7519)

    @patch("osm_fetcher.requests.get")
    def test_empty_result(self, mock_get, fetcher):
        mock_resp = MagicMock()
        mock_resp.json.return_value = []
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        assert fetcher.fetch_city_bbox("Nonexistentville") is None

    @patch("osm_fetcher.requests.get")
    def test_network_error(self, mock_get, fetcher):
        import requests
        mock_get.side_effect = requests.RequestException("timeout")
        assert fetcher.fetch_city_bbox("Monaco") is None


# ---------------------------------------------------------------
# _safe_filename
# ---------------------------------------------------------------

class TestSafeFilename:
    def test_basic(self):
        assert OSMFetcher._safe_filename("Monaco") == "Monaco"

    def test_path_separators(self):
        assert "/" not in OSMFetcher._safe_filename("foo/bar\\baz")

    def test_null_bytes(self):
        assert "\x00" not in OSMFetcher._safe_filename("abc\x00def")

    def test_collapses_underscores(self):
        result = OSMFetcher._safe_filename("a///b")
        assert "__" not in result

    def test_empty_string(self):
        assert OSMFetcher._safe_filename("") == "city"


# ---------------------------------------------------------------
# save_bbox_cache
# ---------------------------------------------------------------

class TestBboxCache:
    def test_save_and_read(self, fetcher, tmp_cache):
        bbox = (43.7, 7.4, 43.75, 7.44)
        fetcher.save_bbox_cache("Monaco", bbox)

        cache_file = os.path.join(tmp_cache, "Monaco_bbox.json")
        assert os.path.exists(cache_file)

        with open(cache_file) as f:
            data = json.load(f)
        assert data["city"] == "Monaco"
        assert data["bbox"] == list(bbox)


# ---------------------------------------------------------------
# collect_coords
# ---------------------------------------------------------------

class TestCollectCoords:
    def test_extracts_from_roads_and_stops(self):
        parsed = {
            "roads": [{"coordinates": [(7.4, 43.7), (7.41, 43.71)]}],
            "railways": [],
            "waterways": [],
            "transit": {
                "stops": [{"coordinates": (7.42, 43.72)}],
                "routes": [],
            },
        }
        coords = OSMFetcher.collect_coords(parsed)
        # Roads: (lon, lat) → extracted as (lat, lon)
        assert (43.7, 7.4) in coords
        assert (43.72, 7.42) in coords

    def test_empty_data(self):
        parsed = {"roads": [], "railways": [], "waterways": []}
        assert OSMFetcher.collect_coords(parsed) == []


# ---------------------------------------------------------------
# fetch_elevation (with mocked HTTP)
# ---------------------------------------------------------------

class TestFetchElevation:
    @patch("osm_fetcher.requests.get")
    def test_fetches_and_caches(self, mock_get, fetcher, tmp_cache):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {"location": {"lat": 43.7, "lng": 7.4}, "elevation": 120.5},
            ]
        }
        mock_get.return_value = mock_resp

        result = fetcher.fetch_elevation([(43.7, 7.4)])
        assert (43.7, 7.4) in result
        assert result[(43.7, 7.4)] == pytest.approx(120.5)

        # Cache file should exist
        cache_path = os.path.join(tmp_cache, "elevation_cache.json")
        assert os.path.exists(cache_path)

    @patch("osm_fetcher.requests.get")
    def test_uses_cache(self, mock_get, fetcher, tmp_cache):
        # Pre-populate cache
        cache_path = os.path.join(tmp_cache, "elevation_cache.json")
        os.makedirs(tmp_cache, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump({"43.7,7.4": 99.9}, f)

        result = fetcher.fetch_elevation([(43.7, 7.4)])
        assert result[(43.7, 7.4)] == pytest.approx(99.9)
        # Should not have made any HTTP calls
        mock_get.assert_not_called()

    def test_empty_coords(self, fetcher):
        assert fetcher.fetch_elevation([]) == {}
