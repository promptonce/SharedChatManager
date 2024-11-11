import json
import os
import re
import threading
import sqlite3
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from markdown_it import MarkdownIt
from mdit_py_plugins.amsmath import amsmath_plugin
from mdit_py_plugins.deflist import deflist_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from tkinterweb import HtmlFrame
import requests  # 用于检查 AI API 可访问性

# 如果您使用的是 openai 包，请确保已安装并导入
# import openai

# ====================== 配置相关 ======================
# 获取用户主目录
HOME_DIR = Path.home()
# 定义配置文件路径
CONFIG_FILE = HOME_DIR / ".sharedchat_config.json"
# 默认配置
DEFAULT_CONFIG = {
    "download_directory": "",
    "auto_import": False,
    "enable_ai_rename": False,
    "auto_import_interval": 30000  # 默认时间间隔，单位为毫秒（30秒）
}

def load_config():
    """加载配置文件，如果不存在则创建默认配置。"""
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        # 确保所有默认配置项都存在
        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = value
        return config
    except json.JSONDecodeError:
        messagebox.showerror("配置错误", "配置文件格式错误，将重置为默认配置。")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    except Exception as e:
        messagebox.showerror("配置加载失败", f"无法加载配置文件: {e}")
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """保存配置到配置文件。"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        messagebox.showerror("保存失败", f"无法保存配置文件: {e}")

def open_config_dialog():
    """打开配置对话框，让用户修改设置。"""
    config = load_config()
    dialog = tk.Toplevel(root)
    dialog.title("配置设置")
    dialog.geometry("400x350")
    dialog.resizable(False, False)
    dialog.transient(root)
    dialog.grab_set()

    # 下载目录
    ttk.Label(dialog, text="下载目录:").pack(pady=5, anchor='w', padx=10)
    download_dir_var = tk.StringVar(value=config["download_directory"])
    download_dir_entry = ttk.Entry(dialog, textvariable=download_dir_var, width=50)
    download_dir_entry.pack(pady=5, padx=10, fill=tk.X)

    def browse_directory():
        directory = filedialog.askdirectory(initialdir=download_dir_var.get())
        if directory:
            download_dir_var.set(directory)
    browse_button = ttk.Button(dialog, text="浏览", command=browse_directory)
    browse_button.pack(pady=5, padx=10, anchor='e')

    # 自动导入选项
    auto_import_var = tk.BooleanVar(value=config["auto_import"])
    auto_import_check = ttk.Checkbutton(dialog, text="启用自动导入JSON文件", variable=auto_import_var)
    auto_import_check.pack(pady=5, anchor='w', padx=10)

    # 自动导入时间间隔
    ttk.Label(dialog, text="自动导入时间间隔（秒）:").pack(pady=5, anchor='w', padx=10)
    auto_import_interval_var = tk.StringVar(value=str(int(config["auto_import_interval"] / 1000)))
    auto_import_interval_entry = ttk.Entry(dialog, textvariable=auto_import_interval_var, width=10)
    auto_import_interval_entry.pack(pady=5, padx=10, anchor='w')

    # 启用AI自动重命名选项
    enable_ai_rename_var = tk.BooleanVar(value=config["enable_ai_rename"])
    enable_ai_rename_check = ttk.Checkbutton(dialog, text="启用AI自动重命名", variable=enable_ai_rename_var)
    enable_ai_rename_check.pack(pady=5, anchor='w', padx=10)

    # 按钮框架
    button_frame = ttk.Frame(dialog)
    button_frame.pack(pady=10)

    def on_save():
        new_config = {
            "download_directory": download_dir_var.get(),
            "auto_import": auto_import_var.get(),
            "enable_ai_rename": enable_ai_rename_var.get(),
            "auto_import_interval": int(auto_import_interval_var.get()) * 1000  # 转换为毫秒
        }

        if new_config["enable_ai_rename"]:
            if not check_ai_api_accessible():
                messagebox.showerror("错误", "无法访问AI API，已禁用AI自动重命名选项。")
                new_config["enable_ai_rename"] = False

        save_config(new_config)
        dialog.destroy()
        messagebox.showinfo("配置已保存", "配置已成功保存。")
        update_batch_import_button_text()  # 更新按钮文本
        # 重启自动导入以应用新的时间间隔
        restart_auto_import()
    def on_cancel():
        dialog.destroy()

    save_button = ttk.Button(button_frame, text="保存", command=on_save)
    save_button.pack(side=tk.LEFT, padx=5)
    cancel_button = ttk.Button(button_frame, text="取消", command=on_cancel)
    cancel_button.pack(side=tk.LEFT, padx=5)

def check_ai_api_accessible():
    """检查AI API是否可访问。"""
    try:
        # 假设AI API的ping端点为 'http://localhost:11434/v1/models'
        response = requests.get('http://localhost:11434/v1/models', timeout=5)
        if response.status_code == 200:
            return True
        else:
            return False
    except Exception:
        return False

# ====================== 初始化AI客户端 ======================
# 请确保您已安装并正确配置了 OpenAI 客户端
# 您可以使用 openai 库或其他适合的库
# 以下是根据您提供的代码进行初始化
from openai import OpenAI

client = OpenAI(
    base_url='http://localhost:11434/v1',
    api_key='ollama',  # 必需，但未使用
)

# ====================== 数据库初始化 ======================
def init_db():
    """初始化SQLite数据库并创建必要的表。"""
    try:
        conn = sqlite3.connect('conversations.db')
        cursor = conn.cursor()
        # 创建会话表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                conversation_name TEXT
            )
        ''')
        # 创建消息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT,
                author_role TEXT,
                content TEXT,
                create_time TEXT,
                FOREIGN KEY (conversation_id) REFERENCES conversations (conversation_id)
            )
        ''')
        conn.commit()
        return conn
    except sqlite3.Error as e:
        messagebox.showerror("数据库错误", f"数据库初始化失败: {e}")
        return None

# ====================== Markdown初始化 ======================
md = MarkdownIt().use(dollarmath_plugin).use(amsmath_plugin).use(deflist_plugin).use(tasklists_plugin)

# ====================== 全局变量 ======================
current_html_content = ""
messages_per_page = 10  # 每页显示的消息数量
current_page = 0  # 当前页索引
conversation_collapsed = False  # 是否折叠会话列表
selected_conversation_id = None  # 当前选中的会话ID
search_query = ""  # 搜索查询
is_dark_mode = False  # 是否启用深色模式
# 正则表达式模式，用于匹配默认未命名的会话名称格式
default_name_pattern = r"^messages-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

# ====================== 导入JSON文件 ======================
def import_json(file_path, conn, selected_conversation_id=None, suppress_prompts=False):
    """导入单个JSON文件到数据库。"""
    try:
        root.config(cursor="wait")
        root.update_idletasks()
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cursor = conn.cursor()
        conversation_id = data.get("conversation_id", None)
        if selected_conversation_id:
            # 使用提供的会话ID追加消息
            conversation_id = selected_conversation_id
        if not conversation_id:
            if not suppress_prompts:
                messagebox.showerror("错误", "无法找到有效的会话ID。")
            return
        # 检查会话是否存在
        if conversation_id:
            cursor.execute('SELECT conversation_id FROM conversations WHERE conversation_id=?', (conversation_id,))
            existing_conversation = cursor.fetchone()
            if existing_conversation:
                if not suppress_prompts:
                    messagebox.showinfo("信息", "正在将新消息追加到现有会话。")
            else:
                if not suppress_prompts:
                    conversation_name = simpledialog.askstring("输入", "为此会话输入一个名称:")
                    if not conversation_name:
                        conversation_name = f"Conversation {conversation_id[:8]}"
                else:
                    conversation_name = os.path.splitext(os.path.basename(file_path))[0]
                cursor.execute('''
                    INSERT OR REPLACE INTO conversations (conversation_id, conversation_name)
                    VALUES (?, ?)
                ''', (conversation_id, conversation_name))
        else:
            if not suppress_prompts:
                messagebox.showerror("错误", "无法找到有效的会话ID。")
            return
        # 插入消息
        for message in data.get('messages', []):
            message_id = message.get('id')
            author_role = message.get('author', {}).get('role', '')
            content_parts = message.get('content', {}).get('parts', [])
            content = "\n".join([str(part) if isinstance(part, str) else "[Non-text content]" for part in content_parts])
            create_time = str(message.get('create_time', ''))
            cursor.execute('''
                INSERT OR REPLACE INTO messages (message_id, conversation_id, author_role, content, create_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (message_id, conversation_id, author_role, content, create_time))
        conn.commit()
        if not suppress_prompts:
            messagebox.showinfo("成功", "消息成功追加！")
        load_conversations(conn)
    except Exception as e:
        if not suppress_prompts:
            messagebox.showerror("错误", f"导入失败: {e}")
    finally:
        root.config(cursor="")
        root.update_idletasks()

def batch_import_json():
    """批量导入指定目录下的JSON文件。"""
    config = load_config()
    directory_path = config["download_directory"]
    if directory_path and os.path.isdir(directory_path):
        json_files = [f for f in os.listdir(directory_path) if f.lower().endswith('.json') and os.path.isfile(os.path.join(directory_path, f))]
        if json_files:
            root.config(cursor="wait")
            root.update_idletasks()
            for json_file in json_files:
                file_path = os.path.join(directory_path, json_file)
                import_json(file_path, conn, suppress_prompts=True)
                # 移动到备份文件夹
                move_to_backup(file_path, directory_path)
            root.config(cursor="")
            root.update_idletasks()
            load_conversations(conn)
            # 如果启用了AI自动重命名，则在导入后进行重命名
            if config.get("enable_ai_rename", False):
                ai_automatic_rename()
        else:
            pass  # 没有找到JSON文件，不提示
    else:
        messagebox.showwarning("警告", "请先在配置中设置有效的下载目录。")

def move_to_backup(file_path, directory):
    """将已处理的文件移动到备份文件夹。"""
    backup_folder = os.path.join(directory, "sharedchat_history_backup")
    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)
    try:
        # 如果目标路径有同名文件，直接覆盖
        os.rename(file_path, os.path.join(backup_folder, os.path.basename(file_path)))
    except FileExistsError:
        # 如果文件已存在，先删除再移动
        os.remove(os.path.join(backup_folder, os.path.basename(file_path)))
        os.rename(file_path, os.path.join(backup_folder, os.path.basename(file_path)))
    except Exception as e:
        messagebox.showerror("移动失败", f"无法移动文件 {os.path.basename(file_path)}: {e}")

def select_directory_and_import():
    """根据按钮文本执行相应的操作。"""
    if batch_import_button['text'] == "批量导入JSON":
        # 执行批量导入
        directory_path = filedialog.askdirectory()
        if directory_path:
            config = load_config()
            config['download_directory'] = directory_path
            save_config(config)
            update_batch_import_button_text()
            batch_import_json()
    else:
        # 刷新会话列表
        batch_import_json()

def select_file():
    """选择单个JSON文件并导入。"""
    file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
    if file_path:
        import_json(file_path, conn)

def update_batch_import_button_text():
    """更新批量导入按钮的文本。"""
    config = load_config()
    directory_path = config.get("download_directory", "")
    if directory_path and os.path.isdir(directory_path):
        batch_import_button.config(text="刷新会话列表")
    else:
        batch_import_button.config(text="批量导入JSON")

# ====================== 加载会话和消息 ======================
def load_conversations(conn, search_query=""):
    """从数据库加载会话列表。"""
    try:
        cursor = conn.cursor()
        if search_query:
            cursor.execute('SELECT conversation_id, conversation_name FROM conversations WHERE conversation_name LIKE ?', ('%' + search_query + '%',))
        else:
            cursor.execute('SELECT conversation_id, conversation_name FROM conversations')
        records = cursor.fetchall()
        conversations_listbox.delete(0, tk.END)
        for record in records[::-1]:
            conversations_listbox.insert(tk.END, f"{record[1]} ({record[0]})")
    except sqlite3.Error as e:
        messagebox.showerror("错误", f"加载会话失败: {e}")

def load_messages(conversation_id, conn, page=0):
    """从数据库加载指定会话的消息，并显示在HTML框中。"""
    global current_html_content, selected_conversation_id, is_dark_mode
    offset = page * messages_per_page
    selected_conversation_id = conversation_id
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT author_role, content, create_time FROM messages WHERE conversation_id=? ORDER BY create_time LIMIT ? OFFSET ?', (conversation_id, messages_per_page, offset))
        messages = cursor.fetchall()
        html_content = ""
        for msg in messages:
            author_role, content, create_time = msg
            try:
                create_time_formatted = datetime.fromtimestamp(float(create_time)).strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                create_time_formatted = create_time
            formatted_message = f"""
            <div class="message">
                <div class="author">{author_role}</div>
                <div class="timestamp">{create_time_formatted}</div>
                <div class="content">{md.render(content)}</div>
            </div>
            """
            html_content += formatted_message
        # 更新HTML内容
        if page == 0:
            current_html_content = html_content
        else:
            current_html_content += html_content
        # 定义主题颜色
        if is_dark_mode:
            body_bg_color = "#333"
            text_color = "#fff"
            border_color = "#555"
        else:
            body_bg_color = "#fff"
            text_color = "#000"
            border_color = "#ccc"
        # 构建完整的HTML模板
        html_template = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Conversation Messages</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    padding: 20px;
                    background-color: {body_bg_color};
                    color: {text_color};
                }}
                .message {{
                    margin-bottom: 20px;
                    padding: 10px;
                    border-bottom: 1px solid {border_color};
                }}
                .author {{
                    font-weight: bold;
                }}
                .timestamp {{
                    color: {text_color};
                    font-size: 0.9em;
                }}
                pre {{
                    white-space: pre-wrap;
                }}
            </style>
        </head>
        <body>{current_html_content}</body>
        </html>
        """
        # 显示在HtmlFrame中
        html_view.load_html(html_template)
    except sqlite3.Error as e:
        messagebox.showerror("错误", f"加载消息失败: {e}")

