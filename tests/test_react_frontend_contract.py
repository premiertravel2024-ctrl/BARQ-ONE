"""Static integration contracts only: these tests do not claim browser/UI runtime coverage."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
UI=ROOT/'frontend'

class ReactFrontendContract(unittest.TestCase):
    def test_required_modules(self):
        needed=['package.json','index.html','src/main.tsx','src/App.tsx',
            'src/styles/tokens.css','src/lib/motion.ts','src/lib/mockAI.ts',
            'src/components/ui/Button.tsx','src/pages/Playground.tsx',
            'src/components/chat/Message.tsx','src/components/layout/Sidebar.tsx']
        for name in needed:
            with self.subTest(name=name):self.assertTrue((UI/name).is_file())
    def test_button_states_and_reduced_motion(self):
        button=(UI/'src/components/ui/Button.tsx').read_text(encoding='utf-8')
        for piece in ['useReducedMotion','whileHover','whileTap','focus-visible','ripples','shineKey',"'loading'","'success'","'error'","'danger'","'pill'","magnetic"]:
            with self.subTest(piece=piece):self.assertIn(piece,button)
    def test_both_palettes_and_type(self):
        css=(UI/'src/styles/tokens.css').read_text(encoding='utf-8')
        for piece in ['#100D14','#18121D','#221925','#120E17','#362A3A','#FCF3F8','#BFB1C2','#AC3159','#F0779F','#F8F4F6','#FFFFFF','#F1E8EE']:
            with self.subTest(piece=piece):self.assertIn(piece,css)
    def test_python_fallback_serving(self):
        api=(ROOT/'api.py').read_text(encoding='utf-8')
        self.assertIn('react_dist',api)
        self.assertIn("@app.get('/playground')",api)
        self.assertIn("resource('web','index.html')",api)
    def test_windows_pipeline_builds_react_first(self):
        script=(ROOT/'scripts/build_windows.ps1').read_text(encoding='utf-8')
        # Inspect the executed build steps, not comments naming PyInstaller.
        react = "Invoke-Step 'Type-checking and building React UI' { npm run build }"
        package = "Invoke-Step 'Packaging native Windows .exe with Python + React' { & $python @pyArgs }"
        self.assertIn(react, script)
        self.assertIn(package, script)
        self.assertLess(script.index(react), script.index(package))
        self.assertIn('web/react/index.html',script)
    def test_model_calls_not_faked_as_real(self):
        mock=(UI/'src/lib/mockAI.ts').read_text(encoding='utf-8')
        self.assertIn('simulated response',mock.lower())
        self.assertIn('AbortSignal',mock)
        self.assertIn('async *stream',mock)

if __name__=='__main__':unittest.main()
