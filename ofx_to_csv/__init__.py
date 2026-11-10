"""Single-account OFX bank/card transactions to CSV."""
import csv
import html
import io
import re
import warnings
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree as ET

__all__ = ["convert"]

CONTAINERS = set("OFX SIGNONMSGSRSV1 SONRS STATUS FI BANKMSGSRSV1 STMTTRNRS STMTRS BANKACCTFROM BANKTRANLIST STMTTRN BANKTRANLISTP STMTTRNP LEDGERBAL AVAILBAL CREDITCARDMSGSRSV1 CCSTMTTRNRS CCSTMTRS CCACCTFROM CURRENCY ORIGCURRENCY".split())
TRANSACTION_TYPES = set("CREDIT DEBIT INT DIV FEE SRVCHG DEP ATM POS XFER CHECK PAYMENT CASH DIRECTDEP DIRECTDEBIT REPEATPMT HOLD OTHER".split())


def _parse(raw):
    text = raw.decode("utf-8-sig")
    if "<!" in text:
        raise ValueError("DTD, entities and XML declarations other than processing instructions are unsupported.")
    start = re.search(r"<(?:\w+:)?OFX(?:\s[^>]*)?>", text, re.I)
    if not start:
        raise ValueError("No OFX root found.")
    content = text[start.start():]
    try:
        root = ET.fromstring(content)
        for node in root.iter():
            node.tag = node.tag.rsplit("}", 1)[-1].upper()
        return root
    except ET.ParseError:
        if "OFXHEADER:" not in text.upper() or "DATA:OFXSGML" not in text.upper():
            raise ValueError("Malformed OFX XML.") from None
    # shortcut: SGML supports only explicitly closed bank/card containers; use the online version for other layouts.
    tokens = list(re.finditer(r"<(/?)([A-Za-z][A-Za-z0-9_.]*)\s*>", content))
    stack, root, end = [], None, 0
    for index, token in enumerate(tokens):
        if content[end:token.start()].strip():
            raise ValueError("Unexpected text between OFX tags.")
        closing, tag = token[1], token[2].upper()
        if closing:
            if not stack or stack[-1].tag != tag:
                raise ValueError("Unbalanced OFX tags.")
            stack.pop()
            end = token.end()
        else:
            node = ET.Element(tag)
            if stack:
                stack[-1].append(node)
            elif root is None and tag == "OFX":
                root = node
            else:
                raise ValueError("Unexpected OFX root.")
            end = token.end()
            if tag in CONTAINERS:
                stack.append(node)
            else:
                end = tokens[index + 1].start() if index + 1 < len(tokens) else len(content)
                leaf = content[token.end():end].strip()
                if "<" in leaf or ">" in leaf:
                    raise ValueError("Unsupported OFX markup.")
                node.text = html.unescape(leaf)
                if index + 1 < len(tokens) and tokens[index + 1][1] and tokens[index + 1][2].upper() == tag:
                    stack.append(node)
        if len(stack) > 30:
            raise ValueError("OFX nesting exceeds 30 levels.")
    if root is None or stack or content[end:].strip():
        raise ValueError("Incomplete OFX statement.")
    return root


def _value(node, path):
    found = node.find(path)
    return (found.text or "").strip() if found is not None else ""


def _safe(text):
    if any(ord(ch) < 32 and ch not in "\t\n\r" for ch in text):
        raise ValueError("Unsupported text control character.")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def convert(source, target):
    """Export posted transactions; warn for skipped pending rows, reject pending-only files."""
    source, target = Path(source), Path(target)
    if source.suffix.lower() != ".ofx" or target.suffix.lower() != ".csv":
        raise ValueError("Use an .ofx input and .csv output.")
    if source.stat().st_size > 15 * 1024 * 1024:
        raise ValueError("OFX exceeds 15 MiB.")
    root = _parse(source.read_bytes())
    if any(node.tag.startswith("INV") for node in root.iter()):
        raise ValueError("Investment statements are unsupported.")
    statements = [*root.findall(".//STMTRS"), *root.findall(".//CCSTMTRS")]
    if len(statements) != 1:
        raise ValueError("Exactly one bank or credit-card statement is required.")
    if any(_value(status, "CODE") != "0" for status in root.findall(".//STATUS")):
        raise ValueError("OFX contains a non-success status.")
    statement = statements[0]
    accounts = [*statement.findall("BANKACCTFROM"), *statement.findall("CCACCTFROM")]
    if len(accounts) != 1 or not _value(accounts[0], "ACCTID"):
        raise ValueError("Account ID is required.")
    if len(statement.findall("CURDEF")) != 1:
        raise ValueError("Exactly one account currency is required.")
    currency = _value(statement, "CURDEF")
    if not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("One three-letter account currency is required.")
    rows = []
    transactions = statement.findall("BANKTRANLIST/STMTTRN")
    if len(transactions) != len(root.findall(".//STMTTRN")):
        raise ValueError("Transactions outside the single statement are unsupported.")
    pending = len(root.findall(".//STMTTRNP"))
    if pending and not transactions:
        raise ValueError(f"No posted transactions found; {pending} pending STMTTRNP transactions are not exported.")
    for number, trn in enumerate(transactions, 1):
        for tag in ("DTPOSTED", "TRNAMT", "FITID", "TRNTYPE"):
            if len(trn.findall(tag)) != 1 or not _value(trn, tag):
                raise ValueError(f"Transaction {number}: require exactly one nonempty {tag}.")
        if _value(trn, "TRNTYPE") not in TRANSACTION_TYPES:
            raise ValueError(f"Transaction {number}: invalid TRNTYPE.")
        if any(trn.find(tag) is not None for tag in ("CORRECTFITID", "CORRECTACTION", "CURRENCY", "ORIGCURRENCY")):
            raise ValueError("Corrections and transaction-level currencies are unsupported.")
        raw_date = _value(trn, "DTPOSTED")
        if not re.fullmatch(r"\d{8}(?:\d{6}(?:\.\d+)?)?(?:\[[^\]\r\n]{1,30}\])?", raw_date):
            raise ValueError("Unsupported OFX date.")
        day = datetime.strptime(raw_date[:8], "%Y%m%d").date().isoformat()
        if len(raw_date) >= 14 and raw_date[8:14].isdigit():
            datetime.strptime(raw_date[:14], "%Y%m%d%H%M%S")
        amount = _value(trn, "TRNAMT")
        if not re.fullmatch(r"-?\d{1,13}(?:\.\d{1,2})?", amount):
            raise ValueError("Use dot-decimal amounts with at most two decimal places.")
        rows.append([day, _safe(_value(trn, "NAME")), _safe(_value(trn, "MEMO")),
                     format(Decimal(amount), ".2f"), _safe(_value(trn, "FITID")), _safe(_value(trn, "TRNTYPE"))])
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["date", "name", "memo", "amount", "fitid", "type"])
    writer.writerows(rows)
    if pending:
        warnings.warn(f"Skipped {pending} pending STMTTRNP transactions; only posted STMTTRN transactions are exported.",
                      UserWarning, stacklevel=2)
    with target.open("x", encoding="utf-8", newline="") as output:
        output.write(buffer.getvalue())
    return len(rows)
