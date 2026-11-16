"""Regression contracts for the existing HTML UI without modifying the API."""
from pathlib import Path
import re
import unittest
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
HTML=(ROOT/'web/index.html').read_text(encoding='utf-8')
CSS=(ROOT/'web/fonts/ui-refine.css').read_text(encoding='utf-8')
JS=(ROOT/'web/fonts/ui-refine.js').read_text(encoding='utf-8')
MOTION=(ROOT/'web/fonts/ui-motion.js').read_text(encoding='utf-8')

class Tags(HTMLParser):
    def __init__(self): super().__init__();self.ids=[]
    def handle_starttag(self,tag,attrs):
        self.ids.extend(value for key,value in attrs if key=='id')

class LegacyUIPolish(unittest.TestCase):
    def test_assets_use_existing_static_route(self):
        for path in ['ui-refine.css','ui-refine.js','ui-motion.js']:
            self.assertIn('/fonts/'+path,HTML)
            self.assertTrue((ROOT/'web/fonts'/path).is_file())
    def test_preserves_legacy_api_bindings(self):
        t=Tags();t.feed(HTML)
        self.assertEqual(len(t.ids),len(set(t.ids)))
        for essential in ['model','status','history','new','prompt','send','mic',
                          'agentApprove','agentDiscard','agentPlanOutput','agentEditReview',
                          'workspace','reaEnable','mcpRegister','gitApply','buildPreview',
                          'previewEdit','applyEdit','undoEdit','voiceSelect','liveVoice','saveApiKey']:
            with self.subTest(essential=essential):self.assertIn(essential,t.ids)
    def test_sidebar_is_clean_and_modal_has_tools(self):
        from bs4 import BeautifulSoup
        s=BeautifulSoup(HTML,'html.parser')
        sidebar=s.select_one('.sidebar')
        self.assertIsNone(sidebar.select_one('.manager'))
        self.assertIsNone(sidebar.select_one('#deleteChat'))
        self.assertIsNotNone(s.select_one('#chatMenu #deleteChat'))
        self.assertIsNotNone(s.select_one('#agentPlanCard #agentApprove'))
        self.assertIsNotNone(s.select_one('#settingsModal #buildPreview'))
        self.assertIsNotNone(s.select_one('#settingsModal #reaEnable'))
    def test_colors_motion_and_rtl(self):
        for token in ['#0F1115','#13161B','#191D24','#111419','#2B313B','#F5F7FA','#A7AFBC','#E52235','#F23B4D']:
            self.assertIn(token,CSS)
        self.assertIn('margin-inline',CSS)
        self.assertIn('prefers-reduced-motion',CSS)
        self.assertIn('hoverMs: 180',MOTION)
        self.assertIn('menuStaggerMs: 30',MOTION)
        self.assertIn('aria-live',HTML)
        self.assertIn('lang="ar"',HTML)
    def test_model_approval_and_dialog_accessibility(self):
        self.assertIn('setModel(id)',JS)
        self.assertIn('modalTrap',JS)
        self.assertIn('syncPlanCard',JS)
        self.assertIn('router:plan',JS)
        self.assertNotIn("note.className='fallback-note'",JS)
        self.assertIn('if(m.incomplete)',JS)
        self.assertIn('aria-label',JS)

if __name__=='__main__':unittest.main()
