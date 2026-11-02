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
        self.events, self.rule_events = queue.Queue(), queue.Queue()
        self.closed = self.busy = False
        self.last_error_code = self.poll_id = self.current_future = None
        self.rule_thread = self.rule_result = None
        self.poll_count = self.job_serial = 0
        self.files, self.nodes, self.file_labels, self.node_labels = [], [], [], []
        self.page, self.loaded_node, self.saved_receipt = 1, None, None
        root.title('Clash 配置助手')
        root.geometry(f"680x{min(660, root.winfo_screenheight()-80)}")
        root.minsize(640, 640)
        root.protocol('WM_DELETE_WINDOW', self.close)
        if sys.platform == 'darwin':root.createcommand('tk::mac::Quit', self.close)
        style = ttk.Style(root); style.theme_use('clam')
        font = tkfont.nametofont('TkDefaultFont'); font.configure(size=12 if sys.platform=='darwin' else 11)
        style.configure('.', background='#f5f7fa', foreground='#172033', font=font)
        style.configure('TFrame', background='#f5f7fa')
        style.configure('Card.TFrame', background='#ffffff')
        style.configure('TLabel', background='#f5f7fa')
        style.configure('Card.TLabel', background='#ffffff')
        style.configure('Hint.TLabel', foreground='#526076')
        style.configure('CardHint.TLabel', background='#ffffff', foreground='#526076')
        self.title_font = font.copy(); self.title_font.configure(size=22, weight='bold')
        self.heading_font = font.copy(); self.heading_font.configure(size=14, weight='bold')
        style.configure('Title.TLabel', font=self.title_font)
        style.configure('Heading.TLabel', font=self.heading_font, background='#ffffff')
        style.configure('TButton', padding=(14,9), background='#edf2fa', borderwidth=0,
                        relief='flat',bordercolor='#edf2fa',lightcolor='#edf2fa',darkcolor='#edf2fa')
        style.map('TButton', background=[('active','#dce6f7')],relief=[('pressed','flat'),('active','flat')])
        style.configure('Primary.TButton', background='#2563eb', foreground='#ffffff', borderwidth=0, padding=(20,11))
        style.map('Primary.TButton', background=[('disabled','#dce3ef'),('pressed','#1e40af'),('active','#1d4ed8')], foreground=[('disabled','#637083')])
        style.configure('Quiet.TButton', background='#f5f7fa', borderwidth=0, padding=(8,6), foreground='#2563eb')
        style.configure('TCombobox', padding=7, fieldbackground='#ffffff', arrowsize=16,
                        relief='flat',bordercolor='#cbd5e1',lightcolor='#ffffff',darkcolor='#ffffff')
        style.map('TCombobox', fieldbackground=[('readonly','#ffffff')], foreground=[('readonly','#172033')])
        style.configure('TCheckbutton', padding=(0,5), background='#ffffff')
        style.configure('Thin.Horizontal.TProgressbar',thickness=3,borderwidth=0,
                        troughcolor='#f5f7fa',background='#2563eb',lightcolor='#f5f7fa',darkcolor='#f5f7fa')
        root.configure(background='#f5f7fa')
        shell=ttk.Frame(root,padding=(26,20));shell.pack(fill='both',expand=True)
        top=ttk.Frame(shell);top.pack(fill='x')
        ttk.Label(top,text='Clash 配置助手',style='Title.TLabel').pack(side='left')
        ttk.Button(top,text='帮助',style='Quiet.TButton',command=self.guidance).pack(side='right')
        self.subtitle=tk.StringVar(value='保留你的节点，为 AI 访问生成一份新配置。')
        ttk.Label(shell,textvariable=self.subtitle,style='Hint.TLabel',wraplength=590).pack(anchor='w',pady=(7,18))
        steps=ttk.Frame(shell);steps.pack(fill='x',pady=(0,18))
        self.step_labels=[]
        for i,text in enumerate(('读取配置','核对网络','生成副本'),1):
            label=ttk.Label(steps,text=f'{i}  {text}',padding=(0,5))
            label.pack(side='left',expand=True,fill='x');self.step_labels.append(label)
        self.content=ttk.Frame(shell);self.content.pack(fill='both',expand=True)
        self.pages={i:ttk.Frame(self.content) for i in range(1,5)}
        def card(page):
            item=ttk.Frame(self.pages[page],style='Card.TFrame',padding=18)
            item.pack(fill='x',pady=(0,12));return item
        source=card(1)
        ttk.Label(source,text='先找到你正在使用的配置',style='Heading.TLabel').pack(anchor='w')
        self.file_var=tk.StringVar(value='尚未选择配置文件')
        ttk.Label(source,textvariable=self.file_var,style='Card.TLabel',wraplength=550).pack(anchor='w',pady=(12,7))
        self.file_box=ttk.Combobox(source,textvariable=self.file_var,state='readonly')
        self.file_box.bind('<<ComboboxSelected>>',self.choose_discovered)
        self.source_note=ttk.Label(source,text='工具会先自动查找。没有找到时，选择 Clash 导出的完整配置。',style='CardHint.TLabel',wraplength=550)
        self.source_note.pack(anchor='w')
        links=ttk.Frame(source,style='Card.TFrame');links.pack(fill='x',pady=(10,0))
        self.file_button=ttk.Button(links,text='选择本地文件…',command=self.pick_file)
        self.file_button.pack(side='left')
        self.scan_button=ttk.Button(links,text='重新查找',command=self.scan)
        self.scan_button.pack(side='left',padx=8)
        self.export_help_button=ttk.Button(self.pages[1],text='不知道怎么导出配置？',style='Quiet.TButton',command=self.export_help)
        self.export_help_button.pack(anchor='w')
        self.node_frame=ttk.Frame(self.pages[1],style='Card.TFrame',padding=18)
        ttk.Label(self.node_frame,text='AI 访问使用哪个节点？',style='Heading.TLabel').pack(anchor='w')
        self.node_var=tk.StringVar(value='请先读取配置')
        self.node_box=ttk.Combobox(self.node_frame,textvariable=self.node_var,state='disabled')
        self.node_box.pack(fill='x',pady=(12,8));self.node_box.bind('<<ComboboxSelected>>',lambda _:self.node_changed())
        self.chain_note=ttk.Label(self.node_frame,text='',style='CardHint.TLabel',wraplength=550)
        self.chain_note.pack(anchor='w')
        self.manual={};self.manual_boxes=[];self.site_buttons=[]
        checks=card(2)
        descriptions={'IP':('出口 IP','显示地区与节点预期不符，或无法判断时，选择“需要协助”。'),
                      'DNS':('DNS 解析','出现本地运营商，或无法判断结果时，选择“需要协助”。'),
                      'WebRTC':('浏览器 WebRTC','发现原公网 IP，或无法判断时，选择“需要协助”。')}
        for i,name in enumerate(SITES):
            title,description=descriptions[name]
            row=ttk.Frame(checks,style='Card.TFrame');row.pack(fill='x',pady=(0,16) if i<2 else 0)
            line=ttk.Frame(row,style='Card.TFrame');line.pack(fill='x')
            ttk.Label(line,text=title,style='Heading.TLabel').pack(side='left')
            button=ttk.Button(line,text='打开检测页',command=lambda n=name:self.open_site(n))
            variable=tk.StringVar(value='未检查');self.manual[name]=variable
            combo=ttk.Combobox(line,textvariable=variable,state='readonly',width=9,values=('未检查','未见异常','需要协助'))
            combo.pack(side='right');self.manual_boxes.append(combo)
            button.pack(side='right',padx=8);self.site_buttons.append(button)
            ttk.Label(row,text=description,style='CardHint.TLabel',wraplength=550).pack(anchor='w',pady=(7,0))
        ttk.Label(self.pages[2],text='看不懂结果时，可选择“需要协助”，再继续生成副本。\n这里检查当前连接；新副本导入后，还需要再测一次。',style='Hint.TLabel',wraplength=580).pack(anchor='w')
        summary=card(3)
        ttk.Label(summary,text='核对后，保存一份新配置',style='Heading.TLabel').pack(anchor='w')
        self.preview_node=tk.StringVar();self.preview_checks=tk.StringVar()
        ttk.Label(summary,textvariable=self.preview_node,style='Card.TLabel',wraplength=550).pack(anchor='w',pady=(12,10))
        ttk.Label(summary,text='国内访问直连；AI 与其他国外访问使用所选出口。\n原节点、完整代理链和原文件都会保留。',style='CardHint.TLabel',wraplength=550).pack(anchor='w')
        self.keep=tk.BooleanVar(value=True)
        self.keep_box=ttk.Checkbutton(summary,text='保留原有直连业务（推荐）',variable=self.keep)
        self.keep_box.pack(anchor='w',pady=(10,0))
        ttk.Button(summary,text='查看具体调整',command=self.change_details).pack(anchor='w',pady=(8,0))
        ttk.Label(self.pages[3],textvariable=self.preview_checks,style='Hint.TLabel',wraplength=580).pack(anchor='w',pady=(0,10))
        ttk.Label(self.pages[3],text='保存成功后，由你导入并选择启用。工具不会自动切换配置。',style='Hint.TLabel',wraplength=580).pack(anchor='w')
        saved=card(4)
        ttk.Label(saved,text='新配置已保存',style='Heading.TLabel').pack(anchor='w')
        self.saved_name=tk.StringVar()
        ttk.Label(saved,textvariable=self.saved_name,style='Card.TLabel',wraplength=550).pack(anchor='w',pady=(12,18))
        ttk.Label(saved,text='接下来，在 Clash 中：\n\n1. 导入刚保存的 YAML 文件\n2. 由你选择启用，原配置继续保留\n3. 再次检测 IP、DNS 和 WebRTC',style='Card.TLabel',wraplength=550).pack(anchor='w')
        ttk.Label(saved,textvariable=self.preview_checks,style='CardHint.TLabel',wraplength=550).pack(anchor='w',pady=(14,0))
        ttk.Button(self.pages[4],text='我需要导入帮助',style='Quiet.TButton',command=self.import_help).pack(anchor='w')
        footer=ttk.Frame(shell);footer.pack(fill='x',pady=(12,0))
        progress_slot=ttk.Frame(footer,height=3);progress_slot.pack(fill='x',pady=(0,9));progress_slot.pack_propagate(False)
        self.progress=ttk.Progressbar(progress_slot,mode='determinate',maximum=100,style='Thin.Horizontal.TProgressbar')
        self.status_var=tk.StringVar(value='先读取配置，整个过程不会切换你正在使用的代理。')
        self.status_label=ttk.Label(footer,textvariable=self.status_var,style='Hint.TLabel',wraplength=590)
        self.status_label.pack(anchor='w',pady=(0,12))
        actions=ttk.Frame(footer);actions.pack(fill='x')
        self.back_button=ttk.Button(actions,text='上一步',command=lambda:self.goto(max(1,self.page-1)))
        self.back_button.pack(side='left')
        ttk.Button(actions,text='遇到问题',style='Quiet.TButton',command=self.support_help).pack(side='left',padx=8)
        self.export_button=ttk.Button(actions,text='选择配置文件',style='Primary.TButton',command=self.advance)
        self.export_button.pack(side='right');self.export_button.bind('<Return>',lambda _:(self.advance(),'break')[1])
        self.rule_var=tk.StringVar(value='使用随程序提供的规则')
        self.auto_rules=tk.BooleanVar(value=auto)
        self._menus()
        self.schedule_drain();root.report_callback_exception=self.callback_error
        self.goto(1)
        if initial_config:root.after(120,lambda:self.load(initial_config,probe_runtime=auto))
        elif auto:root.after(120,self.scan)
        if auto:
            try:self.init_rule_client()
            except Exception:self.rule_var.set('暂时不能检查更新，继续使用内置规则')
            root.after(500,self.refresh_rules)

    def _menus(self):
        menu=tk.Menu(self.root);file=tk.Menu(menu,tearoff=False)
        file.add_command(label='选择配置文件…',command=self.pick_file,accelerator='⌘O' if sys.platform=='darwin' else 'Ctrl+O')
        file.add_command(label='生成配置副本…',command=self.generate,accelerator='⌘S' if sys.platform=='darwin' else 'Ctrl+S')
        file.add_separator();file.add_command(label='退出',command=self.close);menu.add_cascade(label='文件',menu=file)
        steps=tk.Menu(menu,tearoff=False)
        for i,label in enumerate(('读取配置','核对网络','生成副本'),1):
            steps.add_command(label=f'{i}. {label}',command=lambda p=i:self.goto(p))
            self.root.bind(f'<Command-Key-{i}>' if sys.platform=='darwin' else f'<Control-Key-{i}>',lambda _,p=i:self.goto(p))
        menu.add_cascade(label='步骤',menu=steps)
        help=tk.Menu(menu,tearoff=False)
        help.add_command(label='使用帮助',command=self.guidance)
        help.add_command(label='版本与更新…',command=self.show_updates)
        help.add_command(label='复制问题摘要',command=self.copy_summary,accelerator='⌘D' if sys.platform=='darwin' else 'Ctrl+D')
        menu.add_cascade(label='帮助',menu=help);self.root.configure(menu=menu)
        for key,callback in (('o',self.pick_file),('s',self.generate),('d',self.copy_summary)):
            self.root.bind(f'<Command-{key}>' if sys.platform=='darwin' else f'<Control-{key}>',lambda _,f=callback:f())

    def ready(self):
        index=selected_index(self.node_box,self.node_var,self.node_labels)
        return (self.service.source is not None and bool((self.service.inspection or {}).get('export_ready'))
                and 0<=index<len(self.nodes) and self.nodes[index]['selectable'])

    def goto(self,page):
        if self.busy:return
        if page in (2,3) and not self.ready():
            self.status_var.set('请先读取完整配置，并确认要使用的出口节点。');return
        self.page=page
        for frame in self.pages.values():frame.pack_forget()
        self.pages[page].pack(fill='both',expand=True)
        for i,label in enumerate(self.step_labels,1):
            text=('读取配置','核对网络','生成副本')[i-1]
            label.configure(text=f'{i}  {text}'+(' · 当前' if i==page else ''),foreground='#2563eb' if i==page else '#526076')
        self.subtitle.set({1:'先确认配置来源，以及 AI 访问使用的节点。',2:'打开网页检查当前连接，再回来记录结果。',3:'保存独立副本，原配置继续保留。',4:'文件已生成；导入与启用仍由你操作。'}[page])
        self.status_var.set({1:'确认配置和节点后，点击“下一步”。' if self.ready() else '请先读取完整配置。',
                             2:'检测后在右侧记录结果；未检查的项目不会被视为通过。',
                             3:'只保存新文件，不自动导入或启用。',4:'导入并启用后，还需要重新检查网络和实际 AI 功能。'}[page])
        if page==3:
            index=selected_index(self.node_box,self.node_var,self.node_labels)
            name=self.nodes[index]['name'];self.preview_node.set('访问出口：'+(name if len(name)<85 else name[:82]+'…'))
            untested=sum(v.get()=='未检查' for v in self.manual.values())
            problems=sum(v.get()=='需要协助' for v in self.manual.values())
            if problems or untested:
                parts=([f'{problems} 项需要协助'] if problems else [])+([f'{untested} 项未检查'] if untested else [])
                self.preview_checks.set('网络核对：'+'，'.join(parts)+'。导入后仍需复测。')
            else:self.preview_checks.set('已记录你的检查结果；导入后还需复测。')
        self.update_actions()
        target=self.site_buttons[0] if page==2 else self.export_button
        self.root.after_idle(target.focus_set)

    def advance(self):
        if self.busy:return
        if self.page==1:
            if not self.service.source or not self.nodes or not (self.service.inspection or {}).get('export_ready'):self.pick_file()
            elif self.ready():self.goto(2);self.status_var.set('按顺序打开检测页，人工核对后记录结果。')
        elif self.page==2:self.goto(3);self.status_var.set('确认调整范围后，点击右下角保存副本。')
        elif self.page==3:self.generate()
        else:self.close()

    def export_help(self):
        messagebox.showinfo('如何取得配置文件','在你当前使用的 Clash 客户端中，找到“配置”页面，导出当前完整配置，或打开配置所在文件夹。\n\n回到这里，选择导出的 YAML／YML／JSON 文件。不要只复制节点名称。\n\n如果客户端只提供订阅链接，或找不到导出入口，请联系交付人员。工具不会替你停用代理。',parent=self.root)

    def import_help(self):
        messagebox.showinfo('导入新配置','在 Clash 的“配置”页面，选择从本地文件导入，找到刚保存的 YAML。\n\n核对节点后，由你选择启用。保留原配置，便于需要时手动选回。\n\n启用后，在日常使用的浏览器重新检测 IP、DNS 和 WebRTC，再尝试实际 AI 功能。遇到异常请联系交付人员。',parent=self.root)

    def change_details(self):
        messagebox.showinfo('这份副本会调整什么','• AI 与普通国外访问统一使用所选出口；国内访问直连。\n• 保留节点账号、完整代理链和原有选择组；勾选时保留原有直连例外。\n• 副本限制普通 UDP，国内视频保留例外。会议、游戏等业务可能需要另行适配。\n• 只在副本中关闭 IPv6；保留原有 DNS 上游。系统与浏览器设置不会被自动修改。\n• 只保存新文件；不会导入、启用或重启当前代理。',parent=self.root)

    def support_help(self):
        messagebox.showinfo('遇到问题怎么处理','读取失败：重新导出完整配置，或选择普通本机目录里的文件。若系统询问文件访问权限，请由你决定是否允许。\n\n检测有问题：保存副本不等于已修复 DNS 或浏览器设置，请联系交付人员。\n\n可从“帮助 → 复制问题摘要”取得脱敏信息。不要把含节点账号的完整配置发到公开聊天。',parent=self.root)

    def show_updates(self):
        window=tk.Toplevel(self.root);window.title('版本与规则更新');window.geometry('480x250')
        window.transient(self.root)
        body=ttk.Frame(window,padding=22);body.pack(fill='both',expand=True)
        ttk.Label(body,text='规则更新',style='Title.TLabel').pack(anchor='w')
        ttk.Label(body,textvariable=self.rule_var,wraplength=430).pack(anchor='w',pady=(14,8))
        ttk.Checkbutton(body,text='自动从 GitHub 更新规则数据',variable=self.auto_rules).pack(anchor='w')
        ttk.Label(body,text='只影响之后生成的副本，不修改已导入的配置。\nGitHub 会看到出口 IP，配置和节点账号不上传。',style='Hint.TLabel',wraplength=430).pack(anchor='w',pady=10)
        ttk.Button(body,text='立即检查',command=lambda:self.refresh_rules(True)).pack(anchor='w')

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
        self.job_serial += 1
        serial = self.job_serial
        self.root.after(8000, lambda: self.slow_notice(serial))
        self.back_button.configure(state='disabled')
        self.progress.configure(mode='indeterminate')
        self.progress.pack(fill='both',expand=True)
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

    def slow_notice(self, serial):
        if not self.closed and self.busy and serial == self.job_serial:
            self.status_var.set('文件处理等待较久。请检查系统是否在询问文件访问权限；遇到问题可查看下方帮助，或退出本工具后换本机目录重试。')

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
                self.progress.configure(mode='determinate', value=0)
                self.progress.pack_forget()
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
                    self.status_var.set(error_message(exc).split(' [', 1)[0])
                    if self.service.source is None:
                        self.file_var.set('读取未完成，请重新选择配置文件')
                        self.node_frame.pack_forget()
                        self.export_help_button.pack(anchor='w')
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
        self.goto(1)
        self.nodes = []; self.node_var.set('先读取配置')
        self.status_var.set('正在只读识别本机配置…')
        self.work(self.service.discover, self.scanned)

    def scanned(self, value):
        self.files = value['candidates']
        labels = [f"{i+1}. {row['client']} · {row['label']}" + (' · 已读取选择记录' if row['active'] else '') for i,row in enumerate(self.files)]
        self.file_labels = labels
        self.file_box.configure(values=labels)
        if not labels:
            self.file_var.set('没有找到可直接读取的配置')
            self.source_note.configure(text='请从你现用的 Clash 导出完整配置，再点击右下角选择文件。')
            self.status_var.set('点击“选择配置文件”继续；不知道如何导出时，可查看上方帮助。')
        else:
            self.file_var.set(f'识别到 {len(labels)} 份配置，请核对来源')
            selected = [i for i, row in enumerate(self.files) if row['active']]
            if len(selected) == 1 or len(self.files) == 1:
                index = selected[0] if selected else 0
                self.file_box.current(index)
                path = self.files[index]['path']
                self.root.after(1, lambda p=path: self.load(p))
            else:
                self.file_box.pack(fill='x',pady=(8,0))
                self.status_var.set('找到多份配置，请在列表中选择你正在使用的那一份。')

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
        self.goto(1)
        for variable in self.manual.values():variable.set('未检查')
        self.loaded_node=None
        self.nodes = []; self.node_var.set('正在读取…')
        self.node_frame.pack_forget()
        self.status_var.set('正在读取文件和已有节点，请稍候…')
        self.work(lambda: self.service.load(path, probe_runtime=probe_runtime), self.loaded)

    def loaded(self, result):
        self.file_var.set(result['file_label'])
        self.file_button.configure(text='更换配置文件…')
        self.nodes = result['inspection']['nodes']
        labels = [f"{i+1}. " + n['name'] + ('（资料不完整）' if not n['selectable'] else
                              '（含中转）' if n['has_chain'] else '') for i,n in enumerate(self.nodes)]
        self.node_labels = labels
        self.node_box.configure(values=labels, state='readonly' if labels else 'disabled')
        self.export_help_button.pack_forget()
        self.node_frame.pack(fill='x',pady=(12,0))
        match = next((i for i, n in enumerate(self.nodes) if n['name'] == result['selected_node']), None)
        if match is not None:
            self.node_box.current(match)
        else:
            self.node_var.set('请选择本次使用的出口节点' if labels else '未取得完整节点，请导出完整配置')
        origin = result['runtime'].get('selection_origin')
        if origin == 'runtime':
            note = '已读取客户端当前的节点选择，请在下方核对。'
        elif origin == 'config-fallback':
            note = '已按文件中的默认出口预选，请与 Clash 当前使用的节点核对。'
        else:
            note = '文件已读取。请选择你在 Clash 中使用的出口节点。'
        self.source_note.configure(text=note)
        self.node_changed()
        warnings = result['inspection']['warnings']
        if not result['inspection']['export_ready']:
            self.status_var.set('这份文件还依赖其他本地文件，暂不能直接生成。请导出完整配置或联系交付人员。')
        elif any(not n['selectable'] for n in self.nodes):
            self.status_var.set('有些节点资料不完整。如果它是你的出口，请重新导出完整配置，不要改选中转节点。')
        else:
            self.status_var.set('读取完成。确认所选节点无误后，点击“下一步”。')

    def node_changed(self):
        index = selected_index(self.node_box, self.node_var, self.node_labels)
        if 0 <= index < len(self.nodes):
            if self.nodes[index]['name'] != self.loaded_node:
                self.service.prepared = None
                for variable in self.manual.values():variable.set('未检查')
                self.loaded_node=self.nodes[index]['name']
            self.chain_note.configure(text='这个节点缺少完整资料，请重新导出配置或联系交付人员。'
                                      if not self.nodes[index]['selectable'] else
                                      '这是含中转的出口；节点账号和完整代理链都会保留。'
                                      if self.nodes[index]['has_chain'] else '将保留这个节点的账号和连接参数。')
        self.update_actions()

    def update_actions(self):
        index = selected_index(self.node_box, self.node_var, self.node_labels)
        ready = (not self.busy and self.service.source is not None
                 and bool((self.service.inspection or {}).get('export_ready'))
                 and 0 <= index < len(self.nodes) and self.nodes[index]['selectable'])
        page=getattr(self,'page',3)
        enabled=ready
        text={1:'下一步：核对网络',2:'下一步：查看副本',3:'生成并保存副本',4:'完成'}[page]
        if page==1 and (self.service.source is None or not self.nodes or not (self.service.inspection or {}).get('export_ready')):
            enabled=not self.busy;text='选择配置文件' if self.service.source is None else '选择完整配置文件'
        if page==4:enabled=not self.busy
        self.export_button.configure(state='normal' if enabled else 'disabled',text=text)
        if hasattr(self,'back_button'):self.back_button.configure(state='normal' if page in (2,3) and not self.busy else 'disabled')

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
        if self.page==1:self.export_help()
        elif self.page==2:messagebox.showinfo('如何核对网络','逐个打开检测页，在你平常访问 AI 的浏览器中运行检测，再回来选择结果。\n\n看不懂或不确定时，选择“需要协助”，由交付人员继续核对。\n\n检测的是当前连接，工具不会切换节点，也不会自动读取检测结果。生成文件不代表问题已修复；导入新副本后，还需要重新检查。',parent=self.root)
        else:self.import_help()

    def copy_summary(self):
        summary = self.service.support_summary(self.last_error_code)
        summary['rule_update'] = self.rule_result
        summary['manual_checks']={name:value.get() if value.get() in ('未检查','未见异常','需要协助') else '未检查'
                                  for name,value in self.manual.items()}
        summary['workflow_step']=self.page
        summary['ui'] = {'busy': self.busy, 'queued_results': self.events.qsize(),
                         'poll_callbacks': self.poll_count,
                         'future_done': self.current_future.done() if self.current_future else None,
                         'node_selection_index': selected_index(self.node_box, self.node_var, self.node_labels)}
        text = json.dumps(summary, ensure_ascii=False, indent=2)
        import claude_setup as c
        import uuid
        c.write_new(self.service.root / ('diagnostic-' + uuid.uuid4().hex + '.json'), text.encode('utf-8'))
        self.root.clipboard_clear(); self.root.clipboard_append(text)
        self.status_var.set('问题摘要已复制，可发给交付人员；不含节点账号、订阅或配置原文。')

    def generate(self):
        if self.busy:return
        if self.page!=3:
            self.goto(3)
            if self.page==3:self.status_var.set('先核对调整范围，再点击“生成并保存副本”。')
            return
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
        manual = {name: {'未检查':'未记录','未见异常':'人工核对未见异常','需要协助':'人工请求协助'}[variable.get()]
                  for name, variable in self.manual.items()}
        self.status_var.set('正在生成和核对新副本，请稍候；当前连接保持不变…')
        def run():
            result = self.service.prepare(node, preserve)
            return self.service.export(destination, manual), result
        def done(value):
            receipt, result = value
            self.saved_receipt=receipt
            self.saved_name.set(Path(receipt['output']).name)
            self.goto(4)
            self.status_var.set('请在原来的 Clash 客户端导入这份副本，并按上方步骤复测。')
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
