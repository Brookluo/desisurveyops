from typing import List, Dict
import numpy as np
from pathlib import Path
from astropy.table import Table, vstack
from desisurveyops.fba_tertiary_design_io import (
    assert_environ_settings,
    assert_files,
    assert_tertiary_settings,
    create_targets_assign,
    create_tiles_table,
    creates_priority_table,
    finalize_target_table,
    get_fn,
    get_tile_centers_rosette,
    match_coord,
    plot_targets_assign,
    print_samples_overlap,
    read_yaml,
    subsample_targets_avail,
    TertiaryTileDesignBase,
    merge_target_catalogs
)
from desiutil.log import get_logger

logger = get_logger()


class TertiaryTileDesign(TertiaryTileDesignBase):
    """Tertiary Tile Design for XMM High-z (prognum)

    This class implements the specific tertiary tile design logic for the XMM High-z program.
    It inherits from TertiaryTileDesignBase and overrides necessary methods to perform the design.

    Attributes:
        yamlfp (str): The path to the yaml file containing the tertiary design configuration.
    """

    def __init__(self, yamlfp: str):
        self.yamlfp = yamlfp
        self.settings = read_yaml(yamlfp)["settings"]
        self.samples = read_yaml(yamlfp)["samples"]
        self.rootdir = Path(self.settings["targdir"])

    def create_tiles(self, outfp: str):
        field_ra, field_dec = self.settings["field_ra"], self.settings["field_dec"]
        ras, decs = get_tile_centers_rosette(field_ra, field_dec, self.settings["ntile"])
        rundate = self.settings["rundate"]
        obsconds = self.settings["obsconds"]
        tileids = np.arange(
            self.settings["tileid_start"],
            self.settings["tileid_start"] + self.settings["ntile"],
            dtype=int,
        )
        tab = create_tiles_table(tileids, ras, decs, obsconds)
        tab.write(outfp)

    def create_priorities(self, outfp: str):
        tab = creates_priority_table(self.yamlfp)
        tab.pprint_all()
        for sample in np.unique(tab["TERTIARY_TARGET"]):
            sel = tab["TERTIARY_TARGET"] == sample
            logger.info("priorites for {}: {}".format(sample, tab["PRIORITY"][sel].tolist()))
        tab.write(outfp)


    def create_targets(self, outfp: str):
        targets = merge_target_catalogs(self.rootdir / "inputcats", self.samples)
        
        targets = finalize_target_table(targets, self.yamlfp)
        targets.write(outfp)
        