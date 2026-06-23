"""Tests for main.py helpers (bbox sizing)."""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import resize_bbox, MAP_SIZE_FACTORS
from cs2_converter import CoordinateTransformer

# A small admin-boundary-sized bbox around Ghent.
GENT_BBOX = (50.9795, 3.5798, 51.1889, 3.8493)


def _size_m(bbox):
    south, west, north, east = bbox
    clat = (south + north) / 2.0
    width_m = (east - west) * 111_320.0 * math.cos(math.radians(clat))
    height_m = (north - south) * 111_320.0
    return width_m, height_m


class TestResizeBbox:
    def test_city_keeps_bbox(self):
        assert resize_bbox(GENT_BBOX, "city") == GENT_BBOX

    def test_full_fills_cs2_map(self):
        w, h = _size_m(resize_bbox(GENT_BBOX, "full"))
        target = CoordinateTransformer.CS2_MAP_SIZE
        assert w == pytest.approx(target, rel=0.01)
        assert h == pytest.approx(target, rel=0.01)

    def test_full_is_centred_on_city(self):
        s0, w0, n0, e0 = GENT_BBOX
        s1, w1, n1, e1 = resize_bbox(GENT_BBOX, "full")
        assert (s1 + n1) / 2 == pytest.approx((s0 + n0) / 2)
        assert (w1 + e1) / 2 == pytest.approx((w0 + e0) / 2)

    def test_half_is_half_of_full(self):
        w_full, _ = _size_m(resize_bbox(GENT_BBOX, "full"))
        w_half, _ = _size_m(resize_bbox(GENT_BBOX, "half"))
        assert w_half == pytest.approx(w_full / 2, rel=0.01)

    def test_factors(self):
        assert MAP_SIZE_FACTORS == {"full": 1.0, "half": 0.5, "quarter": 0.25}
