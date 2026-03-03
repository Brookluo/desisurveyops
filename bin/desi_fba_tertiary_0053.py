import os
from typing import List, Dict
import numpy as np
from pathlib import Path
from astropy.table import Table, vstack
from astropy.coordinates import SkyCoord
import astropy.units as u
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
    merge_target_catalogs,
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
        # YL: tile centers are provided by VM
        pass

    def create_priorities(self, outfp: str):
        tab = creates_priority_table(self.yamlfp)
        tab.pprint_all()
        for sample in np.unique(tab["TERTIARY_TARGET"]):
            logger.info(
                f"Sample {sample} has priority {tab['PRIORITY'][tab['TERTIARY_TARGET'] == sample][0]}"
            )
        tab.write(outfp)

    def create_targets(self, outfp: str):
        # YL: Split VM's targets into the three catalogs individually, then merge with XLG targets. XLG targets act as higher priority fillers.
        vm_targets = Table.read(
            self.rootdir / "inputcats" / "tertiary-targets-9410-v2.fits"
        )
        for samp in np.unique(vm_targets["TERTIARY_TARGET"]):
            samp_targets = vm_targets[vm_targets["TERTIARY_TARGET"] == samp]
            samp_targets.write(self.rootdir / "inputcats" / f"{samp}-targets.fits")
        # YL: Now add the ToO targets. Their priority is set to be higher than fillers but lower than LOWP
        # too = Table.read(
        #     Path(os.getenv("DESI_SURVEYOPS"), "mtl", "main", "ToO", "ToO.ecsv")
        # )
        # too_coords = SkyCoord(ra=too["RA"], dec=too["DEC"], unit="deg")
        # field_coord = SkyCoord(
        #     ra=self.settings["field_ra"], dec=self.settings["field_dec"], unit="deg"
        # )
        # sel_toos = (
        #     field_coord.separation(too_coords) < 2 * u.deg
        # )  # the field is 2 deg in radius
        # too_targ = too[sel_toos][
        #     [
        #         "TARGETID",
        #         "RA",
        #         "DEC",
        #         "PMDEC",
        #         "SUBPRIORITY",
        #         "REF_EPOCH",
        #         "PRIORITY_INIT",
        #         "PMRA",
        #         "CHECKER",
        #     ]
        # ]
        # too_targ.add_column(["TOO"] * len(too_targ), name="TERTIARY_TARGET")
        # too_targ.add_column(
        #     [self.samples["TOO"]["NGOAL"]] * len(too_targ), name="NGOAL"
        # )
        # too_targ.write(self.rootdir / "inputcats" / "TOO-targets.fits")

        targets = merge_target_catalogs(
            self.rootdir / "inputcats",
            self.samples,
            remove_duplicates=True,
        )
        targets = finalize_target_table(targets, self.yamlfp)
        # targets = vstack([too_targ, targets])
        # YL: restore checker column for TOO targets
        # targ_coords = SkyCoord(ra=targets["RA"], dec=targets["DEC"], unit="deg")
        # too_coords = SkyCoord(ra=too_targ["RA"], dec=too_targ["DEC"], unit="deg")
        # idx_too, idx_targ, sep, _ = targ_coords.search_around_sky(too_coords, seplimit=0.01 * u.arcsec)
        # if targets["CHECKER"].dtype < too_targ["CHECKER"].dtype:
        #     targets["CHECKER"] = targets["CHECKER"].astype(too_targ["CHECKER"].dtype)  # ensure the dtype can hold both
        # targets["CHECKER"][idx_targ] = too_targ["CHECKER"][idx_too]
        targets.write(outfp)
