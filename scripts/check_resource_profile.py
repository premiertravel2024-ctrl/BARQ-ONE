"""Run the real suite with a simulated host, without changing runtime resource policy.

Examples (from the source root):
  python scripts/check_resource_profile.py --profile low-memory -q
  python scripts/check_resource_profile.py --profile high-memory -q
Tests that provide their own hardware sampler retain that explicit fixture.
"""
import argparse
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    import pytest
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile',required=True,choices=('low-memory','high-memory'))
    args,test_args=parser.parse_known_args()
    from core import adaptive_resources as hardware
    total,free,load=(4*1024**3,512*1024**2,90) if args.profile=='low-memory' else (32*1024**3,16*1024**3,5)

    class SimulatedHost:
        @pytest.hookimpl(tryfirst=True)
        def pytest_runtest_call(self,item):
            patch=item._request.getfixturevalue('monkeypatch')
            patch.setattr(hardware,'_memory_bytes',lambda:(total,free))
            patch.setattr(hardware,'_cpu_percent',lambda cores:load)
            patch.setattr(hardware,'_gpu_devices',lambda:[])
            patch.setattr(hardware.resources,'_last_sample',None)
            patch.setattr(hardware.resources,'_last_sample_at',0.0)

    print(f'Simulated host: {args.profile}, available RAM={free//1024**2} MiB, CPU load={load}%')
    return pytest.main(test_args or ['-q'],plugins=[SimulatedHost()])


if __name__=='__main__':
    raise SystemExit(main())
