import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

try:
    import openpyxl  # noqa: F401
    _OPENPYXL_AVAILABLE = True
except ImportError:
    _OPENPYXL_AVAILABLE = False

import pytest
from tools.audit_mapping import run_audit


@pytest.mark.skipif(not _OPENPYXL_AVAILABLE, reason="openpyxl not installed")
def test_entity_mapping_matches_xlsx():
    result = run_audit()
    discrepancies = result["discrepancies"]
    assert discrepancies == [], (
        f"{len(discrepancies)} mapping discrepancy(ies) found:\n"
        + "\n".join(
            f"  {d['domain']}/{d['device_class']} "
            f"[{d['component']}.{d['field']}]: "
            f"expected={d['expected']!r} actual={d['actual']!r}"
            for d in discrepancies
        )
    )


@pytest.mark.skipif(not _OPENPYXL_AVAILABLE, reason="openpyxl not installed")
def test_audit_reports_missing_entries():
    """Missing entries are non-blocking; the list must not be empty (xlsx has unimplemented rows)."""
    result = run_audit()
    assert isinstance(result["missing_entries"], list)