# ====================== 会话选择处理 ======================
def on_select_conversation(event):
    """处理会话列表中的选择事件。"""
    selection = conversations_listbox.curselection()
    if selection:
        conversation = conversations_listbox.get(selection[0])
        conversation_id = conversation.split('(')[-1].strip(')')
        global current_page
        current_page = 0
        load_messages(conversation_id, conn, current_page)

def next_page():
    """加载下一页消息。"""
    global current_page
    current_page += 1
    if selected_conversation_id:
        load_messages(selected_conversation_id, conn, current_page)

# ====================== 保存HTML ======================
def save_html_to_file():
    """将当前HTML内容保存到文件。"""
    file_path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML Files", "*.html")])
    if file_path:
        try:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(current_html_content)
            messagebox.showinfo("成功", f"HTML内容已保存到 {file_path}!")
        except Exception as e:
            messagebox.showerror("错误", f"保存文件失败: {e}")

# ====================== 切换会话列表框架 ======================
def toggle_conversations_frame():
    """折叠或展开会话列表框架。"""
    global conversation_collapsed
    if conversation_collapsed:
        # 使用 add 方法并指定 before 参数将 conversations_frame 插入到 messages_frame 之前
        main_paned_window.add(conversations_frame, before=messages_frame, stretch='always')
        toggle_button.config(text="折叠对话列表")
    else:
        main_paned_window.forget(conversations_frame)
        toggle_button.config(text="展开对话列表")
    conversation_collapsed = not conversation_collapsed


