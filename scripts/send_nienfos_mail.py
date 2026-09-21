#!/usr/bin/env python3
"""Send Nienfos email through SES and keep an auditable local copy."""

from __future__ import annotations

import argparse
import base64
import configparser
import datetime as dt
import hashlib
import hmac
import mimetypes
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path


DEFAULT_PROFILE = "codex-aws-operator"
DEFAULT_REGION = "us-east-1"
DEFAULT_FROM_ADDRESS = "bjaime@nienfos.com"
DEFAULT_FROM_NAME = "Bruno Jaime | Nienfos"
DEFAULT_BCC = "nienfos.apps@gmail.com"
DEFAULT_SENT_DIR = ".data/sent-mail"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Send an email through Amazon SES SMTP using a local AWS profile. "
            "A .eml copy is saved before every send."
        )
    )
    parser.add_argument("--to", required=True, help="Recipient email address.")
    parser.add_argument("--subject", required=True, help="Email subject.")
    parser.add_argument(
        "--body",
        help="Plain text body. Use '-' to read body from stdin.",
    )
    parser.add_argument(
        "--body-file",
        type=Path,
        help="Path to a UTF-8 plain text body file.",
    )
    parser.add_argument(
        "--attachment",
        action="append",
        type=Path,
        default=[],
        help="Attachment path. Can be passed multiple times.",
    )
    parser.add_argument(
        "--from-address",
        default=DEFAULT_FROM_ADDRESS,
        help=f"Sender address. Default: {DEFAULT_FROM_ADDRESS}",
    )
    parser.add_argument(
        "--from-name",
        default=DEFAULT_FROM_NAME,
        help=f"Sender display name. Default: {DEFAULT_FROM_NAME}",
    )
    parser.add_argument(
        "--reply-to",
        help="Reply-To address. Defaults to --from-address.",
    )
    parser.add_argument(
        "--bcc",
        default=DEFAULT_BCC,
        help=f"BCC archive address. Default: {DEFAULT_BCC}",
    )
    parser.add_argument(
        "--no-bcc",
        action="store_true",
        help="Disable the default BCC archive recipient.",
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        help=f"AWS profile used for SMTP credentials. Default: {DEFAULT_PROFILE}",
    )
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        help=f"SES region. Default: {DEFAULT_REGION}",
    )
    parser.add_argument(
        "--sent-dir",
        type=Path,
        default=Path(DEFAULT_SENT_DIR),
        help=f"Directory for saved .eml copies. Default: {DEFAULT_SENT_DIR}",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Save the .eml copy but do not send.",
    )
    args = parser.parse_args()
    if bool(args.body) == bool(args.body_file):
        parser.error("Provide exactly one of --body or --body-file.")
    return args


def read_body(args: argparse.Namespace) -> str:
    if args.body_file:
        return args.body_file.read_text(encoding="utf-8")
    if args.body == "-":
        return sys.stdin.read()
    return str(args.body)


def ses_smtp_password(secret_access_key: str, region: str) -> str:
    def sign(key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()

    k_date = sign(("AWS4" + secret_access_key).encode("utf-8"), "11111111")
    k_region = sign(k_date, region)
    k_service = sign(k_region, "ses")
    k_terminal = sign(k_service, "aws4_request")
    k_message = sign(k_terminal, "SendRawEmail")
    return base64.b64encode(bytes([0x04]) + k_message).decode("ascii")


def aws_profile_credentials(profile: str) -> tuple[str, str]:
    credentials_path = Path.home() / ".aws" / "credentials"
    config = configparser.ConfigParser()
    config.read(credentials_path)
    if profile not in config:
        raise RuntimeError(f"AWS profile not found in {credentials_path}: {profile}")
    section = config[profile]
    access_key = section.get("aws_access_key_id")
    secret_key = section.get("aws_secret_access_key")
    if not access_key or not secret_key:
        raise RuntimeError(f"AWS profile is missing access keys: {profile}")
    return access_key, secret_key


def attach_file(message: EmailMessage, path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    content_type, _encoding = mimetypes.guess_type(str(path))
    maintype, subtype = (content_type or "application/octet-stream").split("/", 1)
    message.add_attachment(
        path.read_bytes(),
        maintype=maintype,
        subtype=subtype,
        filename=path.name,
    )


def archive_path(sent_dir: Path, subject: str, recipient: str) -> Path:
    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    slug_source = f"{recipient}-{subject}".lower()
    slug = re.sub(r"[^a-z0-9@._-]+", "-", slug_source).strip("-")
    return sent_dir / f"{timestamp}-{slug[:96]}.eml"


def build_message(args: argparse.Namespace) -> EmailMessage:
    body = read_body(args)
    message = EmailMessage()
    message["Subject"] = args.subject
    message["From"] = formataddr((args.from_name, args.from_address))
    message["To"] = args.to
    message["Reply-To"] = args.reply_to or args.from_address
    if args.bcc and not args.no_bcc:
        message["Bcc"] = args.bcc
    message.set_content(body)
    for attachment in args.attachment:
        attach_file(message, attachment)
    return message


def send_message(message: EmailMessage, profile: str, region: str) -> None:
    access_key, secret_key = aws_profile_credentials(profile)
    password = ses_smtp_password(secret_key, region)
    host = f"email-smtp.{region}.amazonaws.com"
    with smtplib.SMTP(host, 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(access_key, password)
        refused = smtp.send_message(message)
    if refused:
        raise RuntimeError(f"Refused recipients: {refused}")


def main() -> int:
    args = parse_args()
    message = build_message(args)
    args.sent_dir.mkdir(parents=True, exist_ok=True)
    saved_path = archive_path(args.sent_dir, args.subject, args.to)
    saved_path.write_bytes(message.as_bytes())
    if args.dry_run:
        print(f"saved={saved_path}")
        print("dry_run=true")
        return 0
    send_message(message, args.profile, args.region)
    print(f"sent_to={args.to}")
    if args.bcc and not args.no_bcc:
        print(f"bcc={args.bcc}")
    print(f"saved={saved_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
