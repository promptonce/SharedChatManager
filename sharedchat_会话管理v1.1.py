import sqlite3
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
import os
import markdown2
from datetime import datetime
from tkinterweb import HtmlFrame
import threading

# Declare global variable to store HTML content and pagination
current_html_content = ""
messages_per_page = 5  # Number of messages to load per page, reducing it to prevent lag
current_page = 0        # Current page index
conversation_collapsed = False  # Track if conversation list is collapsed
selected_conversation_id = None  # Track currently selected conversation
search_query = ""  # Store the search query
is_dark_mode = False  # Track the current theme (False for light mode, True for dark mode)

# 初始化SQLite数据库
def init_db():
    try:
        conn = sqlite3.connect('conversations.db')
        global cursor
        cursor = conn.cursor()

        # 创建数据库表，添加 conversation_name 字段
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                conversation_name TEXT
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT,
                author_role TEXT,
                content TEXT,
                create_time TEXT,
                FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
            )
        ''')

        conn.commit()
        return conn
    except sqlite3.Error as e:
        messagebox.showerror("Error", f"Database initialization failed: {e}")

# 从JSON文件导入数据
def import_json(file_path, conn):
    try:
        # 禁用窗口上的组件以防止交互干扰
        root.config(cursor="wait")
        root.update_idletasks()

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        cursor = conn.cursor()
        conversation_id = data["conversation_id"]

        # 提示用户输入对话名称
        conversation_name = simpledialog.askstring("Input", "Enter a name for this conversation:")
        if not conversation_name:
            conversation_name = f"Conversation {conversation_id[:8]}"

        cursor.execute('''
            INSERT OR REPLACE INTO conversations (conversation_id, conversation_name)
            VALUES (?, ?)
        ''', (conversation_id, conversation_name))

        for message in data['messages']:
            message_id = message['id']
            author_role = message['author']['role']
            content_parts = message.get('content', {}).get('parts', [])
            content = "\n".join([str(part) if isinstance(part, str) else "[Non-text content]" for part in content_parts])
            create_time = str(message.get('create_time', ''))

            cursor.execute('''
                INSERT OR REPLACE INTO messages (message_id, conversation_id, author_role, content, create_time)
                VALUES (?, ?, ?, ?, ?)
            ''', (message_id, conversation_id, author_role, content, create_time))

        conn.commit()
        messagebox.showinfo("Success", "Data Imported Successfully!")
        load_conversations(conn)

    except Exception as e:
        messagebox.showerror("Error", f"Failed to import data: {e}")

    finally:
        # 恢复窗口的可交互状态
        root.config(cursor="")
        root.update_idletasks()


# 选择文件对话框
def select_file():
    file_path = filedialog.askopenfilename(filetypes=[("JSON Files", "*.json")])
    if file_path:
        import_json(file_path, conn)

# 从数据库中加载对话列表
def load_conversations(conn, search_query=""):
    try:
        if search_query:
            cursor.execute('SELECT conversation_id, conversation_name FROM conversations WHERE conversation_name LIKE ?', ('%' + search_query + '%',))
        else:
            cursor.execute('SELECT conversation_id, conversation_name FROM conversations')

        records = cursor.fetchall()

        conversations_listbox.delete(0, tk.END)
        for record in records:
            conversations_listbox.insert(tk.END, f"{record[1]} ({record[0]})")
    except sqlite3.Error as e:
        messagebox.showerror("Error", f"Failed to load conversations: {e}")

# 从数据库中分页加载消息
def load_messages(conversation_id, conn, page=0):
    global current_html_content
    global selected_conversation_id
    global is_dark_mode
    offset = page * messages_per_page
    selected_conversation_id = conversation_id

    try:
        cursor.execute(
            'SELECT author_role, content, create_time FROM messages WHERE conversation_id=? ORDER BY create_time LIMIT ? OFFSET ?',
            (conversation_id, messages_per_page, offset))
        messages = cursor.fetchall()

        html_content = ""

        for msg in messages:
            author_role = msg[0]
            content = msg[1]
            create_time = msg[2]

            # Format the time and build HTML content
            try:
                create_time_formatted = datetime.fromtimestamp(float(create_time)).strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError):
                create_time_formatted = create_time

            formatted_message = f"""
            <div class="message">
                <div class="author">{author_role}</div>
                <div class="timestamp">{create_time_formatted}</div>
                <div class="content">{markdown2.markdown(content)}</div>
            </div>
            """
            html_content += formatted_message

        # Append to the existing HTML content
        current_html_content = html_content if page == 0 else current_html_content + html_content

        # Define light and dark themes
        if is_dark_mode:
            body_bg_color = "#333"
            text_color = "#fff"
            border_color = "#555"
        else:
            body_bg_color = "#fff"
            text_color = "#000"
            border_color = "#ccc"

        # Construct the full HTML document with dynamic theme
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
        <body>
            {current_html_content}
        </body>
        </html>
        """

        # Use HtmlFrame to display the content
        html_view.load_html(html_template)

    except sqlite3.Error as e:
        messagebox.showerror("Error", f"Failed to load messages: {e}")

# 处理选择对话时的动作
def on_select_conversation(event):
    selection = conversations_listbox.curselection()
    if selection:
        conversation = conversations_listbox.get(selection[0])
        conversation_id = conversation.split('(')[-1].strip(')')
        global current_page
        current_page = 0  # Reset to the first page
        load_messages(conversation_id, conn, current_page)

# 下一页消息
def next_page():
    global current_page
    current_page += 1
    if selected_conversation_id:
        load_messages(selected_conversation_id, conn, current_page)

# 保存 HTML 到文件
def save_html_to_file():
    global current_html_content

    file_path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML Files", "*.html")])

    if file_path:
        try:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(current_html_content)

            messagebox.showinfo("Success", f"HTML content saved to {file_path}!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save file: {e}")

# 折叠/展开对话框
def toggle_conversations_frame():
    global conversation_collapsed

    if conversation_collapsed:
        main_paned_window.add(conversations_frame, before=messages_frame, stretch="always")  # 显示对话列表
        toggle_button.config(text="折叠对话列表")
    else:
        main_paned_window.forget(conversations_frame)  # 隐藏左侧对话列表
        toggle_button.config(text="展开对话列表")

    conversation_collapsed = not conversation_collapsed

# 搜索对话框
def search_conversations(event=None):
    global search_query
    search_query = search_entry.get()
    load_conversations(conn, search_query)

# 右键菜单功能
def on_right_click(event):
    try:
        selection = conversations_listbox.curselection()
        if selection:
            selected_item = conversations_listbox.get(selection[0])
            conversation_id = selected_item.split('(')[-1].strip(')')

            menu = tk.Menu(root, tearoff=0)
            menu.add_command(label="删除", command=lambda: delete_conversation(conversation_id))
            menu.add_command(label="重命名", command=lambda: rename_conversation(conversation_id))
            menu.post(event.x_root, event.y_root)
    except tk.TclError:
        pass

# 删除对话
def delete_conversation(conversation_id):
    try:
        cursor.execute('DELETE FROM conversations WHERE conversation_id=?', (conversation_id,))
        cursor.execute('DELETE FROM messages WHERE conversation_id=?', (conversation_id,))
        conn.commit()
        load_conversations(conn)
        messagebox.showinfo("Success", "Conversation deleted successfully!")
    except sqlite3.Error as e:
        messagebox.showerror("Error", f"Failed to delete conversation: {e}")

# 重命名对话
def rename_conversation(conversation_id):
    new_name = simpledialog.askstring("Rename", "Enter a new name for this conversation:")
    if new_name:
        try:
            cursor.execute('UPDATE conversations SET conversation_name=? WHERE conversation_id=?', (new_name, conversation_id))
            conn.commit()
            load_conversations(conn)
            messagebox.showinfo("Success", "Conversation renamed successfully!")
        except sqlite3.Error as e:
            messagebox.showerror("Error", f"Failed to rename conversation: {e}")

# 切换深色/浅色主题
def toggle_theme():
    global is_dark_mode
    is_dark_mode = not is_dark_mode  # Toggle between dark and light mode

    if selected_conversation_id:
        load_messages(selected_conversation_id, conn, current_page)  # Reload messages with the new theme

# 创建主窗口
root = tk.Tk()
root.title("Shared Chat会话管理工具v1.1")

# 主窗口布局
main_paned_window = tk.PanedWindow(root, orient=tk.HORIZONTAL)
main_paned_window.pack(fill=tk.BOTH, expand=True)

# 左侧对话列表框架
conversations_frame = tk.Frame(main_paned_window)
main_paned_window.add(conversations_frame, stretch="always")

conversations_listbox = tk.Listbox(conversations_frame)
conversations_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
conversations_listbox.bind('<<ListboxSelect>>', on_select_conversation)
conversations_listbox.bind('<Button-3>', on_right_click)  # 绑定右键点击事件

scrollbar_conversations = ttk.Scrollbar(conversations_frame, orient=tk.VERTICAL)
scrollbar_conversations.pack(side=tk.RIGHT, fill=tk.Y)
conversations_listbox.config(yscrollcommand=scrollbar_conversations.set)
scrollbar_conversations.config(command=conversations_listbox.yview)

# 搜索框
search_entry = tk.Entry(conversations_frame)
search_entry.pack(side=tk.TOP, fill=tk.X)

# 默认提示信息
search_hint = "请输入搜索关键词"

# 初始化搜索框提示
def set_search_hint():
    if not search_entry.get():  # 如果搜索框为空，设置提示信息
        search_entry.insert(0, search_hint)
        search_entry.config(fg="grey")  # 设置提示文字颜色为灰色

# 移除提示信息
def clear_search_hint(event):
    if search_entry.get() == search_hint:  # 如果输入框中是提示信息，清空
        search_entry.delete(0, tk.END)
        search_entry.config(fg="black")  # 恢复文字颜色

# 离开搜索框时，检查是否为空，如果是则恢复提示信息
def restore_search_hint(event):
    if not search_entry.get():  # 如果输入框为空，重新显示提示信息
        set_search_hint()

# 绑定事件：进入输入框时清除提示，离开时恢复提示
search_entry.bind("<FocusIn>", clear_search_hint)
search_entry.bind("<FocusOut>", restore_search_hint)

# 搜索对话框
search_entry.bind('<KeyRelease>', search_conversations)

# 初始加载时设置提示
set_search_hint()

# 右侧消息显示框架
messages_frame = tk.Frame(main_paned_window)
main_paned_window.add(messages_frame, stretch="always")

html_view = HtmlFrame(messages_frame, horizontal_scrollbar="auto")
html_view.pack(fill="both", expand=True)

# 文件操作按钮
file_button_frame = ttk.Frame(root)
file_button_frame.pack(side=tk.TOP, pady=5)

import_button = ttk.Button(file_button_frame, text="导入JSON", command=select_file)
import_button.pack(side=tk.LEFT)

save_button = ttk.Button(file_button_frame, text="保存为HTML", command=save_html_to_file)
save_button.pack(side=tk.LEFT)

next_page_button = ttk.Button(file_button_frame, text="下一页", command=next_page)
next_page_button.pack(side=tk.LEFT)

# 折叠按钮
toggle_button = ttk.Button(file_button_frame, text="折叠对话列表", command=toggle_conversations_frame)
toggle_button.pack(side=tk.LEFT)

# 主题切换按钮
theme_button = ttk.Button(file_button_frame, text="切换深色/浅色模式", command=toggle_theme)
theme_button.pack(side=tk.LEFT)

# 初始化数据库
conn = init_db()
load_conversations(conn)

root.mainloop()