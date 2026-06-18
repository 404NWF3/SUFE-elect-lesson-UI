"""
上财选课系统 - 现代化UI版本
基于 CustomTkinter 的现代化界面设计
功能：
1. 设置模块：输入cookies和profile_id
2. 选/换课模块：管理选课/换课任务列表
3. 课程信息获取：自动获取并解析课程信息
4. 显示模块：实时显示选课状态和日志
5. 日志功能：记录所有操作和调试信息
"""

import customtkinter as ctk
from tkinter import messagebox, filedialog, ttk
import tkinter as tk
import requests
import json
import re
import time
import threading
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# 设置外观模式和默认颜色主题
ctk.set_appearance_mode("dark")  # 可选: "light", "dark", "system"
ctk.set_default_color_theme("blue")  # 可选: "blue", "green", "dark-blue"


class CourseSelector:
    """课程选择器核心类"""
    
    def __init__(self):
        self.cookies = None
        self.profile_id = None
        self.course_info_cache = {}  # 课程信息缓存
        self.is_running = False
        self.elect_thread = None
        
    def trans_cookies(self, cookies_str: str) -> dict:
        """转换cookies字符串为字典"""
        cookies_dict = {}
        for cookie in cookies_str.split(';'):
            if '=' in cookie:
                key, value = cookie.split('=', 1)
                cookies_dict[key.strip()] = value.strip()
        return cookies_dict
    
    def set_credentials(self, cookies_str: str, profile_id: str):
        """设置登录凭证"""
        self.cookies = self.trans_cookies(cookies_str)
        self.profile_id = profile_id
    
    def get_all_courses(self) -> dict:
        """获取所有课程信息"""
        if not self.cookies or not self.profile_id:
            raise Exception("请先设置cookies和profile_id")

        url = f"https://eams.sufe.edu.cn/eams/stdElectCourse!data.action?profileId={self.profile_id}"
        try:
            req = requests.get(url, cookies=self.cookies, timeout=10)
            origin_text = req.text

            # 保存原始响应用于调试
            with open("courses_raw_response.txt", "w", encoding="utf-8") as f:
                f.write(origin_text)

            # 解析JavaScript变量 var lessonJSONs = [...];
            match = re.search(r'var\s+lessonJSONs\s*=\s*(\[.*\]);', origin_text, re.S)
            if not match:
                raise Exception("无法找到课程数据，可能是cookies已过期或profile_id错误")

            lesson_json_str = match.group(1)

            # 将JavaScript对象转换为JSON格式
            def replace_single_quoted_string(match):
                """将单引号字符串转为双引号字符串，保持内容不变"""
                content = match.group(1)
                return f'"{content}"'

            string_pattern = r"'((?:[^'\\]|\\.)*)'"
            lesson_json_str = re.sub(string_pattern, replace_single_quoted_string, lesson_json_str)
            lesson_json_str = re.sub(r'(\w+):', r'"\1":', lesson_json_str)

            try:
                lessons = json.loads(lesson_json_str)
            except json.JSONDecodeError as je:
                with open("courses_processed.txt", "w", encoding="utf-8") as f:
                    f.write(lesson_json_str[:5000])
                raise Exception(f"JSON解析失败: {str(je)}")

            # 解析课程信息
            course_dict = {}
            for lesson in lessons:
                lesson_id = str(lesson.get('id', ''))
                course_name = lesson.get('name', '未知课程')
                teacher = lesson.get('teachers', '')
                credit = lesson.get('credits', '')
                course_type = lesson.get('courseTypeName', '')

                arrange_info = lesson.get('arrangeInfo', [])
                schedules = []
                for arrange in arrange_info:
                    weekday = arrange.get('weekDay', '')
                    start_unit = arrange.get('startUnit', '')
                    end_unit = arrange.get('endUnit', '')
                    rooms = arrange.get('rooms', '')
                    schedules.append({
                        'weekday': weekday,
                        'start_unit': start_unit,
                        'end_unit': end_unit,
                        'rooms': rooms
                    })

                course_dict[lesson_id] = {
                    'id': lesson_id,
                    'name': course_name,
                    'teacher': teacher,
                    'credit': credit,
                    'type': course_type,
                    'schedules': schedules
                }

            self.course_info_cache = course_dict
            return course_dict
        except Exception as e:
            raise Exception(f"获取课程信息失败: {str(e)}")
    
    def get_lesson_limit(self) -> dict:
        """获取课程人数限额信息"""
        if not self.cookies or not self.profile_id:
            return {}
        
        url = f"https://eams.sufe.edu.cn/eams/stdElectCourse!queryStdCount.action?profileId={self.profile_id}"
        try:
            req = requests.get(url, cookies=self.cookies, timeout=10)
            origin_text = req.text
            
            match = re.search(r'=\s*({.*})', origin_text, re.S)
            if not match:
                return {}
            
            obj_text = match.group(1)
            obj_text = re.sub(r'(\W)(sc|lc):', r'\1"\2":', obj_text)
            obj_text = obj_text.replace("'", '"')
            data = json.loads(obj_text)
            
            result = {k: (v["sc"], v["lc"]) for k, v in data.items()}
            return result
        except Exception as e:
            print(f"获取课程限额失败: {str(e)}")
            return {}
    
    def operate_lessons(self, elect_lesson_id: str, withdraw_lesson_id: str) -> str:
        """执行选课/换课操作"""
        if not self.cookies or not self.profile_id:
            raise Exception("请先设置cookies和profile_id")
        
        url = f"https://eams.sufe.edu.cn/eams/stdElectCourse!batchOperator.action?profileId={self.profile_id}&electLessonIds={elect_lesson_id}&withdrawLessonIds={withdraw_lesson_id}&v={int(time.time()*1000)}&_={int(time.time()*1000)}"
        
        try:
            req = requests.get(url, cookies=self.cookies, timeout=10)
            response_text = req.text
            return response_text
        except Exception as e:
            return f"请求失败: {str(e)}"
    
    def format_weekday(self, weekday: int) -> str:
        """格式化星期几"""
        weekday_map = {
            1: '周一', 2: '周二', 3: '周三', 4: '周四',
            5: '周五', 6: '周六', 7: '周日'
        }
        return weekday_map.get(weekday, f'周{weekday}')

    def format_schedule(self, schedules: list) -> str:
        """格式化课程安排信息"""
        if not schedules:
            return "无安排信息"

        schedule_strs = []
        for schedule in schedules:
            weekday = self.format_weekday(schedule['weekday'])
            start_unit = schedule['start_unit']
            end_unit = schedule['end_unit']
            rooms = schedule.get('rooms', '')
            schedule_str = f"{weekday} {start_unit}-{end_unit}节"
            if rooms:
                schedule_str += f" ({rooms})"
            schedule_strs.append(schedule_str)

        return "; ".join(schedule_strs)

    def get_course_name(self, lesson_id: str) -> str:
        """根据课程ID获取课程名称（简短版本）"""
        if not lesson_id:
            return "无"
        if lesson_id in self.course_info_cache:
            course = self.course_info_cache[lesson_id]
            return course['name']
        return f"课程ID: {lesson_id}"

    def get_course_full_info(self, lesson_id: str) -> str:
        """根据课程ID获取完整的课程信息"""
        if not lesson_id:
            return "无"
        if lesson_id in self.course_info_cache:
            course = self.course_info_cache[lesson_id]
            teacher_info = f" - {course['teacher']}" if course['teacher'] else ""
            schedule_info = self.format_schedule(course.get('schedules', []))
            return f"{course['name']}{teacher_info} ({schedule_info})"
        return f"课程ID: {lesson_id}"

    def search_courses(self, query: str) -> List[dict]:
        """搜索课程"""
        results = []
        query = query.strip()

        if not query:
            return results

        # 如果是纯数字，优先按ID搜索
        if query.isdigit():
            if query in self.course_info_cache:
                results.append(self.course_info_cache[query])
            return results

        # 按课程名称搜索
        for lesson_id, course in self.course_info_cache.items():
            if query.lower() in course['name'].lower():
                results.append(course)

        return results


