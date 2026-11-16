"""Build gate for packaged native agent support; no screenshots/mic/network."""
from pathlib import Path
import importlib.util
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


def check(spec=importlib.util.find_spec,root=ROOT):
    required=('mss','PIL','pyautogui','pywinauto','psutil','pyperclip','send2trash','sherpa_onnx','winsdk')
    missing=[name for name in required if spec(name) is None]
    if not (root/'scripts/read_screen_ocr.ps1').is_file():missing.append('read_screen_ocr.ps1')
    if not (root/'models/speaker/wespeaker_en_voxceleb_resnet34_LM.onnx').is_file():missing.append('speaker model')
    return missing

if __name__=='__main__':
    problems=check()
    if problems:
        print('BARQ native agent dependencies missing: '+', '.join(problems),file=sys.stderr)
        raise SystemExit(2)
    print('BARQ agent runtime dependencies and local OCR helper available. Actual screen/audio permissions still require device testing.')
