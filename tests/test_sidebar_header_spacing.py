"""Prevent BARQ sidebar header regressions in the React and fallback interfaces."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class SidebarHeaderSpacing(unittest.TestCase):
    def test_react_brand_uses_dedicated_header(self):
        sidebar=(ROOT/'frontend/src/components/layout/Sidebar.tsx').read_text(encoding='utf-8')
        self.assertIn('sidebar-brand-header',sidebar)
        self.assertIn('sidebar-new-chat-row',sidebar)
        self.assertLess(sidebar.index('sidebar-brand-header'),sidebar.index('sidebar-new-chat-row'))
        self.assertIn('BrandLockup compact={compact}',sidebar)
        self.assertIn('renderBody(false,true)',sidebar)
        self.assertIn('renderBody(collapsed)',sidebar)
        self.assertNotIn('>{body}</motion.aside>',sidebar)

    def test_brand_can_never_shrink_over_new_chat(self):
        css=(ROOT/'frontend/src/styles/global.css').read_text(encoding='utf-8')
        for expected in ('min-height: 84px','sidebar-brand-header','sidebar-new-chat-row',
                         'flex-shrink: 0','border-block-end: 1px solid var(--border-color)'):
            with self.subTest(expected=expected):self.assertIn(expected,css)

    def test_legacy_fallback_is_protected(self):
        css=(ROOT/'web/fonts/ui-refine.css').read_text(encoding='utf-8')
        self.assertIn('.sidebar > .brand',css)
        self.assertIn('min-height:76px!important',css)
        self.assertIn('flex:0 0 44px!important',css)

if __name__=='__main__': unittest.main()