class ModernCourseSelectorGUI:
    """现代化选课系统GUI界面类"""
    
    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("上财选课系统 - 现代化版本")
        self.root.geometry("1200x800")
        
        # 设置窗口图标（如果有的话）
        # self.root.iconbitmap("icon.ico")
        
        self.selector = CourseSelector()
        self.task_list = []
        
        self.setup_ui()
        
    def setup_ui(self):
        """创建UI界面"""
        # 创建侧边栏
        self.create_sidebar()
        
        # 创建主内容区域
        self.create_main_content()
        
    def create_sidebar(self):
        """创建侧边栏"""
        self.sidebar = ctk.CTkFrame(self.root, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)
        
        # 标题
        title = ctk.CTkLabel(
            self.sidebar, 
            text="上财选课系统",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # 副标题
        subtitle = ctk.CTkLabel(
            self.sidebar,
            text="Modern Edition",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        subtitle.grid(row=1, column=0, padx=20, pady=(0, 20))
        
        # 外观模式切换
        self.appearance_label = ctk.CTkLabel(self.sidebar, text="外观模式:", anchor="w")
        self.appearance_label.grid(row=2, column=0, padx=20, pady=(10, 0))
        
        self.appearance_mode = ctk.CTkOptionMenu(
            self.sidebar,
            values=["Light", "Dark", "System"],
            command=self.change_appearance_mode
        )
        self.appearance_mode.grid(row=3, column=0, padx=20, pady=(10, 10))
        self.appearance_mode.set("Dark")
        
        # UI缩放
        self.scaling_label = ctk.CTkLabel(self.sidebar, text="UI缩放:", anchor="w")
        self.scaling_label.grid(row=4, column=0, padx=20, pady=(10, 0))
        
        self.scaling_optionemenu = ctk.CTkOptionMenu(
            self.sidebar,
            values=["80%", "90%", "100%", "110%", "120%"],
            command=self.change_scaling_event
        )
        self.scaling_optionemenu.grid(row=5, column=0, padx=20, pady=(10, 20))
        self.scaling_optionemenu.set("100%")
        
    def create_main_content(self):
        """创建主内容区域"""
        # 配置网格权重
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=0)
        self.root.grid_rowconfigure(1, weight=0)
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_rowconfigure(3, weight=0)
        
        # 1. 设置区域
        self.create_settings_section()
        
        # 2. 任务列表区域
        self.create_tasks_section()
        
        # 3. 日志区域
        self.create_log_section()
        
        # 4. 控制按钮区域
        self.create_control_section()
    
    def create_settings_section(self):
        """创建设置区域"""
        settings_frame = ctk.CTkFrame(self.root, corner_radius=10)
        settings_frame.grid(row=0, column=1, padx=20, pady=(20, 10), sticky="ew")
        
        # 标题
        title = ctk.CTkLabel(
            settings_frame,
            text="⚙️ 账户设置",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title.grid(row=0, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="w")
        
        # Cookies输入
        cookies_label = ctk.CTkLabel(settings_frame, text="Cookies:")
        cookies_label.grid(row=1, column=0, padx=(20, 10), pady=10, sticky="w")
        
        self.cookies_entry = ctk.CTkEntry(
            settings_frame,
            placeholder_text="请输入您的Cookies...",
            width=500
        )
        self.cookies_entry.grid(row=1, column=1, padx=(0, 20), pady=10, sticky="ew")
        
        # Profile ID输入
        profile_label = ctk.CTkLabel(settings_frame, text="Profile ID:")
        profile_label.grid(row=2, column=0, padx=(20, 10), pady=10, sticky="w")
        
        self.profile_id_entry = ctk.CTkEntry(
            settings_frame,
            placeholder_text="例如: 11045",
            width=200
        )
        self.profile_id_entry.grid(row=2, column=1, padx=(0, 20), pady=10, sticky="w")
        self.profile_id_entry.insert(0, "11045")
        
        # 按钮框架
        btn_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, padx=20, pady=(10, 15), sticky="w")
        
        # 保存设置按钮
        save_btn = ctk.CTkButton(
            btn_frame,
            text="💾 保存设置",
            command=self.save_settings,
            width=120
        )
        save_btn.pack(side="left", padx=5)
        
        # 导出配置按钮
        export_btn = ctk.CTkButton(
            btn_frame,
            text="📤 导出配置",
            command=self.export_config,
            width=120,
            fg_color="transparent",
            border_width=2
        )
        export_btn.pack(side="left", padx=5)
        
        # 导入配置按钮
        import_btn = ctk.CTkButton(
            btn_frame,
            text="📥 导入配置",
            command=self.import_config,
            width=120,
            fg_color="transparent",
            border_width=2
        )
        import_btn.pack(side="left", padx=5)
        
        settings_frame.grid_columnconfigure(1, weight=1)
    
    def create_tasks_section(self):
        """创建任务列表区域"""
        tasks_frame = ctk.CTkFrame(self.root, corner_radius=10)
        tasks_frame.grid(row=1, column=1, padx=20, pady=10, sticky="ew")
        
        # 标题和按钮行
        header_frame = ctk.CTkFrame(tasks_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="ew")
        
        title = ctk.CTkLabel(
            header_frame,
            text="📋 选课任务列表",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title.pack(side="left")
        
        # 任务管理按钮
        btn_container = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_container.pack(side="right")
        
        add_task_btn = ctk.CTkButton(
            btn_container,
            text="➕ 添加任务",
            command=self.add_task,
            width=100,
            height=32
        )
        add_task_btn.pack(side="left", padx=5)
        
        delete_task_btn = ctk.CTkButton(
            btn_container,
            text="🗑️ 删除",
            command=self.delete_task,
            width=100,
            height=32,
            fg_color="transparent",
            border_width=2
        )
        delete_task_btn.pack(side="left", padx=5)
        
        clear_tasks_btn = ctk.CTkButton(
            btn_container,
            text="🧹 清空",
            command=self.clear_tasks,
            width=100,
            height=32,
            fg_color="transparent",
            border_width=2
        )
        clear_tasks_btn.pack(side="left", padx=5)
        
        # 任务列表（使用Treeview支持选择）
        # 创建Treeview容器
        tree_frame = ctk.CTkFrame(tasks_frame, fg_color="transparent")
        tree_frame.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="ew")
        
        # 创建Treeview
        columns = ('elect_course', 'withdraw_course', 'status')
        self.task_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show='headings',
            height=6,
            selectmode='extended'  # 支持多选
        )
        
        # 设置列标题
        self.task_tree.heading('elect_course', text='要选的课程')
        self.task_tree.heading('withdraw_course', text='要退的课程')
        self.task_tree.heading('status', text='状态')
        
        # 设置列宽
        self.task_tree.column('elect_course', width=350)
        self.task_tree.column('withdraw_course', width=350)
        self.task_tree.column('status', width=100)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscroll=scrollbar.set)
        
        # 布局
        self.task_tree.grid(row=0, column=0, sticky="ew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        tree_frame.grid_columnconfigure(0, weight=1)
        tasks_frame.grid_columnconfigure(0, weight=1)
    
    def create_log_section(self):
        """创建日志区域"""
        log_frame = ctk.CTkFrame(self.root, corner_radius=10)
        log_frame.grid(row=2, column=1, padx=20, pady=10, sticky="nsew")
        
        # 标题和清空按钮
        header_frame = ctk.CTkFrame(log_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="ew")
        
        title = ctk.CTkLabel(
            header_frame,
            text="📝 运行日志",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title.pack(side="left")
        
        clear_log_btn = ctk.CTkButton(
            header_frame,
            text="🧹 清空日志",
            command=self.clear_log,
            width=100,
            height=32,
            fg_color="transparent",
            border_width=2
        )
        clear_log_btn.pack(side="right")
        
        # 日志文本框
        self.log_textbox = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.log_textbox.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="nsew")
        
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)
    
    def create_control_section(self):
        """创建控制按钮区域"""
        control_frame = ctk.CTkFrame(self.root, corner_radius=10, height=80)
        control_frame.grid(row=3, column=1, padx=20, pady=(10, 20), sticky="ew")
        
        # 开始按钮
        self.start_btn = ctk.CTkButton(
            control_frame,
            text="🚀 开始选课",
            command=self.start_election,
            width=150,
            height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#28a745",
            hover_color="#218838"
        )
        self.start_btn.pack(side="left", padx=20, pady=15)
        
        # 停止按钮
        self.stop_btn = ctk.CTkButton(
            control_frame,
            text="⏹️ 停止选课",
            command=self.stop_election,
            width=150,
            height=50,
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#dc3545",
            hover_color="#c82333",
            state="disabled"
        )
        self.stop_btn.pack(side="left", padx=10, pady=15)
        
        # 状态指示器
        self.status_label = ctk.CTkLabel(
            control_frame,
            text="● 就绪",
            font=ctk.CTkFont(size=14),
            text_color="#28a745"
        )
        self.status_label.pack(side="left", padx=20, pady=15)
    
    def change_appearance_mode(self, new_mode: str):
        """切换外观模式"""
        ctk.set_appearance_mode(new_mode.lower())
    
    def change_scaling_event(self, new_scaling: str):
        """改变UI缩放"""
        new_scaling_float = int(new_scaling.replace("%", "")) / 100
        ctk.set_widget_scaling(new_scaling_float)
    
    def log(self, message: str, level: str = "INFO"):
        """输出日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # 根据级别设置颜色标记
        color_tags = {
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "WARN": "⚠️",
            "ERROR": "❌"
        }
        
        tag = color_tags.get(level, "ℹ️")
        log_message = f"[{timestamp}] {tag} {message}\n"
        
        self.log_textbox.insert("end", log_message)
        self.log_textbox.see("end")
        
        # 写入日志文件
        with open("course_selector.log", "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")
    
    def save_settings(self):
        """保存设置"""
        cookies = self.cookies_entry.get().strip()
        profile_id = self.profile_id_entry.get().strip()
        
        if not cookies:
            messagebox.showerror("错误", "请输入Cookies")
            return
        
        if not profile_id:
            messagebox.showerror("错误", "请输入Profile ID")
            return
        
        try:
            self.selector.set_credentials(cookies, profile_id)
            self.log("设置已保存", "SUCCESS")
            messagebox.showinfo("成功", "设置已保存")
        except Exception as e:
            self.log(f"保存设置失败: {str(e)}", "ERROR")
            messagebox.showerror("错误", f"保存设置失败: {str(e)}")
    
    def export_config(self):
        """导出配置"""
        try:
            config = {
                'cookies': self.cookies_entry.get().strip(),
                'profile_id': self.profile_id_entry.get().strip(),
                'task_list': self.task_list,
                'export_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            default_filename = f"选课配置_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
                initialfile=default_filename,
                title="导出配置"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                
                self.log(f"配置已导出到: {file_path}", "SUCCESS")
                messagebox.showinfo("成功", f"配置已成功导出")
        except Exception as e:
            self.log(f"导出配置失败: {str(e)}", "ERROR")
            messagebox.showerror("错误", f"导出配置失败: {str(e)}")
    
    def import_config(self):
        """导入配置"""
        try:
            file_path = filedialog.askopenfilename(
                filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
                title="导入配置"
            )

            if not file_path:
                return

            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if 'cookies' not in config or 'profile_id' not in config:
                messagebox.showerror("错误", "配置文件格式不正确")
                return

            self.cookies_entry.delete(0, "end")
            self.cookies_entry.insert(0, config['cookies'])

            self.profile_id_entry.delete(0, "end")
            self.profile_id_entry.insert(0, config['profile_id'])

            if 'task_list' in config:
                self.task_list = config['task_list']
                self.refresh_task_list()

            export_time = config.get('export_time', '未知')
            self.log(f"配置已导入 (导出时间: {export_time})", "SUCCESS")

            if messagebox.askyesno("导入成功", "配置已导入，是否立即保存设置？"):
                self.save_settings()
        except json.JSONDecodeError:
            messagebox.showerror("错误", "配置文件格式错误，无法解析JSON")
        except Exception as e:
            self.log(f"导入配置失败: {str(e)}", "ERROR")
            messagebox.showerror("错误", f"导入配置失败: {str(e)}")
    
    def add_task(self):
        """添加选课任务"""
        dialog = ModernTaskDialog(self.root, self.selector)
        self.root.wait_window(dialog.dialog)

        if dialog.result:
            elect_id, withdraw_id = dialog.result
            self.task_list.append({
                'elect_id': elect_id,
                'withdraw_id': withdraw_id,
                'status': '等待中'
            })
            self.refresh_task_list()
            self.log(f"添加任务: 选 {self.selector.get_course_full_info(elect_id)}" +
                    (f" / 退 {self.selector.get_course_full_info(withdraw_id)}" if withdraw_id else ""), "SUCCESS")
    
    def delete_task(self):
        """删除选中的任务"""
        selected = self.task_tree.selection()
        if not selected:
            messagebox.showwarning("警告", "请先选择要删除的任务")
            return
        
        if messagebox.askyesno("确认", f"确定要删除选中的 {len(selected)} 个任务吗？"):
            # 获取选中项的索引（从后往前删除以避免索引变化）
            indices = [self.task_tree.index(item) for item in selected]
            for index in sorted(indices, reverse=True):
                del self.task_list[index]
            
            self.refresh_task_list()
            self.log(f"已删除 {len(selected)} 个任务", "SUCCESS")
    
    def clear_tasks(self):
        """清空任务列表"""
        if messagebox.askyesno("确认", "确定要清空所有任务吗？"):
            self.task_list.clear()
            self.refresh_task_list()
            self.log("已清空任务列表", "SUCCESS")
    
    def refresh_task_list(self):
        """刷新任务列表显示"""
        # 清空现有显示
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)
        
        if not self.task_list:
            return
        
        # 添加任务到Treeview
        for task in self.task_list:
            elect_info = self.selector.get_course_full_info(task['elect_id'])
            withdraw_info = self.selector.get_course_full_info(task['withdraw_id']) if task['withdraw_id'] else "无"
            status = task['status']
            
            self.task_tree.insert('', tk.END, values=(elect_info, withdraw_info, status))
    
    def clear_log(self):
        """清空日志"""
        self.log_textbox.delete("0.0", "end")
        self.log("日志已清空", "INFO")
    
    def start_election(self):
        """开始选课"""
        if not self.selector.cookies or not self.selector.profile_id:
            messagebox.showerror("错误", "请先保存设置")
            return
        
        if not self.task_list:
            messagebox.showerror("错误", "请先添加选课任务")
            return
        
        self.selector.is_running = True
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text="● 运行中", text_color="#ffc107")
        
        self.log("=" * 50)
        self.log("开始选课", "SUCCESS")
        self.log("=" * 50)
        
        self.selector.elect_thread = threading.Thread(target=self.run_election, daemon=True)
        self.selector.elect_thread.start()
    
    def stop_election(self):
        """停止选课"""
        self.selector.is_running = False
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="● 已停止", text_color="#dc3545")
        self.log("用户停止选课", "WARN")
    
    def run_election(self):
        """执行选课循环"""
        try:
            while self.selector.is_running and self.task_list:
                self.log("正在获取课程限额信息...")
                lesson_limit = self.selector.get_lesson_limit()
                
                if not lesson_limit:
                    self.log("获取课程限额信息失败，5秒后重试...", "WARN")
                    time.sleep(5)
                    continue
                
                self.log(f"成功获取 {len(lesson_limit)} 门课程的限额信息", "SUCCESS")
                
                with open("lesson_limit_debug.json", "w", encoding="utf-8") as f:
                    json.dump(lesson_limit, f, ensure_ascii=False, indent=4)
                
                completed_tasks = []
                for i, task in enumerate(self.task_list):
                    if not self.selector.is_running:
                        break
                    
                    elect_id = task['elect_id']
                    withdraw_id = task['withdraw_id']

                    if elect_id not in lesson_limit:
                        self.log(f"课程 {self.selector.get_course_full_info(elect_id)} 不在限额列表中", "WARN")
                        continue

                    sc, lc = lesson_limit[elect_id]
                    self.log(f"课程 {self.selector.get_course_name(elect_id)}: 当前人数 {sc}/{lc}")

                    if sc < lc:
                        self.log(f"课程 {self.selector.get_course_name(elect_id)} 有空位，开始选课...")

                        response = self.selector.operate_lessons(elect_id, withdraw_id)

                        with open("operateLessons_debug.txt", "a", encoding="utf-8") as f:
                            f.write(f"\n\n=== {datetime.now()} ===\n")
                            f.write(f"选课ID: {elect_id}, 退课ID: {withdraw_id}\n")
                            f.write(f"响应: {response}\n")

                        self.log(f"选课响应: {response}")

                        task['status'] = '已完成'
                        completed_tasks.append(i)
                        self.root.after(0, self.refresh_task_list)

                        self.log(f"成功处理: {self.selector.get_course_name(elect_id)}", "SUCCESS")
                    else:
                        task['status'] = '已满'
                        self.root.after(0, self.refresh_task_list)
                
                for i in reversed(completed_tasks):
                    del self.task_list[i]
                
                if not self.task_list:
                    self.log("所有任务已完成！", "SUCCESS")
                    break
                
                time.sleep(1)
            
            self.root.after(0, lambda: self.start_btn.configure(state="normal"))
            self.root.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.root.after(0, lambda: self.status_label.configure(text="● 就绪", text_color="#28a745"))
            
            if not self.task_list:
                self.log("=" * 50)
                self.log("选课任务全部完成！", "SUCCESS")
                self.log("=" * 50)
                self.root.after(0, lambda: messagebox.showinfo("完成", "选课任务全部完成！"))
            
        except Exception as e:
            self.log(f"选课过程中发生错误: {str(e)}", "ERROR")
            
            with open("error_log.txt", "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now()}] {str(e)}\n")
            
            self.root.after(0, lambda: self.start_btn.configure(state="normal"))
            self.root.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.root.after(0, lambda: self.status_label.configure(text="● 错误", text_color="#dc3545"))
            self.root.after(0, lambda: messagebox.showerror("错误", f"选课过程中发生错误: {str(e)}"))
    
    def run(self):
        """运行应用"""
        self.log("欢迎使用上财选课系统！", "SUCCESS")
        self.log("请先在设置区域输入Cookies和Profile ID")
        self.root.mainloop()


class ModernTaskDialog:
    """现代化添加任务对话框"""

    def __init__(self, parent, selector):
        self.selector = selector
        self.result = None

        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title("添加选课任务")
        self.dialog.geometry("600x400")
        
        # 设置为模态窗口
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # 居中显示
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (400 // 2)
        self.dialog.geometry(f"+{x}+{y}")

        # 标题
        title = ctk.CTkLabel(
            self.dialog,
            text="📝 添加选课任务",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(pady=(20, 10))

        # 内容框架
        content_frame = ctk.CTkFrame(self.dialog)
        content_frame.pack(padx=30, pady=20, fill="both", expand=True)

        # 任务类型选择
        type_label = ctk.CTkLabel(
            content_frame,
            text="任务类型:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        type_label.pack(anchor="w", padx=20, pady=(20, 10))

        self.task_type = tk.StringVar(value="elect")
        
        type_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        type_frame.pack(anchor="w", padx=20)
        
        elect_radio = ctk.CTkRadioButton(
            type_frame,
            text="选课（只选课）",
            variable=self.task_type,
            value="elect"
        )
        elect_radio.pack(side="left", padx=(0, 20))
        
        exchange_radio = ctk.CTkRadioButton(
            type_frame,
            text="换课（选课+退课）",
            variable=self.task_type,
            value="exchange"
        )
        exchange_radio.pack(side="left")

        # 要选的课程
        elect_label = ctk.CTkLabel(
            content_frame,
            text="要选的课程ID:",
            font=ctk.CTkFont(size=14)
        )
        elect_label.pack(anchor="w", padx=20, pady=(20, 5))

        self.elect_entry = ctk.CTkEntry(
            content_frame,
            placeholder_text="请输入课程ID",
            height=40
        )
        self.elect_entry.pack(fill="x", padx=20, pady=(0, 10))

        # 要退的课程
        withdraw_label = ctk.CTkLabel(
            content_frame,
            text="要退的课程ID (换课时必填):",
            font=ctk.CTkFont(size=14)
        )
        withdraw_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.withdraw_entry = ctk.CTkEntry(
            content_frame,
            placeholder_text="换课时请输入要退的课程ID",
            height=40
        )
        self.withdraw_entry.pack(fill="x", padx=20, pady=(0, 10))

        # 提示信息
        tip_label = ctk.CTkLabel(
            content_frame,
            text="💡 提示：选课只需填写要选的课程ID，换课需要同时填写要选和要退的课程ID",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        tip_label.pack(pady=(10, 20))

        # 按钮框架
        btn_frame = ctk.CTkFrame(self.dialog, fg_color="transparent")
        btn_frame.pack(pady=(0, 20))

        ok_btn = ctk.CTkButton(
            btn_frame,
            text="✅ 确定",
            command=self.ok,
            width=120,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        ok_btn.pack(side="left", padx=10)

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="❌ 取消",
            command=self.cancel,
            width=120,
            height=40,
            font=ctk.CTkFont(size=14),
            fg_color="transparent",
            border_width=2
        )
        cancel_btn.pack(side="left", padx=10)

    def ok(self):
        elect_id = self.elect_entry.get().strip()
        withdraw_id = self.withdraw_entry.get().strip()

        if not elect_id:
            messagebox.showerror("错误", "请输入要选的课程ID")
            return

        if self.task_type.get() == "exchange" and not withdraw_id:
            messagebox.showerror("错误", "换课需要输入要退的课程ID")
            return

        self.result = (elect_id, withdraw_id)
        self.dialog.destroy()

    def cancel(self):
        self.dialog.destroy()


def main():
    """主函数"""
    app = ModernCourseSelectorGUI()
    app.run()


if __name__ == "__main__":
    main()
