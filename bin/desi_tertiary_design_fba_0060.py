from pathlib import Path
import shutil
import numpy as np
from astropy.table import Table
from desisurveyops.fba_tertiary_design_io import (
    finalize_target_table,
    read_yaml,
    TertiaryTileDesignBase,
)
from desiutil.log import get_logger

logger = get_logger()


class TertiaryTileDesign(TertiaryTileDesignBase):
    """Tertiary tile design for the M31 disk (prognum 0060).

    Tiles are copied from the input catalog with TILEID rewritten to
    tileid_start .. tileid_start + ntile - 1. Priorities are copied
    unchanged. Targets are rebuilt with new TARGETID and SUBPRIORITY values.
    """

    def __init__(self, yamlfp: str):
        self.yamlfp = yamlfp
        self.settings = read_yaml(yamlfp)["settings"]
        self.samples = read_yaml(yamlfp)["samples"]
        self.rootdir = Path(self.settings["targdir"])

    def create_tiles(self, outfp: str):
        srcs = sorted(self.rootdir.glob("inputcats/tertiary-tiles-*.ecsv"))
        if len(srcs) != 1:
            raise ValueError(
                "0060 expects one input tile catalog, found {}".format(
                    [str(src) for src in srcs]
                )
            )
        src = srcs[0]
        tiles = Table.read(src)
        ntile = int(self.settings["ntile"])
        tileid_start = int(self.settings["tileid_start"])
        if len(tiles) != ntile:
            raise ValueError(
                "input tiles have {} rows, yaml ntile is {}".format(len(tiles), ntile)
            )
        tiles.sort("TILEID")
        new_ids = np.arange(tileid_start, tileid_start + ntile, dtype=int)
        assert len(tiles) == len(new_ids), "Number of tiles and new IDs do not match"
        logger.info(
            "rewriting TILEID %s -> %s from %s",
            tiles["TILEID"].tolist(),
            new_ids.tolist(),
            src,
        )
        tiles["TILEID"] = new_ids
        tiles.write(outfp, format="ascii.ecsv", overwrite=True)
        logger.info("wrote %s", outfp)

    def create_priorities(self, outfp: str):
        logger.info("Using the provided priorities file")
        srcs = sorted((self.rootdir / "inputcats").glob("tertiary-priorities-*.ecsv"))
        if len(srcs) != 1:
            raise ValueError(
                "0060 expects one input priorities catalog, found {}".format(
                    [str(src) for src in srcs]
                )
            )
        src = srcs[0]
        shutil.copy(src, outfp)

    def create_targets(self, outfp: str):
        fns = {cfg["FN"] for cfg in self.samples.values()}
        if len(fns) != 1:
            raise ValueError(
                "0060 expects every sample to point at the same input catalog"
            )
        fn = self.rootdir / "inputcats" / fns.pop()
        logger.info("reading targets from %s", fn)
        targets = Table.read(fn)
        for col in targets.colnames:
            if targets[col].dtype.kind == "S":
                targets[col] = targets[col].astype(str)

        catalog_samples = set(np.unique(targets["TERTIARY_TARGET"]))
        missing = catalog_samples - set(self.samples)
        if missing:
            raise ValueError(
                "catalog TERTIARY_TARGET values missing from yaml: {}".format(
                    sorted(missing)
                )
            )

        if "TARGETID" in targets.colnames:
            logger.info("dropping %d input TARGETID values", len(targets))
            targets.remove_column("TARGETID")
        if "SUBPRIORITY" in targets.colnames:
            targets.remove_column("SUBPRIORITY")

        targets = finalize_target_table(targets, self.yamlfp)
        targets.meta["PROGNUM"] = self.settings["prognum"]
        logger.info(
            "assigned %d TARGETID values for prognum %s",
            len(targets),
            self.settings["prognum"],
        )
        targets.write(outfp, overwrite=True)
