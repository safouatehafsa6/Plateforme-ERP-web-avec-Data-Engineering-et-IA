import pytest
from app.services import transferts

COLS=["id","nom","montant","date_creation"]
ROWS=[[1,"Entreprise A",12.5,"2026-11-18"],[2,"Entreprise B",8.0,"2026-11-17"]]

@pytest.mark.parametrize("fmt",["csv","xlsx","ods","json","xml","yaml","sqlite","zip","tar","gz"])
def test_formats_structures_round_trip(fmt):
    payload,mime=transferts.encoder(COLS,ROWS,fmt)
    assert payload and mime
    result=transferts.decoder(payload,fmt)
    assert len(result)==2

@pytest.mark.parametrize("fmt",["zip","tar","gz","ods","rtf","odt"])
def test_formats_export_document_et_archives(fmt):
    payload,mime=transferts.encoder(COLS,ROWS,fmt)
    assert payload and mime