# ====================== 搜索会话 ======================
def search_conversations(event=None):
    """根据搜索查询加载会话列表。"""
    global search_query
    search_query = search_entry.get()
    if search_query == search_hint:
        search_query = ""
    load_conversations(conn, search_query)

# ====================== 右键菜单 ======================
def on_right_click(event):
    """显示右键菜单。"""
    try:
        selection = conversations_listbox.curselection()
        if selection:
            selected_item = conversations_listbox.get(selection[0])
            conversation_id = selected_item.split('(')[-1].strip(')')
            menu = tk.Menu(root, tearoff=0)
            menu.add_command(label="删除", command=lambda: delete_conversation(conversation_id))
            menu.add_command(label="重命名", command=lambda: rename_conversation(conversation_id))
            menu.add_command(label="导入并追加到此会话", command=lambda: import_json(filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")]), conn, selected_conversation_id=conversation_id))
            menu.add_command(label="导入并创建新会话", command=lambda: import_json(filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")]), conn))
            menu.post(event.x_root, event.y_root)
    except tk.TclError:
        pass

def delete_conversation(conversation_id):
    """删除指定会话及其消息。"""
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM conversations WHERE conversation_id=?', (conversation_id,))
        cursor.execute('DELETE FROM messages WHERE conversation_id=?', (conversation_id,))
        conn.commit()
        load_conversations(conn)
        messagebox.showinfo("成功", "会话已成功删除！")
    except sqlite3.Error as e:
        messagebox.showerror("错误", f"删除会话失败: {e}")

def rename_conversation(conversation_id):
    """重命名指定会话。"""
    new_name = simpledialog.askstring("重命名", "请输入新的会话名称:")
    if new_name:
        try:
            cursor = conn.cursor()
            cursor.execute('UPDATE conversations SET conversation_name=? WHERE conversation_id=?', (new_name, conversation_id))
            conn.commit()
            load_conversations(conn)
            messagebox.showinfo("成功", "会话已成功重命名！")
        except sqlite3.Error as e:
            messagebox.showerror("错误", f"重命名会话失败: {e}")

# ====================== 复制会话到剪贴板 ======================
def copy_conversation_to_clipboard():
    """将选定的会话复制到剪贴板。"""
    if not selected_conversation_id:
        messagebox.showwarning("未选择", "请选择一个会话以复制。")
        return
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT author_role, content, create_time FROM messages WHERE conversation_id=? ORDER BY create_time', (selected_conversation_id,))
        messages = cursor.fetchall()
        conversation_text = ""
        for msg in messages:
            author_role, content, create_time = msg
            conversation_text += f"{author_role}: {content}\n"
        if len(conversation_text) <= 8000:
            root.clipboard_clear()
            root.clipboard_append(conversation_text)
            messagebox.showinfo("已复制", "会话已成功复制到剪贴板！")
        else:
            # 分割为8000字符块
            chunks = [conversation_text[i:i+8000] for i in range(0, len(conversation_text), 8000)]
            ChunkCopyPopup(chunks)
    except sqlite3.Error as e:
        messagebox.showerror("错误", f"复制会话失败: {e}")

class ChunkCopyPopup(tk.Toplevel):
    """处理长文本分块复制的弹出窗口。"""
    def __init__(self, chunks):
        super().__init__(root)
        self.attributes("-topmost", True)
        self.title("复制会话块")
        self.geometry("500x300")
        self.chunks = chunks
        self.total_chunks = len(chunks)
        self.current_index = 0
        self.label = ttk.Label(self, text=f"Chunk 1 of {self.total_chunks}")
        self.label.pack(pady=10)
        self.text = tk.Text(self, wrap=tk.WORD, height=10)
        self.text.insert(tk.END, self.chunks[self.current_index])
        self.text.config(state=tk.DISABLED)
        self.text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        buttons_frame = ttk.Frame(self)
        buttons_frame.pack(pady=10)
        self.prev_button = ttk.Button(buttons_frame, text="上一页", command=self.prev_chunk)
        self.prev_button.grid(row=0, column=0, padx=5)
        self.copy_button = ttk.Button(buttons_frame, text="复制", command=self.copy_current_chunk)
        self.copy_button.grid(row=0, column=1, padx=5)
        self.next_button = ttk.Button(buttons_frame, text="下一页", command=self.next_chunk)
        self.next_button.grid(row=0, column=2, padx=5)
        self.update_buttons()

    def copy_current_chunk(self):
        try:
            root.clipboard_clear()
            root.clipboard_append(self.chunks[self.current_index])
            messagebox.showinfo("已复制", f"Chunk {self.current_index+1} 已复制到剪贴板！")
        except Exception as e:
            messagebox.showerror("错误", f"复制失败: {e}")

    def next_chunk(self):
        if self.current_index < self.total_chunks - 1:
            self.current_index += 1
            self.update_content()

    def prev_chunk(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.update_content()

    def update_content(self):
        self.label.config(text=f"Chunk {self.current_index+1} of {self.total_chunks}")
        self.text.config(state=tk.NORMAL)
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, self.chunks[self.current_index])
        self.text.config(state=tk.DISABLED)
        self.update_buttons()

    def update_buttons(self):
        if self.current_index == 0:
            self.prev_button.config(state=tk.DISABLED)
        else:
            self.prev_button.config(state=tk.NORMAL)
        if self.current_index == self.total_chunks - 1:
            self.next_button.config(state=tk.DISABLED)
        else:
            self.next_button.config(state=tk.NORMAL)

# ====================== 切换主题 ======================
def toggle_theme():
    """切换深色模式和浅色模式。"""
    global is_dark_mode
    is_dark_mode = not is_dark_mode
    if selected_conversation_id:
        load_messages(selected_conversation_id, conn, current_page)

# ====================== AI自动重命名 ======================
def ai_automatic_rename():
    """启动AI自动重命名功能。"""
    ai_rename_button.config(state="disabled")
    threading.Thread(target=rename_conversations_in_background, daemon=True).start()

def rename_conversations_in_background():
    """在后台线程中重命名会话。"""
    # 创建一个新的SQLite连接用于线程
    conn_thread = sqlite3.connect('conversations.db')
    cursor_thread = conn_thread.cursor()

    try:
        # 查询所有会话
        cursor_thread.execute("SELECT conversation_id, conversation_name FROM conversations")
        conversations = cursor_thread.fetchall()

        # 过滤出默认未命名的会话
        unamed_conversations = [
            (conversation_id, conversation_name)
            for conversation_id, conversation_name in conversations
            if re.match(default_name_pattern, conversation_name)
        ][::-1]

        if not unamed_conversations:
            # 如果没有未命名的会话，显示提示信息
            msg_box = tk.Toplevel(root)
            msg_box.title("提示")
            msg_box.geometry("300x100")
            label = ttk.Label(msg_box, text="没有需要重命名的会话")
            label.pack(pady=20)
            # 3秒后关闭弹窗
            root.after(3000, msg_box.destroy)
            return

        # 重命名每个符合条件的会话
        for conversation_id, conversation_name in unamed_conversations:
            cursor_thread.execute("""
                SELECT content FROM messages 
                WHERE conversation_id=? AND author_role='user' 
                ORDER BY create_time LIMIT 1
            """, (conversation_id,))
            result = cursor_thread.fetchone()
            if not result:
                continue
            first_user_message = result[0]
            first_user_message = first_user_message[:500]

            prompt = f"请将会话内容'{first_user_message}'整理为一个简洁的标题，不超过10个字。只输出标题，不要添加解释或说明。"

            try:
                response = client.chat.completions.create(
                    model="llama3.2",
                    messages=[
                        {"role": "system", "content": "你是一个帮助重命名会话的助手。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=20
                )
                new_title = response.choices[0].message.content.strip()

                cursor_thread.execute("""
                    UPDATE conversations SET conversation_name=? WHERE conversation_id=?
                """, (new_title, conversation_id))
                conn_thread.commit()

                root.after(0, lambda cid=conversation_id, name=new_title: update_conversation_name_in_list(cid, name))

            except Exception as e:
                # 在弹出窗口中显示错误信息
                error_msg = f"AI重命名失败: {e}"
                root.after(0, lambda msg=error_msg: messagebox.showerror("错误", msg))
                continue

    except sqlite3.Error as e:
        # 在弹出窗口中显示数据库错误
        error_msg = f"数据库操作失败: {e}"
        root.after(0, lambda msg=error_msg: messagebox.showerror("数据库错误", msg))
    finally:
        conn_thread.close()
        root.after(0, lambda: load_conversations(conn, search_query))
        root.after(0, lambda: ai_rename_button.config(state="normal"))

def update_conversation_name_in_list(conversation_id, new_name):
    """更新会话列表中的会话名称。"""
    # 遍历左侧会话列表找到对应的会话并更新其名称
    for index in range(conversations_listbox.size()):
        item_text = conversations_listbox.get(index)
        # 找到对应的会话ID
        if conversation_id in item_text:
            # 更新显示的会话名称
            conversations_listbox.delete(index)
            conversations_listbox.insert(index, f"{new_name} ({conversation_id})")
            break

# ====================== 主程序 ======================
def main():
    """主程序入口。"""
    global conn
    conn = init_db()
    if not conn:
        return
    load_conversations(conn)
    update_batch_import_button_text()  # 更新批量导入按钮的文本
    config = load_config()
    if config["auto_import"]:
        # 启动自动导入线程
        start_auto_import()
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

def on_closing():
    """处理应用关闭事件，确保线程安全关闭。"""
    if messagebox.askokcancel("退出", "您确定要退出吗？"):
        root.destroy()

auto_import_job = None  # 用于保存自动导入的after job ID

def start_auto_import():
    """启动自动导入的定时器。"""
    config = load_config()
    interval = config.get("auto_import_interval", 30000)

    def auto_import():
        batch_import_json()
        global auto_import_job
        auto_import_job = root.after(interval, auto_import)  # 使用配置中的时间间隔
    auto_import()

def restart_auto_import():
    """重新启动自动导入，以应用新的时间间隔。"""
    global auto_import_job
    if auto_import_job:
        root.after_cancel(auto_import_job)
        auto_import_job = None
    start_auto_import()

# ====================== Tkinter界面构建 ======================
# 创建主窗口
root = tk.Tk()
root.title("SharedChat会话管理工具v2.0")
root.geometry("1000x700")

# 创建顶部框架，用于按钮和搜索框
top_frame = ttk.Frame(root)
top_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

# 文件操作按钮框架
file_button_frame = ttk.Frame(top_frame)
file_button_frame.pack(side=tk.TOP, fill=tk.X)

import_button = ttk.Button(file_button_frame, text="导入JSON", command=select_file)
import_button.pack(side=tk.LEFT, padx=2)
batch_import_button = ttk.Button(file_button_frame, text="批量导入JSON", command=select_directory_and_import)
batch_import_button.pack(side=tk.LEFT, padx=2)
save_button = ttk.Button(file_button_frame, text="保存为HTML", command=save_html_to_file)
save_button.pack(side=tk.LEFT, padx=2)
next_page_button = ttk.Button(file_button_frame, text="下一页", command=next_page)
next_page_button.pack(side=tk.LEFT, padx=2)
toggle_button = ttk.Button(file_button_frame, text="折叠对话列表", command=toggle_conversations_frame)
toggle_button.pack(side=tk.LEFT, padx=2)
theme_button = ttk.Button(file_button_frame, text="切换深色/浅色模式", command=toggle_theme)
theme_button.pack(side=tk.LEFT, padx=2)
# 复制到剪贴板按钮
copy_button = ttk.Button(file_button_frame, text="复制到剪贴板", command=copy_conversation_to_clipboard)
copy_button.pack(side=tk.LEFT, padx=2)
# AI自动重命名按钮
ai_rename_button = ttk.Button(file_button_frame, text="AI自动重命名", command=ai_automatic_rename)
ai_rename_button.pack(side=tk.LEFT, padx=2)
# 配置设置按钮
config_button = ttk.Button(file_button_frame, text="配置设置", command=open_config_dialog)
config_button.pack(side=tk.LEFT, padx=2)

# 搜索框框架
search_frame = ttk.Frame(top_frame)
search_frame.pack(side=tk.TOP, fill=tk.X, pady=5)
search_entry = tk.Entry(search_frame)
search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
# 默认搜索提示
search_hint = "请输入搜索关键词"
def set_search_hint():
    if not search_entry.get():
        search_entry.insert(0, search_hint)
        search_entry.config(fg="grey")
def clear_search_hint(event):
    if search_entry.get() == search_hint:
        search_entry.delete(0, tk.END)
        search_entry.config(fg="black")
def restore_search_hint(event):
    if not search_entry.get():
        set_search_hint()
# 绑定事件
search_entry.bind("<FocusIn>", clear_search_hint)
search_entry.bind("<FocusOut>", restore_search_hint)
search_entry.bind('<KeyRelease>', search_conversations)
# 初始化搜索提示
set_search_hint()

# 创建PanedWindow，用于左右布局
main_paned_window = tk.PanedWindow(root, orient=tk.HORIZONTAL)
main_paned_window.pack(fill=tk.BOTH, expand=True)

# 左侧会话列表框架
conversations_frame = tk.Frame(main_paned_window)
main_paned_window.add(conversations_frame, stretch='always')
conversations_listbox = tk.Listbox(
    conversations_frame, font=("Arial", 12), selectbackground="#3399FF",
    selectforeground="white", bg="#F7F9FC", fg="#333", bd=0, highlightthickness=0,
    activestyle="none", relief="flat"
)
conversations_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
conversations_listbox.bind('<<ListboxSelect>>', on_select_conversation)
conversations_listbox.bind('<Button-3>', on_right_click)
# 滚动条
scrollbar_conversations = ttk.Scrollbar(conversations_frame, orient=tk.VERTICAL)
scrollbar_conversations.pack(side=tk.RIGHT, fill=tk.Y)
conversations_listbox.config(yscrollcommand=scrollbar_conversations.set)
scrollbar_conversations.config(command=conversations_listbox.yview)

# 右侧消息显示框架
messages_frame = tk.Frame(main_paned_window)
main_paned_window.add(messages_frame, stretch='always')
html_view = HtmlFrame(messages_frame, horizontal_scrollbar="auto", messages_enabled = False)
html_view.pack(fill="both", expand=True)

# ====================== 启动主程序 ======================
if __name__ == "__main__":
    main()
