import os
import subprocess
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.table import Table
from desiutil.log import get_logger
from fiberassign.fba_tertiary_io import get_toofn

from desisurveyops.fba_tertiary_design_io import (
    assert_files,
    create_tiles_table,
    creates_priority_table,
    finalize_target_table,
    get_fn,
    merge_target_catalogs,
    read_yaml,
    TertiaryTileDesignBase,
)

logger = get_logger()


class TertiaryTileDesign(TertiaryTileDesignBase):
    """Tertiary tile design for program 0062.

    Tiles are built from tile_ra, tile_dec, and obsconds in the yaml.
    Priorities come from the yaml.
    The yaml samples share one combined catalog. create_targets splits that
    catalog on its priority column, points each sample at its own file, then
    merges those files.
    """

    def __init__(self, yamlfp: str):
        self.yamlfp = yamlfp
        self.settings = read_yaml(yamlfp)["settings"]
        self.samples = read_yaml(yamlfp)["samples"]
        self.rootdir = Path(self.settings["targdir"])

    def create_tiles(self, outfp: str):
        ras = np.array(self.settings["tile_ra"], dtype=float)
        decs = np.array(self.settings["tile_dec"], dtype=float)
        ntile = int(self.settings["ntile"])
        if len(ras) != ntile or len(decs) != ntile:
            raise ValueError(
                "tile_ra and tile_dec must each have ntile={} entries, found {} and {}".format(
                    ntile, len(ras), len(decs)
                )
            )
        tileids = np.arange(
            self.settings["tileid_start"],
            self.settings["tileid_start"] + ntile,
            dtype=int,
        )
        obsconds = self.settings["obsconds"]
        logger.info(
            "writing %d tiles at %s with obsconds %s and goaltime %s s",
            ntile,
            list(zip(ras.tolist(), decs.tolist())),
            obsconds,
            self.settings["goaltime"],
        )
        tab = create_tiles_table(tileids, ras, decs, obsconds)
        tab.write(outfp, overwrite=True)

    def create_priorities(self, outfp: str):
        tab = creates_priority_table(self.yamlfp)
        tab.pprint_all()
        for sample in np.unique(tab["TERTIARY_TARGET"]):
            sel = tab["TERTIARY_TARGET"] == sample
            logger.info(
                "priorities for {}: {}".format(sample, tab["PRIORITY"][sel].tolist())
            )
        tab.write(outfp, overwrite=True)

    def _split_combined_catalog(self):
        """Write one catalog per priority and point self.samples at those files."""
        fns = {cfg["FN"] for cfg in self.samples.values()}
        if len(fns) != 1:
            raise ValueError(
                "0062 expects every sample to start from the same combined catalog, found {}".format(
                    sorted(fns)
                )
            )
        src_name = fns.pop()
        src = self.rootdir / "inputcats" / src_name
        logger.info("splitting %s on the priority column", src)
        catalog = Table.read(src)
        if "priority" not in catalog.colnames:
            raise ValueError("{} has no priority column".format(src))

        priority = np.char.strip(catalog["priority"].astype(str))
        # Sample key very_low corresponds to the catalog value "very low".
        labels = {name: name.replace("_", " ") for name in self.samples}
        catalog_labels = set(np.unique(priority))
        expected = set(labels.values())
        if catalog_labels != expected:
            raise ValueError(
                "priority values {} do not match yaml samples {}".format(
                    sorted(catalog_labels), sorted(expected)
                )
            )

        for ext in (".fits.gz", ".fits"):
            if src_name.endswith(ext):
                stem, suffix = src_name[: -len(ext)], ext
                break
        else:
            raise ValueError("combined catalog name must end in .fits or .fits.gz")

        for name, label in labels.items():
            subsample = catalog[priority == label]
            out_name = "{}-{}{}".format(stem, name, suffix)
            out = self.rootdir / "inputcats" / out_name
            logger.info("writing %d %s targets to %s", len(subsample), label, out)
            subsample.write(out, overwrite=True)
            self.samples[name]["FN"] = out_name

    def create_targets(self, outfp: str):
        self._split_combined_catalog()
        targets = merge_target_catalogs(
            self.rootdir / "inputcats",
            self.samples,
            remove_duplicates=False,
        )
        targets = finalize_target_table(targets, self.yamlfp)
        targets.write(outfp, overwrite=True)
