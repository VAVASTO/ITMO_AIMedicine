"""Reproduce the pinned Synthea pilot; refuse overwriting an existing output."""
import argparse
import hashlib
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAR_SHA='20098ec70c24c715ea874b19140983634711cc4986196105b5b0a9ca72a4b644'


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--java',default='java')
    p.add_argument('--jar',type=Path,default=ROOT/'.cache/tools/synthea-with-dependencies.jar')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if hashlib.sha256(a.jar.read_bytes()).hexdigest()!=JAR_SHA:raise SystemExit('Generator checksum differs from the recorded experiment.')
    if a.output.exists():raise SystemExit('Output exists; choose a new private directory.')
    a.output.mkdir(parents=True)
    cmd=[a.java,'-Xmx2g','-jar',str(a.jar.resolve()),'-s','20261108','-cs','20261108','-r','20261108','-p','100','-a','35-85',
         '--exporter.baseDirectory='+str(a.output.resolve()),'--exporter.csv.export=true','--exporter.fhir.export=false',
         '--exporter.hospital.fhir.export=false','--exporter.practitioner.fhir.export=false','--generate.thread_pool_size=1']
    with (a.output/'generation.log').open('w') as f:subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
    print('Synthetic population generated. Keep the raw export private; import only the normalized fields.')


if __name__=='__main__':main()
