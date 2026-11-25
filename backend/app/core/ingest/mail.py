"""E-mails (.eml, .msg): headers, body, and every attachment, read like an upload of its own."""
from __future__ import annotations

import datetime as dt
import email
import hashlib
import re
import struct
from email import policy
from pathlib import Path

from .media import add_picture
from .model import Options, Parsed
from .text import clean, decode, split, strip_html

SKIP_ATTACHMENTS = {"smime.p7s", "winmail.dat"}


def _header_block(h: dict) -> str:
    return "\n".join(f"{label}: {h[k]}" for k, label in (("from", "Von"), ("to", "An"), ("cc", "Kopie"), ("date", "Datum"), ("subject", "Betreff")) if h.get(k))


def _strip_quotes(text: str) -> str:
    """Reply chains repeat the earlier mails. Keep them (they hold decisions) but drop the '>' markers of quoted lines."""
    return "\n".join(re.sub(r"^(?:>\s?)+", "", l) for l in text.split("\n"))


def read_eml(data: bytes, parse_member, opts: Options, depth: int) -> Parsed:
    msg = email.message_from_bytes(data, policy=policy.default)
    return _from_message(msg, parse_member, opts, depth)


def _parts(m):
    """All leaf parts of a message. A forwarded message (message/rfc822) is one part: it is read as a mail of its own, not taken apart here."""
    if not m.is_multipart():
        return
    for part in m.iter_parts():
        if part.get_content_type() == "message/rfc822":
            yield part
        elif part.is_multipart():
            yield from _parts(part)
        else:
            yield part


def _from_message(msg, parse_member, opts: Options, depth: int) -> Parsed:
    headers = {k: str(msg.get(h, "") or "") for k, h in (("from", "From"), ("to", "To"), ("cc", "Cc"), ("date", "Date"), ("subject", "Subject"))}
    p = Parsed("eml", title=headers["subject"], meta={k: v for k, v in headers.items() if v})
    body = msg.get_body(preferencelist=("plain", "html"))
    text = ""
    if body is not None:
        try:
            text = body.get_content()
        except Exception:  # noqa: BLE001
            text = decode(body.get_payload(decode=True) or b"")
        if body.get_content_type() == "text/html":
            text = strip_html(text)
    p.chunks += split("E-Mail", _header_block(headers) + "\n\n" + _strip_quotes(clean(text)))
    seen: set[str] = set()
    for part in _parts(msg):
        if part is body:
            continue
        ctype = part.get_content_type()
        name = part.get_filename() or ""
        disp = (part.get_content_disposition() or "").lower()
        if ctype == "text/plain" and not name and disp != "attachment":
            continue
        if ctype == "text/html" and not name and disp != "attachment":
            continue
        try:
            blob = part.get_payload(decode=True) if ctype != "message/rfc822" else part.get_payload()[0].as_bytes()
        except Exception:  # noqa: BLE001
            continue
        if not blob:
            continue
        if ctype == "message/rfc822" and not name:
            name = "weitergeleitet.eml"
        if not name:
            ext = {"image/png": "png", "image/jpeg": "jpg", "application/pdf": "pdf"}.get(ctype, "")
            if not ext:
                continue
            name = f"inline.{ext}"
        sha = hashlib.sha256(blob).hexdigest()
        if sha in seen or name.lower() in SKIP_ATTACHMENTS:
            continue
        seen.add(sha)
        ext = Path(name).suffix.lower().lstrip(".")
        if ext in ("png", "jpg", "jpeg", "gif", "bmp", "webp") and len(blob) < opts.min_attachment_image_bytes:
            continue  # signature logos and tracking pixels
        if depth >= opts.max_depth:
            p.warnings.append(f"attachment „{name}“ not read (nesting too deep)")
            continue
        try:
            child = parse_member(name, blob, depth + 1)
        except Exception as e:  # noqa: BLE001
            p.warnings.append(f"attachment „{name}“ not read: {str(e)[:140]}")
            continue
        p.absorb(child, f"Anhang „{name}“")
        p.meta.setdefault("attachments", []).append(name)
    return p


