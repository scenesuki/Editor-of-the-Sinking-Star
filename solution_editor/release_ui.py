"""便携启动器和独立备份窗口；耗时文件操作在后台执行。"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
from tkinter import ttk,filedialog,messagebox

from .paths import paths
from .localization import language,set_language,tr
from .release_profile import VERSION


class Window:
    def __init__(self,title,size):
        self.root=tk.Tk();self.root.title(title)
        wanted=[int(v) for v in size.split('x')]
        width=min(wanted[0],max(640,self.root.winfo_screenwidth()-60));height=min(wanted[1],max(460,self.root.winfo_screenheight()-80))
        self.root.geometry(f'{width}x{height}');self.root.minsize(min(700,width),min(460,height))
        self.root.configure(bg='#0b1721');self.labels=[];self.buttons=[];self.future=None
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='save-backup')
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        style=ttk.Style(self.root);self.style=style;style.theme_use('clam')
        family='Microsoft YaHei UI' if language()=='zh-CN' else 'Segoe UI'
        style.configure('.',font=(family,10),background='#0b1721',foreground='#e0edf2')
        style.configure('TEntry',fieldbackground='#18303e',foreground='#e0edf2',padding=7)
        style.configure('TCombobox',fieldbackground='#18303e',foreground='#e0edf2',padding=5)
        style.map('TCombobox',fieldbackground=[('readonly','#18303e')],foreground=[('readonly','#e0edf2')])
        self.root.option_add('*TCombobox*Listbox.background','#18303e');self.root.option_add('*TCombobox*Listbox.foreground','#e0edf2')
        style.configure('TButton',background='#203c4b',foreground='#e0edf2',padding=(12,9))
        style.map('TButton',background=[('disabled','#13232d'),('active','#2d5365')],foreground=[('disabled','#78909b')])
        style.configure('Primary.TButton',background='#53d5bd',foreground='#09221e')
        style.configure('Danger.TButton',foreground='#ffb8b8')
        style.configure('Treeview',fieldbackground='#122735',background='#122735',rowheight=32,foreground='#e0edf2')
        style.configure('Treeview.Heading',background='#203c4b',foreground='#e0edf2',padding=6)
        style.map('Treeview',background=[('selected','#22564f')])
        self.frame=ttk.Frame(self.root,padding=22);self.frame.pack(fill='both',expand=True)
        top=ttk.Frame(self.frame);top.pack(fill='x',pady=(0,18))
        self.title=ttk.Label(top,font=(family,19,'bold'));self.title.pack(side='left')
        self.lang=ttk.Combobox(top,values=['中文','English'],state='readonly',width=12)
        self.lang.set('中文' if language()=='zh-CN' else 'English');self.lang.pack(side='right')
        self.lang.bind('<<ComboboxSelected>>',self.change_language)
        self.status=tk.StringVar(value='');self.status_label=ttk.Label(self.frame,textvariable=self.status,wraplength=760)

    def t(self,ch,en):return ch if language()=='zh-CN' else en
    def label(self,widget,ch,en,property='text'):
        self.labels.append((widget,property,ch,en));widget.configure(**{property:self.t(ch,en)});return widget
    def button(self,parent,ch,en,command,style='TButton'):
        b=ttk.Button(parent,command=command,style=style);self.label(b,ch,en);self.buttons.append(b);return b
    def change_language(self,event=None):
        set_language('zh-CN' if self.lang.get()=='中文' else 'en')
        for widget,prop,ch,en in self.labels:widget.configure(**{prop:self.t(ch,en)})
        family='Microsoft YaHei UI' if language()=='zh-CN' else 'Segoe UI'
        self.style.configure('.',font=(family,10));self.title.configure(font=(family,19,'bold'))
        if hasattr(self,'tree'):self.tree_headers()
        self.root.title(self.t('沉星编辑器 · 预览版','Sinking Star Editor · Preview'))
    def close(self):
        if self.future is not None:
            messagebox.showinfo(self.t('请等待','Please wait'),self.t('文件操作尚未完成，请等待收尾。','A file operation is still running. Wait for it to finish.'),parent=self.root);return
        self.pool.shutdown(wait=False);self.root.destroy()
    def run_job(self,operation,done):
        if self.future is not None:return
        for b in self.buttons:b.state(['disabled'])
        self.lang.configure(state='disabled')
        self.future=self.pool.submit(operation);self.status.set(self.t('处理中，请等待……','Working. Please wait…'))
        def poll():
            if not self.future.done():self.root.after(100,poll);return
            future,self.future=self.future,None
            for b in self.buttons:b.state(['!disabled'])
            self.lang.configure(state='readonly')
            try:result=future.result()
            except Exception as error:
                import traceback
                (paths().logs/'backup-error.log').write_text(traceback.format_exc(),encoding='utf-8')
                self.status.set(self.t('操作失败：','Failed: ')+tr(error))
                messagebox.showerror(self.t('操作未完成','Operation incomplete'),tr(error),parent=self.root)
            else:done(result)
        self.root.after(100,poll)


class BackupWindow(Window):
    def __init__(self):
        super().__init__('Save Backup · Preview','900x700')
        self.label(self.title,'存档备份与恢复','Save Backup & Restore')
        from .save_backup import default_save_root
        try:source=str(default_save_root())
        except OSError:source=''
        settings=paths().config/'backup-preferences.json'
        try:stored=json.loads(settings.read_text(encoding='utf-8'))
        except (OSError,ValueError):stored={}
        self.source=tk.StringVar(value=stored.get('source',source));self.destination=tk.StringVar(value=stored.get('backups',str(paths().backups)))
        for ch,en,var in [('游戏存档目录','Game save directory',self.source),('备份保存目录','Backup destination',self.destination)]:
            self.label(ttk.Label(self.frame),ch,en).pack(anchor='w',pady=(4,6))
            row=ttk.Frame(self.frame);row.pack(fill='x',pady=(0,10))
            ttk.Entry(row,textvariable=var).pack(side='left',fill='x',expand=True)
            self.button(row,'选择…','Browse…',lambda v=var:self.choose(v)).pack(side='right',padx=(10,0))
        self.label(ttk.Label(self.frame,wraplength=810),'关闭游戏与编辑器后使用。恢复会回滚全部战役和该目录内的设置；恢复前自动备份当前版本。',
                   'Close the game and editor. Restore replaces all campaigns and settings in the save folder; the current version is backed up first.').pack(fill='x',pady=(0,12))
        row=ttk.Frame(self.frame);row.pack(fill='x',pady=(0,12))
        self.button(row,'备份全部存档','Back up all saves',self.backup,'Primary.TButton').pack(side='left')
        self.button(row,'刷新列表','Refresh',self.refresh).pack(side='left',padx=8)
        self.button(row,'选择其他备份…','Open another backup…',self.other).pack(side='left')
        body=ttk.Frame(self.frame)
        self.tree=ttk.Treeview(body,columns=('time','source'),show='tree headings',height=7,selectmode='browse')
        self.tree.heading('#0',text='Backup');self.tree.column('#0',width=260)
        self.tree.heading('time',text='UTC');self.tree.column('time',width=180)
        self.tree.heading('source',text='Source');self.tree.column('source',width=330)
        self.tree_headers()
        bar=ttk.Scrollbar(body,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side='left',fill='both',expand=True);bar.pack(side='right',fill='y')
        bottom=ttk.Frame(self.frame)
        self.button(bottom,'恢复所选备份','Restore selected',self.plan_restore,'Danger.TButton').pack(side='left')
        self.button(bottom,'完成上次恢复','Finish pending restore',self.finish_pending).pack(side='left',padx=8)
        self.button(bottom,'打开备份目录','Open backup folder',self.open_destination).pack(side='right')
        # Reserve status/actions before giving the remaining height to the list.
        # English wrapping and Windows scaling must not clip restore controls.
        self.status_label.pack(side='bottom',fill='x')
        bottom.pack(side='bottom',fill='x',pady=14)
        body.pack(fill='both',expand=True);self.refresh()

    def store(self):
        from .save_backup import SaveBackupStore
        return SaveBackupStore(self.destination.get())
    def tree_headers(self):
        for key,ch,en in [('#0','备份','Backup'),('time','时间（UTC）','Time (UTC)'),('source','来源','Source')]:self.tree.heading(key,text=self.t(ch,en))
    def choose(self,var):
        value=filedialog.askdirectory(parent=self.root,initialdir=var.get() or None)
        if value:var.set(value)
    def remember(self):
        from .campaign_project import _publish
        _publish(paths().config/'backup-preferences.json',dict(source=self.source.get(),backups=self.destination.get()))
    def refresh(self):
        if not hasattr(self,'tree'):return
        try:rows=self.store().list()
        except Exception as error:self.status.set(tr(error));return
        self.tree.delete(*self.tree.get_children())
        for row in rows:self.tree.insert('',tk.END,iid=row['path'],text=Path(row['path']).name,values=(row['created'],row['source']))
    def backup(self):
        try:store=self.store();source=self.source.get();self.remember()
        except Exception as error:messagebox.showerror(self.t('操作未完成','Operation incomplete'),tr(error),parent=self.root);return
        self.run_job(lambda:store.backup(source),lambda p:(self.refresh(),self.status.set(self.t('备份已完成：','Backup saved: ')+str(p))))
    def other(self):
        folder=filedialog.askdirectory(parent=self.root)
        if folder:
            try:row=self.store().verify(folder)
            except Exception as error:messagebox.showerror(self.t('操作未完成','Operation incomplete'),tr(error),parent=self.root);return
            if not self.tree.exists(folder):self.tree.insert('',0,iid=folder,text=Path(folder).name,values=(row['created'],row['source']))
            self.tree.selection_set(folder)
    def plan_restore(self):
        selected=self.tree.selection()
        if not selected:self.status.set(self.t('先选择一份备份。','Select a backup first.'));return
        store=self.store();backup=selected[0];target=self.source.get()
        def reviewed(row):
            count=len(row['inventory']['files']);size=sum(r['bytes'] for r in row['inventory']['files'].values())
            text=self.t('将完整恢复以下存档目录：\n','Replace the complete save directory:\n')+target+'\n\n'+row['created']+f'\n{count} files · {size/1048576:.2f} MiB\n\n'
            text+=self.t('当前版本会先备份。后续新增的战役将从当前目录移出。受影响的旧编辑器会话将作废并保留记录。继续？',
                         'The current version will be backed up first. Newer campaigns will be removed from the current directory. Affected editor sessions will be retired and retained. Continue?')
            if messagebox.askyesno(self.t('确认完整恢复','Confirm full restore'),text,icon='warning',parent=self.root):
                self.remember();self.run_job(lambda:store.restore(backup,target,confirmed=True),lambda result:(self.refresh(),self.status.set(self.t('恢复完成；恢复前备份：','Restored. Previous version: ')+result['before']+('\n'+tr(result['warning']) if result.get('warning') else ''))))
            else:self.status.set(self.t('已取消，存档未修改。','Cancelled. Saves were not changed.'))
        self.run_job(lambda:store.verify(backup),reviewed)
    def finish_pending(self):
        store=self.store();self.run_job(store.finish_pending,lambda result:self.status.set(self.t('恢复收尾完成：','Recovery finalized: ')+str(len(result))))
    def open_destination(self):
        p=Path(self.destination.get());p.mkdir(parents=True,exist_ok=True);os.startfile(p)


class Launcher(Window):
    def __init__(self):
        super().__init__('Sinking Star Editor · Preview','760x490')
        self.label(self.title,'沉星编辑器','Sinking Star Editor')
        ttk.Label(self.frame,text=VERSION).pack(anchor='w',pady=(0,16))
        self.label(ttk.Label(self.frame,wraplength=680),'先打开受支持版本的游戏，再加载面板。录制全部使用短按。',
                   'Start a supported game build, then load the panel. Record using short taps only.').pack(fill='x',pady=(0,20))
        self.button(self.frame,'加载游戏内面板','Load in-game panel',self.start,'Primary.TButton').pack(fill='x',pady=5)
        self.button(self.frame,'存档备份与恢复','Save Backup & Restore',self.backup).pack(fill='x',pady=5)
        row=ttk.Frame(self.frame);row.pack(fill='x',pady=8)
        self.button(row,'打开数据目录','Open data folder',lambda:os.startfile(paths().data)).pack(side='left')
        self.button(row,'使用手册','User manual',self.open_manual).pack(side='right')
        self.status_label.pack(fill='x',pady=14);self.child=None
    def open_manual(self):
        layout=paths()
        name='使用细则.md' if language()=='zh-CN' else 'USAGE.en.md'
        manual=layout.app/'docs'/name
        if not getattr(sys,'frozen',False) and not manual.is_file():
            workspace_manual=(layout.workspace or layout.app)/name
            manual=workspace_manual if workspace_manual.is_file() else layout.app/'release/docs'/name
        try:os.startfile(manual)
        except OSError:
            subprocess.Popen(['notepad.exe',str(manual)],creationflags=subprocess.CREATE_NO_WINDOW)
    def backup(self):
        subprocess.Popen([str(paths().app/'SaveBackup.exe')] if getattr(sys,'frozen',False) else [sys.executable,str(paths().app/'release/entry.py'),'--backup'],creationflags=subprocess.CREATE_NO_WINDOW,cwd=paths().app)
    def start(self):
        if self.child is not None and self.child.poll() is None:return
        import uuid
        status=paths().logs/('startup-'+uuid.uuid4().hex+'.json')
        command=([sys.executable] if getattr(sys,'frozen',False) else [sys.executable,str(paths().app/'release/entry.py')])+['--panel','--startup-status',str(status)]
        self.child=subprocess.Popen(command,cwd=paths().app,creationflags=subprocess.CREATE_NO_WINDOW)
        began=time.monotonic();self.status.set(self.t('正在加载，请稍候……','Loading. Please wait…'))
        def poll():
            row={}
            if status.exists():
                try:row=json.loads(status.read_text(encoding='utf-8'))
                except (OSError,ValueError):pass
            if row.get('stage')=='ready':status.unlink(missing_ok=True);self.close();return
            if row.get('stage')=='failed' or self.child.poll() is not None:
                message=tr(row.get('message') or 'See data/logs/launcher-error.log')
                self.status.set(message);messagebox.showerror(self.t('启动失败','Startup failed'),message,parent=self.root);return
            if time.monotonic()-began>20:
                self.status.set(self.t('加载尚未就绪；进程已保留，请查看游戏和 data/logs。','Still loading. The process was kept; check the game and data/logs.'));return
            self.root.after(100,poll)
        self.root.after(100,poll)


def run(backup=False):
    window=BackupWindow() if backup else Launcher();window.root.mainloop()
