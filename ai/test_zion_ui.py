#!/usr/bin/env python3
"""Run without phone: python3 ai/test_zion_ui.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from zion_ui import build_command, parse_foreground, validate_target

assert parse_foreground('topResumedActivity=ActivityRecord{abc u0 org.example.chat/.Main t123}') == 'org.example.chat'
assert parse_foreground('mCurrentFocus=Window{abc u0 org.example.chat/org.example.chat.Main}') == 'org.example.chat'
assert parse_foreground('topResumedActivity=unknown') is None
validate_target('org.example.chat', ['org.example.chat'], 'org.example.chat')
for pkg, allowed, foreground in [('org.bad', ['org.good'], 'org.bad'), ('org.good', ['org.good'], 'org.bad'),
                                  ('x; rm -rf /', ['x; rm -rf /'], 'x; rm -rf /')]:
    try: validate_target(pkg, allowed, foreground)
    except (ValueError, PermissionError): pass
    else: raise AssertionError('unsafe target passed')
assert build_command('ui_home', {}) == 'input keyevent KEYCODE_HOME'
assert build_command('ui_back', {}) == 'input keyevent KEYCODE_BACK'
assert build_command('app_open', {'package':'org.example.chat'}).startswith('monkey -p org.example.chat ')
assert 'uiautomator dump' in build_command('ui_tree', {}) and 'trap ' in build_command('ui_tree', {})
assert build_command('ui_tap', {'value':'123,456'}) == 'input tap 123 456'
assert build_command('ui_swipe', {'value':'1,2,300,400,250'}) == 'input swipe 1 2 300 400 250'
assert build_command('ui_text', {'text':'hello; rm -rf /'}) == "input text 'hello;%srm%s-rf%s/'"
for action,args in [('app_open',{'package':'x; id'}), ('ui_tap',{'value':'1; rm,2'}),
                    ('ui_tap',{'value':'99999,1'}), ('ui_swipe',{'value':'1,2,3,4,5'}),
                    ('ui_text',{'text':'bonjour\nrm /'}), ('ui_text',{'text':'é'})]:
    try: build_command(action,args)
    except ValueError: pass
    else: raise AssertionError('unsafe UI argument passed: '+action)
print('zion-ui tests: OK (foreground, package scope, injection, bounds)')