# ------------------------------------------------------------------------------------------- Outlook .msg
def _stream(ole, path: str) -> bytes | None:
    try:
        if ole.exists(path):
            return ole.openstream(path).read()
    except Exception:  # noqa: BLE001
        pass
    return None


def _prop(ole, prefix: str, tag: str) -> str:
    """A string property of a .msg storage: Unicode (001F) preferred, else ANSI (001E)."""
    raw = _stream(ole, f"{prefix}__substg1_0_{tag}001F")
    if raw is not None:
        return raw.decode("utf-16-le", "replace").rstrip("\x00")
    raw = _stream(ole, f"{prefix}__substg1_0_{tag}001E")
    return decode(raw).rstrip("\x00") if raw is not None else ""


def _filetime(ole, prefix: str) -> str:
    """PR_CLIENT_SUBMIT_TIME from the properties stream (an 8-byte FILETIME), as a date string."""
    raw = _stream(ole, f"{prefix}__properties_version1.0")
    if not raw:
        return ""
    start = 32 if not prefix else 8  # the top-level stream has a longer header than attachments / embedded messages
    for off in range(start, len(raw) - 15, 16):
        tag, _flags, val = struct.unpack_from("<IIQ", raw, off)
        if tag == 0x00390040:  # PR_CLIENT_SUBMIT_TIME, type PT_SYSTIME
            try:
                return (dt.datetime(1601, 1, 1) + dt.timedelta(microseconds=val // 10)).strftime("%Y-%m-%d %H:%M")
            except OverflowError:
                return ""
    return ""


def read_msg(data: bytes, parse_member, opts: Options, depth: int) -> Parsed:
    import io

    import olefile

    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise ValueError("the .msg file cannot be opened") from e
    try:
        return msg_from_ole(ole, "", parse_member, opts, depth)
    finally:
        ole.close()


def msg_from_ole(ole, prefix: str, parse_member, opts: Options, depth: int) -> Parsed:
    headers = {"from": _prop(ole, prefix, "0C1A") or _prop(ole, prefix, "0065"), "to": _prop(ole, prefix, "0E04"), "cc": _prop(ole, prefix, "0E03"),
               "date": _filetime(ole, prefix), "subject": _prop(ole, prefix, "0037")}
    p = Parsed("msg", title=headers["subject"], meta={k: v for k, v in headers.items() if v})
    body = _prop(ole, prefix, "1000")
    if not body:
        html_raw = _stream(ole, f"{prefix}__substg1_0_10130102")
        body = strip_html(decode(html_raw)) if html_raw else ""
    p.chunks += split("E-Mail", _header_block(headers) + "\n\n" + _strip_quotes(clean(body)))
    n = 0
    while True:
        att = f"{prefix}__attach_version1.0_#{n:08X}/"
        if not any(e[:1] and "/".join(e).startswith(att.rstrip("/")) for e in ole.listdir(storages=True, streams=False)) and not ole.exists(att.rstrip("/")):
            break
        n += 1
        name = _prop(ole, att, "3707") or _prop(ole, att, "3704") or f"anhang{n}"
        blob = _stream(ole, f"{att}__substg1_0_37010102")
        child = None
        try:
            if blob:
                if len(blob) < opts.min_attachment_image_bytes and Path(name).suffix.lower() in (".png", ".jpg", ".jpeg", ".gif"):
                    continue
                if depth >= opts.max_depth:
                    p.warnings.append(f"attachment „{name}“ not read (nesting too deep)")
                    continue
                child = parse_member(name, blob, depth + 1)
            elif ole.exists(f"{att}__substg1_0_3701000D".rstrip("/")) or any("/".join(e).startswith(f"{att}__substg1_0_3701000D") for e in ole.listdir(storages=True, streams=False)):
                child = msg_from_ole(ole, f"{att}__substg1_0_3701000D/", parse_member, opts, depth + 1)
                name = name or "weitergeleitet.msg"
        except Exception as e:  # noqa: BLE001
            p.warnings.append(f"attachment „{name}“ not read: {str(e)[:140]}")
            continue
        if child is not None:
            p.absorb(child, f"Anhang „{name}“")
            p.meta.setdefault("attachments", []).append(name)
    return p
