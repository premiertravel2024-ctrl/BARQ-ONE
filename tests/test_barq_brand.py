"""Rebrand regression: visible UI identity changes, persistent identifiers must not."""
from pathlib import Path
import struct
import re
import unittest

ROOT=Path(__file__).resolve().parents[1]
read=lambda name:(ROOT/name).read_text(encoding='utf-8')
class BARQBrand(unittest.TestCase):
 def test_original_icon_and_required_assets(self):
  icon=ROOT/'assets/app.ico'
  self.assertTrue(icon.exists())
  self.assertGreaterEqual(struct.unpack_from("<H",icon.read_bytes(),4)[0],7)
  for name in ('brand/barq-mark-dark.png','brand/barq-mark-light.png','favicon.png'):
   self.assertTrue((ROOT/'frontend/public'/name).exists(),name)
   self.assertTrue((ROOT/'web'/name).exists(),name)
 def test_tokens(self):
  for x in ('#0F1115','#191D24','#242A34','#111419','#ffffff13','#f8f7f3','#bcb5bd','#ae2143','#ff728c'):
   self.assertIn(x,read('frontend/src/styles/tokens.css'))
  for x in ('#0F1115','#13161B','#191D24','#111419','#2B313B','#F5F7FA','#A7AFBC','#E52235','#F23B4D'):
   self.assertIn(x,read('web/fonts/ui-refine.css'))
 def test_user_identity_and_keys_must_be_stable(self):
  setup=read('scripts/installer.iss')
  self.assertIn("Result := '{9BB70D04-1EC5-4BC6-B811-64B08F5C8977}'",setup)
  self.assertIn('DefaultDirName={localappdata}\\Programs\\AI Router Agent',setup)
  self.assertIn("'AI Router Agent'",read('core/paths.py'))
  self.assertIn('AI_ROUTER_DATA_DIR',read('core/paths.py'))
  self.assertIn('AppName={#AppName}',setup)
  self.assertIn('OutputBaseFilename=BARQ_Setup_{#AppVersion}',setup)
 def test_visible_application_name(self):
  for path in ('desktop.py','frontend/index.html','frontend/src/components/layout/Sidebar.tsx','frontend/src/i18n/index.ts'):
   self.assertIn('BARQ',read(path))
  self.assertIn("webview.create_window('BARQ'",read('desktop.py'))
  self.assertIn('<title>BARQ</title>',read('frontend/index.html'))
  self.assertIn('<title>BARQ</title>',read('web/index.html'))
 def test_static_asset_route(self):
  from fastapi.testclient import TestClient
  from api import app
  with TestClient(app) as client:
   for name in ('/brand/barq-mark-dark.png','/brand/barq-mark-light.png','/favicon.png'):
    with self.subTest(name=name):self.assertEqual(client.get(name).status_code,200)
 def test_must_not_rename_legacy_store(self):
  # React localStorage and Windows Credential Manager storage intentionally unchanged.
  store=read('frontend/src/store/index.ts')
  self.assertIn('localStorage',store)
  self.assertIn('ai-router',store.lower())
