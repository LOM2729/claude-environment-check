"""One native Tk window. External pages open only after a customer click."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
from pathlib import Path
import queue
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk, filedialog, messagebox
import webbrowser
import json
import re
import threading

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lite.service import Service, SITES, error_message
from lite import rule_updates


def label_index(value, labels):
    """Do not use Tk 9's integer getter for an empty/read-only Combobox."""
    try:
        return labels.index(value)
    except ValueError:
        return -1


def selected_index(widget, variable, labels):
    index = label_index(variable.get(), labels)
    if index >= 0 or not labels:return index
    # Some Tcl/Tk builds keep a typed list representation in StringVar while
    # rendering the correct text. The widget index, if valid, is authoritative.
    try:
        index = widget.current()
        return index if isinstance(index, int) and 0 <= index < len(labels) else -1
    except (AttributeError, TypeError, ValueError, tk.TclError):
        return -1


class Window:
    def __init__(self, root, service=None, initial_config=None, auto=True):
        self.root, self.service = root, service or Service()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.events = queue.Queue()
        self.closed = False
        self.busy = False
        self.last_error_code = None
        self.poll_id = None
        self.poll_count = 0
        self.current_future = None
        self.files, self.nodes = [], []
        self.file_labels, self.node_labels = [], []
        self.rule_events = queue.Queue()
        self.rule_thread = None
        self.rule_result = None
        root.title('Clash 配置助手')
        root.geometry(f"{min(720, root.winfo_screenwidth()-60)}x{min(700, root.winfo_screenheight()-100)}")
        root.minsize(650, 520)
        root.protocol('WM_DELETE_WINDOW', self.close)
        if sys.platform == 'darwin':
            root.createcommand('tk::mac::Quit', self.close)
        style = ttk.Style(root)
        base_font = tkfont.nametofont('TkDefaultFont')
        base_font.configure(size=11 if sys.platform == 'win32' else 12)
        self.title_font = base_font.copy(); self.title_font.configure(size=18, weight='bold')
        style.configure('Title.TLabel', font=self.title_font)
        style.configure('Hint.TLabel', foreground='#4b5563')
        style.configure('TButton', padding=(10, 5))
        style.configure('TCheckbutton', padding=(0, 3))
        self.footer = ttk.Frame(root, padding=(16, 8))
        self.footer.pack(side='bottom', fill='x')
        shell = ttk.Frame(root); shell.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(shell, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(shell, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y'); self.canvas.pack(side='left', fill='both', expand=True)
        body = ttk.Frame(self.canvas, padding=16)
        body_id = self.canvas.create_window((0, 0), window=body, anchor='nw')
        body.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        def resize(event):
            self.canvas.itemconfigure(body_id, width=event.width)
            def walk(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Label):
                        try:length = float(str(child.cget('wraplength') or '0'))
                        except (ValueError, TypeError):length = 0
                        if length > 0:child.configure(wraplength=max(400, event.width - 85))
                    walk(child)
            walk(body)
            walk(self.footer)
        self.canvas.bind('<Configure>', resize)
        def wheel(event):
            if not isinstance(event.widget, (ttk.Combobox, ttk.Entry)):
                delta = event.delta if sys.platform == 'darwin' else event.delta / 120
                if delta:self.canvas.yview_scroll(-int(delta), 'units')
        root.bind('<MouseWheel>', wheel, add=True)
        ttk.Label(body, text='Clash 配置助手', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='沿用已有节点或代理链，另存配置副本。原配置和当前连接不变。',
                  style='Hint.TLabel').pack(anchor='w', pady=(5, 12))
        rule_row = ttk.Frame(body); rule_row.pack(fill='x', pady=(0, 10))
        self.rule_var = tk.StringVar(value='规则库：内置版本')
        ttk.Label(rule_row, textvariable=self.rule_var, style='Hint.TLabel').pack(side='left')
        ttk.Button(rule_row, text='检查规则更新', command=lambda: self.refresh_rules(True)).pack(side='right')
        self.auto_rules = tk.BooleanVar(value=auto)
        ttk.Checkbutton(rule_row, text='自动更新（GitHub）', variable=self.auto_rules).pack(side='right', padx=8)

        config = ttk.LabelFrame(body, text='1. 读取现有配置', padding=10)
        config.pack(fill='x')
        self.file_var = tk.StringVar(value='正在识别本机 Clash 配置…')
        self.file_box = ttk.Combobox(config, textvariable=self.file_var, state='readonly')
        self.file_box.pack(fill='x')
        self.file_box.bind('<<ComboboxSelected>>', self.choose_discovered)
        row = ttk.Frame(config); row.pack(fill='x', pady=(9, 0))
        self.scan_button = ttk.Button(row, text='重新识别', command=self.scan)
        self.scan_button.pack(side='left')
        self.file_button = ttk.Button(row, text='选择配置文件…', command=self.pick_file)
        self.file_button.pack(side='left', padx=8)
        self.source_note = ttk.Label(config, text='只读取本机文件；识别不清时由你选择，不猜当前配置。',
                                     style='Hint.TLabel', wraplength=650)
        self.source_note.pack(anchor='w', pady=(8, 0))
        ttk.Label(config, text='本次使用的出口节点／代理链').pack(anchor='w', pady=(12, 5))
        self.node_var = tk.StringVar(value='先读取配置')
        self.node_box = ttk.Combobox(config, textvariable=self.node_var, state='disabled')
        self.node_box.pack(fill='x')
        self.node_box.bind('<<ComboboxSelected>>', lambda _: self.node_changed())
        self.chain_note = ttk.Label(config, text='', style='Hint.TLabel', wraplength=650)
        self.chain_note.pack(anchor='w', pady=(6, 0))

        checks = ttk.LabelFrame(body, text='2. 在常用浏览器中人工核对', padding=10)
        checks.pack(fill='x', pady=10)
        row = ttk.Frame(checks); row.pack(fill='x')
        self.site_buttons = []
        self.manual = {}; self.manual_boxes = []
        for name in SITES:
            column = ttk.Frame(row); column.pack(side='left', expand=True, fill='x', padx=(0, 8))
            button = ttk.Button(column, text=name + ' 检测', command=lambda n=name: self.open_site(n))
            button.pack(fill='x'); self.site_buttons.append(button)
            variable = tk.StringVar(value='未记录'); self.manual[name] = variable
            combo = ttk.Combobox(column, textvariable=variable, state='readonly', width=17,
                                 values=('未记录', '人工核对未见异常', '人工发现问题'))
            combo.pack(fill='x', pady=(7, 0))
            self.manual_boxes.append(combo)
        ttk.Label(checks, text='点击将在浏览器打开 Net.Coffee，站点会看到出口 IP；配置不上传。请在常用浏览器手动检测并记录。',
                  style='Hint.TLabel', wraplength=650).pack(anchor='w', pady=(9, 0))

        output = ttk.LabelFrame(body, text='3. 生成独立 YAML', padding=10)
        output.pack(fill='x')
        self.keep = tk.BooleanVar(value=True)
        self.keep_box = ttk.Checkbutton(output, text='保留已有直连例外',
                                        variable=self.keep)
        self.keep_box.pack(anchor='w')
        ttk.Label(output, text='副本追加 AI 保护，普通国外与 AI 统一到所选出口；国内直连。\n候选关闭 IPv6 并限制普通 UDP（国内视频例外）；DNS 上游沿用原值。\n节点与链路定义保留；导入前核对会议／游戏等业务，系统及浏览器设置见指引。',
                  style='Hint.TLabel', wraplength=650).pack(anchor='w', pady=(6, 10))
        row = ttk.Frame(self.footer); row.pack(fill='x')
        self.export_button = ttk.Button(row, text='生成并另存 YAML 副本…', command=self.generate, state='disabled')
        self.export_button.pack(side='left')
        ttk.Button(row, text='操作指引', command=self.guidance).pack(side='left', padx=8)
        ttk.Button(row, text='复制异常摘要', command=self.copy_summary).pack(side='left')
        self.progress = ttk.Progressbar(self.footer, mode='indeterminate')
        self.progress.pack(fill='x', pady=(16, 7))
        self.status_var = tk.StringVar(value='只读准备中…')
        self.status_label = ttk.Label(self.footer, textvariable=self.status_var, wraplength=680)
        self.status_label.pack(anchor='w')
        ttk.Label(self.footer, text='仅生成副本 · 不导入、切换或重启当前代理 · 检测结果由客户人工核对',
                  style='Hint.TLabel', wraplength=680).pack(anchor='w', pady=(9, 0))
        self.schedule_drain()
        root.report_callback_exception = self.callback_error
        menu = tk.Menu(root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label='选择配置文件…', command=self.pick_file, accelerator='⌘O' if sys.platform == 'darwin' else 'Ctrl+O')
        file_menu.add_command(label='重新识别', command=self.scan)
        file_menu.add_command(label='生成 YAML 副本…', command=self.generate,
                              accelerator='⌘S' if sys.platform == 'darwin' else 'Ctrl+S')
        file_menu.add_separator(); file_menu.add_command(label='退出', command=self.close)
        menu.add_cascade(label='文件', menu=file_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label='操作指引', command=self.guidance)
        help_menu.add_command(label='复制异常摘要', command=self.copy_summary,
                              accelerator='⌘D' if sys.platform == 'darwin' else 'Ctrl+D')
        help_menu.add_command(label='检查规则更新', command=lambda: self.refresh_rules(True))
        menu.add_cascade(label='帮助', menu=help_menu)
        root.configure(menu=menu)
        root.bind('<Command-o>' if sys.platform == 'darwin' else '<Control-o>', lambda _: self.pick_file())
        root.bind('<Command-s>' if sys.platform == 'darwin' else '<Control-s>', lambda _: self.generate())
        root.bind('<Command-d>' if sys.platform == 'darwin' else '<Control-d>', lambda _: self.copy_summary())
        if initial_config:
            root.after(120, lambda: self.load(initial_config, probe_runtime=auto))
        elif auto:
            root.after(120, self.scan)
        if auto:
            try:self.init_rule_client()
            except Exception:self.rule_var.set('规则库：内置版本（缓存不可用）')
            root.after(500, self.refresh_rules)

    def init_rule_client(self):
        if self.service.rule_client is None:
            self.service.rule_client = rule_updates.Client(self.service.root.parent / 'rule-cache')
        selected = self.service.rule_client.current()
        if selected:
            self.rule_var.set(f'规则：{selected.revision}（缓存）')

    def refresh_rules(self, force=False):
        if self.closed:return
        if not force:
            self.root.after(rule_updates.INTERVAL * 1000, self.refresh_rules)
            if not self.auto_rules.get():return
        if self.rule_thread and self.rule_thread.is_alive():return
        try:
            self.init_rule_client()
        except Exception:
            self.rule_var.set('规则库：内置版本（更新缓存不可用）'); return
        self.rule_var.set('规则：后台检查中…')
        def refresh():
            result = self.service.rule_client.refresh(force)
            self.rule_events.put(result)
        self.rule_thread = threading.Thread(target=refresh, daemon=True)
        self.rule_thread.start()

    def drain_rule_events(self):
        events = getattr(self, 'rule_events', None)
        if events is None:return
        while True:
            try:result = events.get_nowait()
            except queue.Empty:return
            self.rule_result = result
            revision = result.get('revision')
            label = str(revision) if revision is not None else '内置版本'
            suffix = '（新）' if result['status'] == 'updated' else (
                '（继续使用）' if result['status'] == 'kept_previous' else '（已校验）')
            self.rule_var.set('规则：' + label + suffix)

    def work(self, function, complete):
        if self.busy:
            return
        self.busy = True
        self.progress.start(15)
        for widget in (self.scan_button, self.file_button, self.export_button, self.keep_box):
            widget.configure(state='disabled')
        self.file_box.configure(state='disabled'); self.node_box.configure(state='disabled')
        for widget in self.site_buttons + self.manual_boxes:
            widget.configure(state='disabled')
        future = self.pool.submit(function)
        self.current_future = future
        future.add_done_callback(lambda f: self.events.put((f, complete)))
        # Cocoa native modal panels may consume/suspend an older polling
        # callback. Re-arm once after returning from a dialog, not forever add
        # another polling loop or make Tk calls from a background thread.
        self.schedule_drain()

    def schedule_drain(self):
        if self.closed:return
        old = getattr(self, 'poll_id', None)
        if old:
            try:self.root.after_cancel(old)
            except tk.TclError:pass
        self.poll_id = self.root.after(80, self.drain)

    def drain(self):
        self.poll_id = None
        self.poll_count = getattr(self, 'poll_count', 0) + 1
        if self.closed:
            return
        try:
            self.drain_rule_events()
            while True:
                future, complete = self.events.get_nowait()
                self.busy = False; self.progress.stop()
                self.scan_button.configure(state='normal'); self.file_button.configure(state='normal')
                self.keep_box.configure(state='normal')
                self.file_box.configure(state='readonly')
                for widget in self.site_buttons:
                    widget.configure(state='normal')
                for widget in self.manual_boxes:
                    widget.configure(state='readonly')
                self.node_box.configure(state='readonly' if self.nodes else 'disabled')
                try:
                    complete(future.result())
                except Exception as exc:
                    value = str(exc)
                    self.last_error_code = value if re.fullmatch(r'[A-Z][A-Z0-9_]{1,90}', value) else 'LITE_OPERATION_FAILED'
                    self.status_var.set(error_message(exc))
                self.update_actions()
        except queue.Empty:
            pass
        except Exception as exc:
            self.busy = False
            self.callback_error(type(exc), exc, exc.__traceback__)
        finally:
            self.schedule_drain()

    def scan(self):
        if self.busy:return
        self.nodes = []; self.node_var.set('先读取配置')
        self.status_var.set('正在只读识别本机配置…')
        self.work(self.service.discover, self.scanned)

    def scanned(self, value):
        self.files = value['candidates']
        labels = [f"{i+1}. {row['client']} · {row['label']}" + (' · 已读取选择记录' if row['active'] else '') for i,row in enumerate(self.files)]
        self.file_labels = labels
        self.file_box.configure(values=labels)
        if not labels:
            self.file_var.set('未识别到可用 Clash 配置，请选择导出文件')
            self.status_var.set('没有改动任何代理；可点击“选择配置文件”继续。')
        else:
            self.file_var.set(f'识别到 {len(labels)} 份配置，请核对来源')
            selected = [i for i, row in enumerate(self.files) if row['active']]
            if len(selected) == 1 or len(self.files) == 1:
                index = selected[0] if selected else 0
                self.file_box.current(index)
                path = self.files[index]['path']
                self.root.after(1, lambda p=path: self.load(p))
            else:
                self.status_var.set('请选择正确配置；文件新旧时间不作为“正在使用”的证明。')

    def choose_discovered(self, _=None):
        index = selected_index(self.file_box, self.file_var, self.file_labels)
        if 0 <= index < len(self.files):
            self.load(self.files[index]['path'])

    def pick_file(self):
        if self.busy:return
        path = filedialog.askopenfilename(parent=self.root, title='选择 Clash 导出的完整配置',
                    filetypes=(('Clash 配置', ('*.yaml', '*.yml', '*.json')), ('全部文件', '*')))
        if path:
            self.load(path)

    def load(self, path, probe_runtime=True):
        if self.busy:
            self.status_var.set('上一项处理尚未结束，请稍后重新选择文件。'); return
        self.nodes = []; self.node_var.set('正在读取…')
        self.status_var.set('正在读取配置和本机选择信息，不测速、不切换连接…')
        self.work(lambda: self.service.load(path, probe_runtime=probe_runtime), self.loaded)

    def loaded(self, result):
        self.file_var.set(result['file_label'])
        self.nodes = result['inspection']['nodes']
        labels = [f"{i+1}. " + n['name'] + (' 〔链路资料缺失〕' if not n['selectable'] else
                              ' 〔链式〕' if n['has_chain'] else '') for i,n in enumerate(self.nodes)]
        self.node_labels = labels
        self.node_box.configure(values=labels, state='readonly' if labels else 'disabled')
        match = next((i for i, n in enumerate(self.nodes) if n['name'] == result['selected_node']), None)
        if match is not None:
            self.node_box.current(match)
        else:
            self.node_var.set('请选择本次使用的出口节点' if labels else '未取得完整节点，请导出完整配置')
        origin = result['runtime'].get('selection_origin')
        if origin == 'runtime':
            note = '已通过本机只读接口读取选择；仅用于预选，未改变客户端出站。'
        elif origin == 'config-fallback':
            note = '按配置末条路由预选；未验证运行核心实际选择，导入前请核对。'
        else:
            note = '未读取到唯一运行选择。请核对文件和出口，运行采用仍未验证。'
        self.source_note.configure(text=note)
        self.node_changed()
        warnings = result['inspection']['warnings']
        if not result['inspection']['export_ready']:
            self.status_var.set('配置依赖未绑定的本地资源，暂不能导出。请联系交付人员，原配置未改动。')
        elif any(not n['selectable'] for n in self.nodes):
            self.status_var.set('部分节点或链路资料不完整，未自动更换出口。请导出完整配置或联系交付人员。')
        else:
            self.status_var.set('配置读取完成。先核对 IP、DNS、WebRTC，再生成副本。' +
                                (' 原有资源依赖尚未核验，导入后需复测。' if warnings else ''))

    def node_changed(self):
        index = selected_index(self.node_box, self.node_var, self.node_labels)
        if 0 <= index < len(self.nodes):
            if self.nodes[index]['name'] != self.service.selection:
                self.service.prepared = None
            self.chain_note.configure(text='链路资料缺失：暂不能生成，请导出完整配置或联系交付人员。'
                                      if not self.nodes[index]['selectable'] else
                                      '链式出口：保留原节点定义、中转依赖和组成员，不拆链。'
                                      if self.nodes[index]['has_chain'] else '单节点出口；保留原有业务与选择组。')
        self.update_actions()

    def update_actions(self):
        index = selected_index(self.node_box, self.node_var, self.node_labels)
        ready = (not self.busy and self.service.source is not None
                 and bool((self.service.inspection or {}).get('export_ready'))
                 and 0 <= index < len(self.nodes) and self.nodes[index]['selectable'])
        self.export_button.configure(state='normal' if ready else 'disabled')

    def callback_error(self, kind, value, traceback):
        if self.closed:return
        self.last_error_code = 'LITE_UI_OPERATION_FAILED'
        self.status_var.set('操作未完成，请复制异常摘要联系交付人员；当前代理未改变。')
        # Detailed diagnostics remain local and private. Never display a raw
        # Tcl/parser message containing user labels or paths in the interface.
        try:
            import claude_setup as c
            import uuid
            c.write_new(self.service.root / ('ui-error-' + uuid.uuid4().hex + '.txt'),
                        (kind.__name__ + ': ' + str(value)[:2000]).encode('utf-8'))
        except Exception:
            pass

    def open_site(self, name):
        if self.busy:
            return
        try:
            opened = webbrowser.open(SITES[name], new=2)
            self.status_var.set('已请求浏览器打开，请在网页确认并手动记录结果。' if opened else '未能打开浏览器，请手动访问检测地址。')
        except Exception:
            self.status_var.set('未能打开浏览器，请手动访问检测地址；当前代理未改变。')

    def guidance(self):
        messagebox.showinfo('导入与复测指引', '1. 保留原配置，导入新 YAML 后由你自行选择启用。\n2. 如果原配置依赖订阅或地理库，沿用原客户端并核对资源。\n3. 在平常访问 AI 的浏览器复测 IP、DNS 和 WebRTC。\n4. WebRTC 属于浏览器设置，YAML 无法替你修改。按浏览器支持项限制非代理路径，并核对会议功能。\n5. 系统 DNS／IPv6／TUN 调整须先确认影响和原值；工具不会自动操作。\n6. 发现问题可选回原配置并联系交付人员；不要把含凭据的完整配置发到公开聊天。', parent=self.root)

    def copy_summary(self):
        summary = self.service.support_summary(self.last_error_code)
        summary['rule_update'] = self.rule_result
        summary['ui'] = {'busy': self.busy, 'queued_results': self.events.qsize(),
                         'poll_callbacks': self.poll_count,
                         'future_done': self.current_future.done() if self.current_future else None,
                         'node_selection_index': selected_index(self.node_box, self.node_var, self.node_labels)}
        text = json.dumps(summary, ensure_ascii=False, indent=2)
        import claude_setup as c
        import uuid
        c.write_new(self.service.root / ('diagnostic-' + uuid.uuid4().hex + '.json'), text.encode('utf-8'))
        self.root.clipboard_clear(); self.root.clipboard_append(text)
        self.status_var.set('已复制脱敏摘要：只有错误码与数量，不含 IP、节点名称、路径、订阅或凭据。')

    def generate(self):
        if self.busy:return
        index = selected_index(self.node_box, self.node_var, self.node_labels)
        if not 0 <= index < len(self.nodes):
            self.status_var.set('请先明确选择已有的出口节点。'); return
        if not self.nodes[index]['selectable']:
            self.status_var.set('当前节点的链路资料不完整，不会自动改用中转节点。请导出完整配置或联系交付人员。'); return
        filename = 'Clash-优化副本-' + dt.datetime.now().strftime('%Y%m%d-%H%M%S') + '.yaml'
        destination = filedialog.asksaveasfilename(parent=self.root, title='另存新的 YAML 副本（不覆盖）',
                         initialfile=filename, defaultextension='.yaml', filetypes=(('YAML 配置', '*.yaml'),))
        if not destination:
            return
        if Path(destination).exists():
            self.status_var.set('该文件已存在，请另选新文件名；没有覆盖任何文件。'); return
        node, preserve = self.nodes[index]['name'], self.keep.get()
        manual = {name: variable.get() for name, variable in self.manual.items()}
        self.status_var.set('正在生成和核对新副本，请稍候；当前连接保持不变…')
        def run():
            result = self.service.prepare(node, preserve)
            return self.service.export(destination, manual), result
        def done(value):
            receipt, result = value
            self.status_var.set('已生成：' + Path(receipt['output']).name + '。原配置未改；请自行导入后复测，尚未验证运行效果。' +
                                ' 规则：' + str(receipt['rules_revision']) +
                                ('；需沿用原客户端资源。' if result['same_client_required'] else '。'))
        self.work(run, done)

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--config')
    parser.add_argument('--no-auto', action='store_true', help='Do not discover clients or query local controller; useful for synthetic UI checks')
    parser.add_argument('--self-test', action='store_true', help='Synthetic offline frozen-engine check; no UI or client access')
    parser.add_argument('--result', help='New file for the synthetic self-test receipt')
    args = parser.parse_args(argv)
    if args.self_test:
        from lite.smoke import run
        import json
        import claude_setup as c
        try:
            result = run()
        except Exception as exc:
            result = {'ok': False, 'error': error_message(exc), 'proxy_or_system_changes': False}
        if args.result:
            c.write_new(Path(args.result), c.encode(result))
        if sys.stdout is not None:
            print(json.dumps(result, ensure_ascii=True))
        return 0 if result['ok'] else 1
    root = tk.Tk()
    try:
        Window(root, initial_config=args.config, auto=not args.no_auto)
        root.mainloop()
    except Exception as exc:
        messagebox.showerror('无法启动配置助手', error_message(exc), parent=root)
        root.destroy()
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
