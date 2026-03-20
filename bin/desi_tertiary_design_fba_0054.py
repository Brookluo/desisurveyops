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
from fiberassign.fba_tertiary_io import get_toofn
from desiutil.log import get_logger
from astropy.io import fits
from astropy.table import Table
import subprocess


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
        # YL: tile centers are provided by Haruki Ebina (HE)
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
        targets = merge_target_catalogs(
            self.rootdir / "inputcats",
            self.samples,
            remove_duplicates=False,
        )
        targets = finalize_target_table(targets, self.yamlfp)
        targets.write(outfp)


def execute_fba(args):
    ttsetting = read_yaml(args.yaml_file_path)["settings"]
    rundate = ttsetting["rundate"]
    targdir = ttsetting["targdir"]
    prognum = ttsetting["prognum"]
    std_dtver = ttsetting["std_dtver"]
    
    link = Path(targdir, f"tertiary-priorities-{prognum:04d}.ecsv")
    # initial targets
    link.symlink_to(Path(targdir, f"tertiary-priorities-{prognum:04d}_tile123.ecsv"))
    
    assert_files(prognum, targdir)
    # AR some settings
    fadir = targdir
    hdr_survey = "special"  # AR what will be recorded in the fiberassign header

    # AR grab some fiberassign settings from TARGFN header
    targfn = get_fn(prognum, "targets", targdir)
    hdr = fits.getheader(targfn, "TARGETS")
    hdr_faprgrm = hdr["FAPRGRM"]
    obsconds = hdr["OBSCONDS"]
    sbprof = hdr["SBPROF"]
    goaltime = hdr["GOALTIME"]

    # AR fiberassign settings, only for the standard stars
    std_survey = "main"
    if std_dtver == "2.2.0":
        std_faprgrm = "BACKUP"
        logger.info("std_dtver=2.2.0 => using BACKUP stars for standard stars")
    else:
        if not obsconds in ["BRIGHT", "DARK"]:
            msg = (
                "obsconds={} => only BRIGHT or DARK authorized for std_dtver={}".format(
                    obsconds, std_dtver
                )
            )
            logger.error(msg)
            raise ValueError(msg)
        std_faprgrm = obsconds

    # AR tiles
    tilesfn = get_fn(prognum, "tiles", targdir)
    tiles = Table.read(tilesfn)
    ntile = len(tiles)

    # AR loop on tiles
    if args.only_tileid:
        tile_idx = [np.where(tiles["TILEID"] == args.only_tileid)[0][0]]
    else:
        tile_idx = np.arange(ntile, dtype=int)
    for i in tile_idx:
        # AR tile properties
        tileid = tiles["TILEID"][i]
        tilera, tiledec = tiles["RA"][i], tiles["DEC"][i]
        tileha = tiles["DESIGNHA"][i]
        
        if i == 3:
            # next 2 tiles with special priorities
            prio_fn = f"tertiary-priorities-{prognum:04d}_tile45.ecsv"
            prio_fp = Path(targdir, prio_fn)
            if link.exists() and link.is_symlink():
                link.unlink()
            else:
                raise FileNotFoundError(f"Expected symlink {link} does not exist or is not a symlink.")
            link.symlink_to(prio_fp)
        
        # AR ToO files
        toofn = get_toofn(prognum, tileid, targdir=targdir)
        logfn = toofn.replace(".ecsv", ".log")
        logger.info("toofn = {}".format(toofn))

        # AR fba_tertiary_too call
        ftt_cmd = [
            "fba_tertiary_too",
            "--tileid", str(tileid),
            "--tilera", str(tilera),
            "--tiledec", str(tiledec),
            "--targdir", targdir,
            "--fadir", fadir,
            "--prognum", str(prognum),
        ]
        if i >= 1:
            prev_tileids = ",".join(tiles["TILEID"][:i].astype(str))
            ftt_cmd.extend(["--previous_tileids", prev_tileids])
        # cmd = "{} > {} 2>&1".format(cmd, logfn)
        # switch the above command with subprocess call and direct output
        logger.info("Running command: {}".format(" ".join(ftt_cmd)))
        if not args.dry_run:
            with open(logfn, "a+") as fp:
                result = subprocess.run(ftt_cmd, stderr=subprocess.STDOUT, stdout=fp)
                if result.returncode != 0:
                    logger.error(f"Error executing fba_tertiary_too: exit code {result.returncode}. Check {logfn} for details.")
        # AR fba_launch call
        fl_cmd = [
            "fba_launch",
            "--outdir", fadir,
            # tiles
            "--tileid", str(tileid),
            "--tilera", str(tilera),
            "--tiledec", str(tiledec),
            "--ha", str(tileha),
            # date
            "--rundate", rundate,
            # tertiary program settings
            "--sbprof", sbprof, "--goaltime", str(goaltime),
            # standard stars
            "--survey", std_survey,
            "--program", std_faprgrm,
            "--dtver", std_dtver,
            "--targ_std_only",
            # no secondary targets
            "--nosteps", "scnd",
            # GOALTIME, SURVEY and FAPRGRM header keywords
            "--goaltype", obsconds, "--hdr_survey", hdr_survey, "--hdr_faprgrm", hdr_faprgrm,
        ]
        # Add ToO file
        all_toofn = toofn
        if args.add_main_too:
            maintoofn = os.path.join(
                os.getenv("DESI_SURVEYOPS"), "mtl", "main", "ToO", "ToO.ecsv"
            )
            all_toofn += f",{maintoofn}"
        fl_cmd.extend(["--too_tile", "--custom_too_file", all_toofn])
        # AR force tileid?
        # AR    ! use with caution !
        # AR    (for cases where tiles are re-designed after having been svn-committed)
        if args.forcetileid:
            fl_cmd.extend(["--forcetileid", "y"])
        # AR custom_too_development?
        # AR    use for testing the design
        if args.custom_too_development:
            fl_cmd.append("--custom_too_development")
        logger.info("Running command: {}".format(" ".join(fl_cmd)))
        if not args.dry_run:
            with open(logfn, "a+") as fp:
                result = subprocess.run(fl_cmd, stderr=subprocess.STDOUT, stdout=fp)
                if result.returncode != 0:
                    logger.error(f"Error executing fba_launch: exit code {result.returncode}. Check {logfn} for details.")
