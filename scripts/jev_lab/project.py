#!/usr/bin/env python3
"""Run the lab using the current workspace Secrets panel credentials.

Use the project's .venv Python (python-dotenv is already a backend dependency).
Only the selected provider variables are mapped; .env is never rewritten.
"""
import os
from pathlib import Path

from dotenv import dotenv_values
import lab


def main():
    root=Path(__file__).resolve().parents[2]
    values=dotenv_values(root/'.env')
    # The spelling chosen in the mobile Secrets panel is authoritative.
    key=values.get('OPEN_ROUTER_API_KEY') or values.get('OPENROUTER_API_KEY')
    if key:
        os.environ['OPENROUTER_API_KEY']=key.strip()
    for name in ('TYPESAFE_API_KEY','CLOUDFLARE_API_TOKEN','CLOUDFLARE_ACCOUNT_ID','CLOUDFLARE_AI_GATEWAY_ID'):
        if values.get(name):
            os.environ[name]=values[name].strip()
    return lab.main()


if __name__=='__main__':
    raise SystemExit(main())
