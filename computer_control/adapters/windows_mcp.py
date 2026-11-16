"""Windows-MCP delegates reviewed GUI actions only, inside BARQ Policy's gate.

No fallback for tool errors: we cannot prove whether an action happened if the
server crashed after clicking. Thus unknown execution state requires reobserve.
"""
from computer_control.adapters.base import OSAdapter
from mcp.windows_client import WindowsMCPClient, BridgeUnavailable

class MCPEnhancedAdapter(OSAdapter):
    def __init__(self, native, bridge=None):
        self.native = native
        self.bridge = bridge or WindowsMCPClient()

    def perceive(self):
        # Native perception already attaches screen signatures and excludes passwords.
        return self.native.perceive()

    def check_abort(self):
        return self.native.check_abort()

    def _point(self,args):
        if args.get('element_id') and not args.get('signature'):
            raise ValueError('UI element signature required before clicking')
        return self.native._point(args)

    @staticmethod
    def _shortcut(keys):
        names = {'ctrl':'Ctrl','control':'Ctrl','alt':'Alt','shift':'Shift','win':'Win',
                 'windows':'Win','esc':'Esc','enter':'Enter','del':'Delete','backspace':'Backspace'}
        if not keys or len(keys) > 4:
            raise ValueError('Invalid shortcut')
        out = [names.get(str(key).lower(), str(key)) for key in keys]
        if any(not k.isascii() or not k.replace('_','').isalnum() for k in out):
            raise ValueError('Unsafe shortcut key')
        return '+'.join(out)

    def _translate(self,tool,args):
        if tool in ('click','double_click','hover'):
            x,y = self._point(args)
            if tool == 'hover':return 'Move', {'loc':[x,y]}
            return 'Click',{'loc':[x,y], 'clicks':2 if tool=='double_click' else 1,
                             'button':str(args.get('button','left'))}
        if tool == 'scroll':
            amount = int(args.get('amount',1))
            if not amount:return None
            return 'Scroll',{'direction':'up' if amount>0 else 'down',
                             'wheel_times':min(20,abs(amount)), 'type':'vertical'}
        if tool == 'drag':
            return 'Move',{'loc':[int(x) for x in args['to']],
                           'from_loc':[int(x) for x in args['from']], 'drag':True}
        if tool in ('type_text','paste'):
            # Type requires a click location; the focused field is not guaranteed
            # to be under the pointer. Keep native focused-element typing.
            return None
        if tool == 'press_key':return 'Shortcut',{'shortcut':self._shortcut([args['key']])}
        if tool == 'hotkey':return 'Shortcut',{'shortcut':self._shortcut(args['keys'])}
        if tool == 'switch_window':return 'Shortcut',{'shortcut':'Alt+Tab'}
        if tool == 'open_app' and args.get('name') and not args.get('appid'):
            return 'App',{'mode':'launch','name':str(args['name'])[:200]}
        return None

    def act(self,tool,args):
        translation = self._translate(tool,args)
        if translation is None:
            return self.native.act(tool,args)
        try:
            return self.bridge.call(*translation)
        except BridgeUnavailable:
            # Only when the bridge declares no action was performed.
            return self.native.act(tool,args)
