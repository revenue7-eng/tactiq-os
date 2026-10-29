#!/usr/bin/env python3
"""Tests for the SBOM supplier claim of the TactiQ layers.

What this guards
----------------

The image SBOM names TactiQ AI as supplier of the recipes TactiQ AI authors
and of nothing else. A recipe makes that claim itself, with

    SPDX_PACKAGE_SUPPLIER_ref = "SPDX_SUPPLIER_tactiq"

Whether a recipe is ours cannot be read from its name or its path: these
layers also carry recipes for upstream code (agentgateway, rkbin, U-Boot),
and one of our own recipes (agentgateway-config) has no tactiq- prefix. So
every recipe has to be classified, and this test makes the classification
two-sided:

  - every recipe in these layers carries the line, unless it is an image
    recipe (covered by SPDX_IMAGE_SUPPLIER) or is listed in UPSTREAM below;
  - a recipe listed in UPSTREAM does not carry the line;
  - no .bbappend carries it (an append would claim an upstream recipe);
  - every name in UPSTREAM still has a recipe, so the list cannot go stale;
  - the distro config defines the supplier and makes no per-recipe claims.

A new recipe fails CI until someone decides which side it is on.

Needs: python3.
Run: python3 tests/supplier/test_spdx_supplier.py
"""
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DISTRO = os.path.join(ROOT, "conf", "distro", "tactiq.conf")
CLAIM = re.compile(r'^SPDX_PACKAGE_SUPPLIER_ref\s*=\s*"SPDX_SUPPLIER_tactiq"\s*$', re.M)
ANY_CLAIM = re.compile(r'^SPDX_PACKAGE_SUPPLIER_ref\b', re.M)
IMAGE_DIR = os.path.join("recipes-core", "images") + os.sep

# Recipes in these layers that package code TactiQ AI did not write.
UPSTREAM = {
    "agentgateway": "upstream agentgateway, vendored",
    "rkbin": "Rockchip firmware blobs",
    "u-boot-rockchip": "upstream U-Boot with TactiQ patches and config",
    "u-boot-tactiq-rpi": "upstream U-Boot with TactiQ patches and config",
}


def recipes(suffix):
    out = []
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if not x.startswith(".") and x != "tests"]
        for f in files:
            if f.endswith(suffix):
                out.append(os.path.relpath(os.path.join(d, f), ROOT))
    return sorted(out)


def pn(path):
    base = os.path.basename(path)
    base = re.sub(r"\.bb(append)?$", "", base)
    return base.split("_", 1)[0]


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class SupplierClaim(unittest.TestCase):
    def test_every_recipe_is_classified(self):
        missing, wrong = [], []
        for rel in recipes(".bb"):
            if rel.startswith(IMAGE_DIR):
                continue
            text = read(rel)
            if pn(rel) in UPSTREAM:
                if ANY_CLAIM.search(text):
                    wrong.append(rel)
            elif len(CLAIM.findall(text)) != 1:
                missing.append(rel)
        self.assertEqual(missing, [],
            "recipes without exactly one supplier line: add "
            'SPDX_PACKAGE_SUPPLIER_ref = "SPDX_SUPPLIER_tactiq" if the code is '
            "TactiQ's, or list the recipe in UPSTREAM in this test")
        self.assertEqual(wrong, [], "upstream recipes that claim TactiQ AI as supplier")

    def test_no_append_claims(self):
        bad = [r for r in recipes(".bbappend") if ANY_CLAIM.search(read(r))]
        self.assertEqual(bad, [], "a .bbappend must not set the supplier of the recipe it appends")

    def test_upstream_list_is_current(self):
        present = {pn(r) for r in recipes(".bb")}
        self.assertEqual(sorted(set(UPSTREAM) - present), [],
            "UPSTREAM names a recipe that no longer exists")

    def test_distro_defines_supplier_once(self):
        text = read(os.path.relpath(DISTRO, ROOT))
        self.assertRegex(text, r'(?m)^SPDX_SUPPLIER_tactiq_name\s*=\s*"TactiQ AI"\s*$')
        self.assertRegex(text, r'(?m)^SPDX_IMAGE_SUPPLIER_ref\s*=\s*"SPDX_SUPPLIER_tactiq"\s*$')
        self.assertIsNone(ANY_CLAIM.search(text),
            "per-recipe supplier claims belong in the recipe, not in the distro config")
        self.assertRegex(text, r"(?m)^SPDX3_VAR_DEPS:append\s*=.*\bSPDX_PACKAGE_SUPPLIER_ref\b")


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False, verbosity=2).result.wasSuccessful() else 1)
