"""Isolated Playwright Chromium session (same worker thread for every action).

No browser profile/cookies from the user's browser are read. Requires
`python -m playwright install chromium` on the Windows machine.
"""
from pathlib import Path
class Browser:
    def __init__(self):self.playwright=None;self.browser=None;self.page=None
    def _init(self,url):
        if self.playwright is None:
            from playwright.sync_api import sync_playwright
            self.playwright=sync_playwright().start()
            self.browser=self.playwright.chromium.launch(headless=False)
            self.page=self.browser.new_page(accept_downloads=True)
        if self.page.url!=url:self.page.goto(url,wait_until='domcontentloaded',timeout=25000)
        return self.page
    def fill(self,url,selector,value):
        page=self._init(url)
        page.locator(selector).first.fill(value[:10000],timeout=10000)
        return {'filled':selector,'url':page.url,'submitted':False}
    def submit(self,url,selector):
        page=self._init(url);page.locator(selector).first.click(timeout=10000)
        return {'clicked':selector,'url':page.url,'submission_attempted':True}
    def download(self,url,selector,path):
        dest=Path(path).expanduser().resolve()
        if dest.exists():raise FileExistsError('Download target already exists')
        page=self._init(url)
        with page.expect_download(timeout=25000) as info:page.locator(selector).first.click(timeout=10000)
        item=info.value;item.save_as(str(dest))
        return {'downloaded':str(dest),'source_url':url}
    def close(self):
        if self.browser:self.browser.close()
        if self.playwright:self.playwright.stop()
