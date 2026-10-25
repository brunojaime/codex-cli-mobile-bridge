#!/usr/bin/env python3
"""Store a dedicated lab credential privately; input is never echoed or logged."""
import argparse
import getpass
import os
from pathlib import Path
import re
import tempfile

from lab import DEFAULT_ENV, KEYS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('provider',choices=list(KEYS))
    parser.add_argument('--path',type=Path,default=DEFAULT_ENV)
    args=parser.parse_args()
    path=args.path.expanduser()
    if path.is_symlink():
        raise SystemExit('La configuración no puede ser un enlace simbólico.')
    values={}
    if path.exists():
        if path.stat().st_mode & 0o077:
            raise SystemExit('La configuración existente requiere permisos 600.')
        for line in path.read_text().splitlines():
            key,sep,value=line.partition('=')
            if sep:values[key]=value
    for key in KEYS[args.provider]:
        value=getpass.getpass(key+' (entrada oculta): ').strip()
        if not value or any(c.isspace() for c in value) or not value.isascii():
            raise SystemExit('Valor vacío o con formato inválido. No se guardó ningún cambio.')
        if key=='CLOUDFLARE_ACCOUNT_ID' and not re.fullmatch(r'[a-fA-F0-9]{32}',value):
            raise SystemExit('El ID de cuenta debe tener 32 caracteres hexadecimales.')
        values[key]=value
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.jev-')
    try:
        with os.fdopen(fd,'w') as f:
            f.write(''.join(k+'='+v+'\n' for k,v in values.items()))
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
    print('Configuración privada guardada. Ejecutá lab.py doctor para comprobar presencia; run para verificar acceso.')


if __name__=='__main__':main()
