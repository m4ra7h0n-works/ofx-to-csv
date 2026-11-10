import csv
import re
import subprocess
import sys
from pathlib import Path

import pytest

from ofx_to_csv import convert

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
SGML = (EXAMPLES / "statement.ofx").read_text()
XML = '''<?xml version="1.0"?><OFX xmlns="urn:synthetic:ofx">
<CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS><CURDEF>USD</CURDEF>
<CCACCTFROM><ACCTID>000002</ACCTID></CCACCTFROM><BANKTRANLIST>
<STMTTRN><DTPOSTED>20260201120000[-5:EST]</DTPOSTED><TRNAMT>-1.25</TRNAMT>
<NAME>Sample &amp; Co</NAME><MEMO>=1+1</MEMO><FITID>00003</FITID><TRNTYPE>DEBIT</TRNTYPE></STMTTRN>
</BANKTRANLIST></CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1></OFX>'''


def run(tmp_path, text):
    source, target = tmp_path / "source.ofx", tmp_path / "output.csv"
    source.write_text(text, encoding="utf-8")
    return convert(source, target), target


def test_bundled_example(tmp_path):
    count, output = run(tmp_path, SGML)
    assert count == 2
    assert output.read_bytes() == (EXAMPLES / "transactions.csv").read_bytes()


def test_xml_card_namespace_and_formula(tmp_path):
    count, output = run(tmp_path, XML)
    rows = list(csv.DictReader(output.open()))
    assert count == 1
    assert rows[0] == dict(date="2026-02-01", name="Sample & Co", memo="'=1+1", amount="-1.25", fitid="00003", type="DEBIT")


@pytest.mark.parametrize("text", [
    SGML.replace("</OFX>", ""),
    SGML.replace("<CODE>0", "<CODE>2000"),
    SGML.replace("20260102120000", "20260230120000"),
    SGML.replace("-12.50", "NaN"),
    SGML.replace("<CURDEF>USD", "<CURDEF>US"),
    SGML.replace("<ACCTID>000001", "<ACCTID>"),
    SGML.replace("<CURDEF>USD", "<CURDEF>USD<CURDEF>EUR"),
    SGML.replace("<TRNAMT>-12.50", "<TRNAMT>-12.50<TRNAMT>999.00"),
    SGML.replace("</BANKACCTFROM>", "</BANKACCTFROM><BANKACCTFROM><ACCTID>000002</BANKACCTFROM>"),
    SGML.replace("<FITID>fictional-001", "<CORRECTFITID>old<FITID>fictional-001"),
    SGML.replace("<FITID>fictional-001", "<CURRENCY><CURSYM>EUR</CURRENCY><FITID>fictional-001"),
    SGML.replace("</OFX>", "<INVSTMTRS></INVSTMTRS></OFX>"),
    SGML.replace("</OFX>", "<STMTRS></STMTRS></OFX>"),
    XML.replace("</TRNAMT>", ""),
    '<!DOCTYPE OFX [<!ENTITY x "bad">]>' + XML,
])
def test_reject_unsupported_without_partial_output(tmp_path, text):
    with pytest.raises(ValueError):
        run(tmp_path, text)
    assert not (tmp_path / "output.csv").exists()


def test_empty_statement(tmp_path):
    text = re.sub(r"<STMTTRN>.*?</STMTTRN>", "", SGML)
    count, output = run(tmp_path, text)
    assert count == 0
    assert len(output.read_text().splitlines()) == 1


def test_no_overwrite_or_qfx_input(tmp_path):
    source, target = tmp_path / "source.ofx", tmp_path / "output.csv"
    source.write_text(SGML)
    target.write_text("keep")
    with pytest.raises(FileExistsError):
        convert(source, target)
    assert target.read_text() == "keep"
    with pytest.raises(ValueError, match=".ofx"):
        convert(source.with_suffix(".qfx"), target)


def test_cli(tmp_path):
    output = tmp_path / "output.csv"
    result = subprocess.run([sys.executable, "-m", "ofx_to_csv", str(EXAMPLES / "statement.ofx"), str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    failed = subprocess.run([sys.executable, "-m", "ofx_to_csv", str(EXAMPLES / "statement.ofx"), str(output)], capture_output=True, text=True)
    assert failed.returncode == 2
    assert "Traceback" not in failed.stderr


@pytest.mark.parametrize("template", [SGML, XML])
@pytest.mark.parametrize("tag", ["DTPOSTED", "TRNAMT", "FITID", "TRNTYPE"])
@pytest.mark.parametrize("invalid", ["missing", "empty", "duplicate"])
def test_required_transaction_fields(tmp_path, template, tag, invalid):
    pattern = rf"<{tag}>[^<]*(?:</{tag}>)?"
    field = re.search(pattern, template)[0]
    replacement = {"missing": "", "empty": f"<{tag}> </{tag}>", "duplicate": field + field}[invalid]
    text = template.replace(field, replacement, 1)
    with pytest.raises(ValueError, match=tag):
        run(tmp_path, text)
    assert not (tmp_path / "output.csv").exists()


@pytest.mark.parametrize("text", [SGML.replace("<TRNTYPE>DEBIT", "<TRNTYPE>INVALID"),
                                       SGML.replace("20260102120000", "20260102999999")])
def test_invalid_type_or_timestamp(tmp_path, text):
    with pytest.raises(ValueError):
        run(tmp_path, text)
    assert not (tmp_path / "output.csv").exists()


@pytest.mark.parametrize("amount,expected", [("-12", "-12.00"), ("0", "0.00"), ("1.2", "1.20")])
def test_integer_and_dot_decimal_amounts(tmp_path, amount, expected):
    _, output = run(tmp_path, SGML.replace("-12.50", amount))
    assert next(csv.DictReader(output.open()))["amount"] == expected


@pytest.mark.parametrize("template", [SGML, XML])
@pytest.mark.parametrize("only_pending", [False, True])
def test_pending_transactions(tmp_path, template, only_pending):
    transaction = re.search(r"<STMTTRN>.*?</STMTTRN>", template, re.S)[0]
    pending = transaction.replace("STMTTRN", "STMTTRNP").replace("DTPOSTED", "DTTRAN")
    text = template
    if only_pending:
        text = re.sub(r"<STMTTRN>.*?</STMTTRN>", "", text, flags=re.S)
    closing = "</CCSTMTRS>" if "</CCSTMTRS>" in text else "</STMTRS>"
    text = text.replace(closing, "<BANKTRANLISTP>" + pending + "</BANKTRANLISTP>" + closing)
    if only_pending:
        with pytest.raises(ValueError, match="No posted transactions.*pending STMTTRNP"):
            run(tmp_path, text)
        assert not (tmp_path / "output.csv").exists()
        source = tmp_path / "source.ofx"
        result = subprocess.run([sys.executable, "-m", "ofx_to_csv", str(source), str(tmp_path / "output.csv")],
                                capture_output=True, text=True)
        assert result.returncode == 2
        assert "pending STMTTRNP" in result.stderr
    else:
        with pytest.warns(UserWarning, match="Skipped 1 pending STMTTRNP"):
            count, output = run(tmp_path, text)
        assert count == (2 if template == SGML else 1)
        assert len(list(csv.DictReader(output.open()))) == count
