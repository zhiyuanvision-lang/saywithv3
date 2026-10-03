#!/usr/bin/env python3
"""Download pending SayWith feedback and prepend to support.md.

Matches the admin 「一键导出待处理」 button: fetch open tickets, write new
ones to support.md (with ---- divider), download screenshots, optionally
close the exported tickets.

    make feedback
    python3 scripts/extract-open-feedback.py --from-tengxun --close
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import ssl
import subprocess
import sys
import shlex
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "tmp" / "feedback-inbox"
DEFAULT_MD = REPO / "support.md"
DEFAULT_API = "https://api.saywith.zhiyuanv.com"
DEFAULT_ENV = REPO / ".env"


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def first_env(*keys: str, file_vals: dict[str, str] | None = None) -> str:
    for key in keys:
        raw = os.environ.get(key, "").strip()
        if raw:
            return raw
    file_vals = file_vals or {}
    for key in keys:
        raw = (file_vals.get(key) or "").strip()
        if raw:
            return raw
    return ""


def token_from_tengxun(host: str, env_path: str) -> str:
    script = (
        f"sudo grep -E '^(export[[:space:]]+)?ADMIN_TOKEN=' {shlex.quote(env_path)} | tail -n1"
    )
    proc = subprocess.run(
        ["ssh", "-q", host, script],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "ssh failed").strip()
        raise SystemExit(f"无法从 {host} 读取管理员令牌：{err}")
    line = proc.stdout.strip()
    if "=" not in line:
        raise SystemExit(f"{host} 上的 {env_path} 没有 ADMIN_TOKEN")
    value = line.split("=", 1)[1].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    if not value:
        raise SystemExit(f"{host} 上的 ADMIN_TOKEN 为空")
    return value


def http_json(
    method: str,
    url: str,
    token: str = "",
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["X-Admin-Token"] = token
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            detail = str(parsed.get("error") or detail)
        except json.JSONDecodeError:
            detail = detail[:200]
        raise SystemExit(f"{method} {url} → HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"{method} {url} 失败：{exc.reason}") from exc
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def http_bytes(url: str, timeout: int = 30) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"Accept": "*/*"})
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read(), resp.headers.get_content_type() or ""


def login(api: str, phone: str, password: str) -> str:
    body = http_json(
        "POST",
        urljoin(api.rstrip("/") + "/", "v1/admin/login"),
        body={"phone": phone, "password": password},
    )
    token = str(body.get("token") or "").strip()
    if not token:
        raise SystemExit("登录成功但没有返回 token")
    return token


def resolve_auth(args: argparse.Namespace, file_vals: dict[str, str]) -> str:
    token = (args.token or "").strip() or first_env(
        "SAYWITH_ADMIN_TOKEN", "ADMIN_TOKEN", file_vals=file_vals
    )
    if args.from_tengxun:
        token = token_from_tengxun(args.ssh_host, args.remote_env)
    if token:
        return token
    phone = (args.phone or "").strip() or first_env(
        "SAYWITH_ADMIN_PHONE", "ADMIN_PHONE", file_vals=file_vals
    )
    password = args.password or first_env(
        "SAYWITH_ADMIN_PASSWORD", "ADMIN_PASSWORD", file_vals=file_vals
    )
    if phone and not password and sys.stdin.isatty():
        password = getpass.getpass(f"管理员 {phone} 的密码：")
    if phone and password:
        return login(args.api, phone, password)
    raise SystemExit(
        "缺少管理员凭证。任选其一：\n"
        "  1. python3 scripts/extract-open-feedback.py --from-tengxun\n"
        "  2. 设置 ADMIN_PHONE + ADMIN_PASSWORD（或 SAYWITH_ADMIN_*）\n"
        "  3. 设置 ADMIN_TOKEN / SAYWITH_ADMIN_TOKEN"
    )


def collect_images(ticket: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in ticket.get("images") or []:
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    for msg in ticket.get("messages") or []:
        for url in msg.get("images") or []:
            if url and url not in seen:
                seen.add(url)
                out.append(url)
    return out


def ticket_text(ticket: dict[str, Any]) -> str:
    texts: list[str] = []
    seen: set[str] = set()
    for msg in ticket.get("messages") or []:
        if msg.get("sender_type") == "support":
            continue
        body = (msg.get("content") or "").strip()
        if body and body not in seen:
            seen.add(body)
            texts.append(body)
    if not texts:
        body = (ticket.get("content") or "").strip()
        if body:
            texts.append(body)
    return "\n\n".join(texts)


def format_entry(index: int, image_paths: list[str], text: str) -> str:
    paths = [p for p in image_paths if p]
    body = (text or "").strip()
    body_lines = [f"  {line}" for line in body.splitlines()] if body else []
    if paths:
        lines = [f"{index}. {paths[0]}"]
        lines.extend(f"   {p}" for p in paths[1:])
        lines.extend(body_lines)
    elif body_lines:
        lines = [f"{index}."]
        lines.extend(body_lines)
    else:
        return ""
    return "\n".join(lines) + "\n"


TICKET_PATH_RE = re.compile(r"tmp/feedback-inbox/([0-9a-fA-F]+)/")


def existing_ticket_ids(md: str) -> set[str]:
    return {m.group(1).lower() for m in TICKET_PATH_RE.finditer(md)} | set(re.findall(r"<!-- feedback:([0-9a-fA-F]+) -->",md))


def next_index(existing: str) -> int:
    last = 0
    for line in existing.splitlines():
        match = re.match(r"^(\d+)\.\s", line)
        if match:
            last = max(last, int(match.group(1)))
    return last + 1


def image_abs(api: str, url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(api.rstrip("/") + "/", url.lstrip("/"))


def ext_for(content_type: str, data: bytes) -> str:
    if "png" in content_type or data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if "webp" in content_type or data[:4] == b"RIFF":
        return ".webp"
    if "gif" in content_type or data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".jpg"


def relpath(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return str(path.resolve())


def download_images(
    api: str, ticket: dict[str, Any], dest: Path
) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for i, url in enumerate(collect_images(ticket), start=1):
        data, ctype = http_bytes(image_abs(api, url))
        path = dest / f"{i:02d}{ext_for(ctype, data)}"
        path.write_bytes(data)
        saved.append(path)
    return saved


def prepend_support_md(path: Path, block: str, *, divider: bool = False) -> None:
    if not block.strip():
        return
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=path.parent,delete=False) as file:
            temporary = Path(file.name)
            file.write(join_support_prepend(existing,block,divider))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary,path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def join_support_prepend(existing: str, block: str, divider: bool = False) -> str:
    if not block:
        return existing or ""
    if not existing.strip():
        return block
    separator = "\n\n----\n\n" if divider else "\n\n"
    return block.rstrip("\n") + separator + existing



def copy_clipboard(text: str) -> bool:
    if not text:
        return False
    try:
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def close_ticket(api: str, token: str, ticket_id: str) -> None:
    http_json(
        "PATCH",
        f"{api}/v1/admin/feedback/{ticket_id}?product=saywith",
        token=token,
        body={"status": "closed"},
    )


def close_tickets(api: str, token: str, ticket_ids: list[str]) -> int:
    closed = 0
    for tid in ticket_ids:
        if not tid:
            continue
        close_ticket(api, token, tid)
        closed += 1
    return closed


def extract(args: argparse.Namespace) -> tuple[Path, str, int, int, list[str]]:
    file_vals = parse_env_file(Path(args.env_file)) if args.env_file else {}
    token = resolve_auth(args, file_vals)
    api = args.api.rstrip("/")
    query = f"status={args.status}&page_size={args.page_size}&product=saywith"
    listing = http_json("GET", f"{api}/v1/admin/feedback?{query}", token=token)
    items = listing.get("items") or []
    if len(items) == args.page_size:
        print("后台列表可能超过本次导出上限；可使用 --id 指定工单。",file=sys.stderr)
    if args.id:
        items = [x for x in items if x.get("id") == args.id]
        if not items:
            items = [{"id": args.id}]

    ticket_ids = [str(head.get("id") or "") for head in items if head.get("id")]
    if not ticket_ids:
        return Path(args.md).resolve(), "", 0, 0, []

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = Path(args.md).resolve()

    existing = md_path.read_text(encoding="utf-8") if md_path.is_file() else ""
    index = next_index(existing)
    seen = existing_ticket_ids(existing)
    entries: list[str] = []
    for head in items:
        tid = str(head.get("id") or "")
        if not tid or tid.lower() in seen:
            continue
        ticket = http_json(
            "GET", f"{api}/v1/admin/feedback/{tid}?product=saywith", token=token
        )
        dest = out_dir / tid
        saved = download_images(api, ticket, dest)
        entry = format_entry(index, [relpath(p) for p in saved], ticket_text(ticket))
        if entry:
            entry += f"<!-- feedback:{tid.lower()} -->\n"
        if entry:
            entries.append(entry)
            seen.add(tid.lower())
            index += 1

    block = "\n".join(entries)
    if entries:
        prepend_support_md(md_path, block, divider=True)

    closed = 0
    if args.close and ticket_ids:
        # Close only tickets whose content was durably exported, including earlier runs.
        persisted = existing_ticket_ids(md_path.read_text(encoding="utf-8")) if md_path.exists() else set()
        closed = close_tickets(api, token, [tid for tid in ticket_ids if tid.lower() in persisted])

    return md_path, block, len(entries), closed, ticket_ids


def self_test() -> None:
    ticket = {
        "content": "选义闯关太简单",
        "images": ["/v1/feedback/images/aaa"],
        "messages": [
            {
                "sender_type": "user",
                "content": "选义闯关太简单",
                "images": ["/v1/feedback/images/aaa"],
            },
            {"sender_type": "support", "content": "已收到"},
        ],
    }
    assert ticket_text(ticket) == "选义闯关太简单"
    assert "已收到" not in ticket_text(ticket)
    entry = format_entry(1, ["tmp/feedback-inbox/abcd/01.jpg"], ticket_text(ticket))
    assert entry == "1. tmp/feedback-inbox/abcd/01.jpg\n  选义闯关太简单\n"
    two = format_entry(
        2,
        ["tmp/a/01.jpg", "tmp/a/02.jpg"],
        "第一行\n第二行",
    )
    assert two == "2. tmp/a/01.jpg\n   tmp/a/02.jpg\n  第一行\n  第二行\n"
    assert next_index(entry + "\n" + two) == 3
    assert existing_ticket_ids(entry) == {"abcd"}
    assert "工单" not in entry
    assert "请根据" not in entry
    divided = join_support_prepend(
        "117. tmp/feedback-inbox/aaa/01.jpg\n  旧内容\n",
        "118. tmp/feedback-inbox/bbb/01.jpg\n  新内容\n",
        True,
    )
    assert divided == (
        "118. tmp/feedback-inbox/bbb/01.jpg\n  新内容\n\n"
        "----\n\n"
        "117. tmp/feedback-inbox/aaa/01.jpg\n  旧内容\n"
    )
    assert join_support_prepend("", "1. foo\n", True) == "1. foo\n"
    assert "---" not in join_support_prepend("1. foo\n  bar\n", "2. baz\n", False)
    print("self-test ok")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--api", default=os.environ.get("SAYWITH_API", DEFAULT_API))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--md", default=str(DEFAULT_MD))
    parser.add_argument("--status", default="open")
    parser.add_argument("--page-size", type=int, choices=range(1,501), default=500)
    parser.add_argument("--id", help="只抽这一条工单")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--token", default="")
    parser.add_argument("--phone", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--from-tengxun", action="store_true")
    parser.add_argument(
        "--close",
        action="store_true",
        help="导出后关闭这批待处理工单（与后台「一键导出待处理」一致）",
    )
    parser.add_argument("--ssh-host", default="tengxun")
    parser.add_argument("--remote-env", default="/opt/saywith/.env")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    md_path, block, n, closed, ticket_ids = extract(args)
    if not ticket_ids:
        print("没有待处理意见反馈")
        return
    copied = copy_clipboard(block)
    if n:
        msg = f"已写入 support.md（{n} 条新反馈）"
    else:
        msg = "这些待处理已经在 support.md 里"
    if args.close:
        msg += f"，已关闭 {closed} 条"
    msg += "，截图在 ./tmp/feedback-inbox"
    print(msg)
    if n:
        print(f"已在 {md_path} 开头插入 {n} 条")
    if copied and block:
        print("新增内容已复制到剪贴板，可直接粘贴。")


if __name__ == "__main__":
    main()
