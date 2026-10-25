"""Repeat the approved long-form RD edit from its captured frames and saved editorial plan."""
import argparse, json, subprocess, sys
from pathlib import Path
from rd_full_render import ROOT, RECIPE, render
from music import render as mix

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,default=ROOT/'reports/rd-tutorial-completo-20260930')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();folder=args.folder.resolve();output=args.output.resolve()
    if output==folder or folder in output.parents and output.name in ('audio','capture'):
        raise ValueError('Preserve captured source files')
    output.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(Path(__file__).with_name('voice.py')),str(RECIPE),'--output',str(output/'audio')],check=True)
    # The immutable source voice files are validated against the newly resolved cache before rendering.
    from bookends import sha
    narration=json.loads((output/'audio/narration.json').read_text())
    for e in narration['entries']:
        if sha(output/'audio'/e['deliverable'])!=sha(folder/'audio'/e['deliverable']):raise ValueError('Source narration changed')
    render(folder,output/'sin-musica',folder/'pacing-plan.json')
    mix(output/'sin-musica',output/'final',Path(__file__).parent/'skill/local-feature-videos/default-music-plan.json')

if __name__=='__main__':main()
