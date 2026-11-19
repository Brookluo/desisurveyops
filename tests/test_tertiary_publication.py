import os
import runpy
import subprocess
import sys
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from unittest.mock import patch

import pytest

from desisurveyops import tertiary_status as status


CLI = Path(__file__).resolve().parents[1] / "bin" / "desi_tertiary_status"


def test_interrupted_qa_and_retry(tmp_path, monkeypatch):
    page = tmp_path / "tertiary-status.html"
    pdf = tmp_path / "tileqa" / "tileqa-tertiary2.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"previous PDF")
    page.write_text("previous page")
    page.chmod(0o640)
    prior_inode = page.stat().st_ino
    monkeypatch.setenv("DESI_ROOT", str(tmp_path))
    monkeypatch.setattr(sys, "argv", [str(CLI), "--prognums", "2", "--outdir", str(tmp_path)])
    monkeypatch.setattr(status, "get_prognum_desc", lambda: {2: {}})
    monkeypatch.setattr(status, "write_html_overview", lambda html, _: html.write("overview\n"))

    def render(html, prognum, outdir, *args):
        html.write(f"Tertiary{prognum}\n")
        (Path(outdir) / "tileqa" / pdf.name).write_bytes(b"updated PDF")
        if fail:
            raise RuntimeError("simulated QA failure")

    monkeypatch.setattr(status, "write_html_prognum", render)
    fail = True
    with pytest.raises(RuntimeError, match="simulated QA failure"):
        runpy.run_path(str(CLI), run_name="__main__")
    assert page.stat().st_ino == prior_inode
    assert page.read_text() == "previous page"
    assert pdf.read_bytes() == b"previous PDF"

    fail = False
    with patch.object(status, "write_html_close", lambda html: html.write("incomplete footer")):
        with pytest.raises(RuntimeError, match="Incomplete"):
            runpy.run_path(str(CLI), run_name="__main__")
    assert page.stat().st_ino == prior_inode
    assert pdf.read_bytes() == b"previous PDF"

    # Slurm can kill a writer before its finally block removes this directory.
    abandoned = tmp_path / ".tertiary-status-stage"
    abandoned.mkdir()
    (abandoned / "partial").touch()
    runpy.run_path(str(CLI), run_name="__main__")
    assert page.stat().st_ino != prior_inode
    assert page.stat().st_mode & 0o777 == 0o640
    assert page.read_text().endswith("</body></html>\n")
    assert "Tertiary2" in page.read_text()
    assert pdf.read_bytes() == b"updated PDF"
    assert not abandoned.exists()


def test_killed_qa_worker_reports_failure():
    with pytest.raises(BrokenProcessPool):
        list(status._qa_results(os._exit, [(1,)], 1))


def test_cached_exposure_catalog_isolated_and_refreshed(tmp_path, monkeypatch):
    monkeypatch.setenv("DESI_ROOT", str(tmp_path))
    redux = tmp_path / "spectro" / "redux" / "daily"
    redux.mkdir(parents=True)
    catalog = redux / "exposures-daily.csv"
    header = "EXPID,EFFTIME_SPEC,FAPRGRM\n"
    catalog.write_text(header + "1,10,tertiary2\n2,0,tertiary2\n3,20,tertiary1\n")
    rows = status.read_exposures("daily", prognum=2)
    assert list(rows["EXPID"]) == [1]
    rows["EFFTIME_SPEC"][0] = 999
    assert list(status.read_exposures("daily")["EFFTIME_SPEC"]) == [10, 20]
    replacement = redux / "replacement.csv"
    replacement.write_text(header + "4,15,tertiary2\n")
    replacement.replace(catalog)
    assert list(status.read_exposures("daily", prognum=2)["EXPID"]) == [4]


@pytest.mark.skipif(not Path("/global/cfs/cdirs/desi/software/desi_environment.sh").exists(),
                    reason="requires the NERSC DESI environment")
@pytest.mark.parametrize(("render", "exit_status"), [
    ("exit 27", 27),
    ("exit 0", 1),
    ("echo incomplete > staged && mv staged tertiary-status.html", 1),
    ("echo '</body></html>' > staged && mv staged tertiary-status.html", 0),
])
def test_worker_reports_publication_status(tmp_path, render, exit_status):
    page = tmp_path / "tertiary-status.html"
    page.write_text("previous page\n</body></html>\n")
    generator = tmp_path / "bin" / CLI.name
    generator.parent.mkdir()
    generator.write_text("#!/bin/bash\n" + render + "\n")
    generator.chmod(0o755)
    result = subprocess.run(["bash", CLI.with_name("tertiary-status-worker.sbatch"),
                             "2", tmp_path], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == exit_status, result.stderr
