"""
选课系统 - 带GUI界面版本
功能：
1. 设置模块：输入cookies和profile_id
2. 选/换课模块：管理选课/换课任务列表
3. 课程信息获取：自动获取并解析课程信息
4. 显示模块：实时显示选课状态和日志
5. 日志功能：记录所有操作和调试信息
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import requests
import time
import re
import json
import threading
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import os


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
            # 使用贪婪匹配 .* 而不是非贪婪 .*? 以匹配到最外层的 ];
            match = re.search(r'var\s+lessonJSONs\s*=\s*(\[.*\]);', origin_text, re.S)
            if not match:
                raise Exception("无法找到课程数据，可能是cookies已过期或profile_id错误")

            lesson_json_str = match.group(1)

            # 将JavaScript对象转换为JSON格式
            # 关键：必须先转换单引号字符串，再添加key引号
            # 否则会误将字符串内的"word:"识别为对象key

            # 步骤1: 先将单引号字符串转为双引号字符串
            # 匹配单引号字符串（支持转义字符：\' 和 \"）
            def replace_single_quoted_string(match):
                """将单引号字符串转为双引号字符串，保持内容不变"""
                content = match.group(1)  # 提取单引号内的内容
                return f'"{content}"'  # 用双引号包裹

            # (?:[^'\\]|\\.)* 表示：非单引号非反斜杠的字符 或 反斜杠+任意字符（转义序列）
            string_pattern = r"'((?:[^'\\]|\\.)*)'"
            lesson_json_str = re.sub(string_pattern, replace_single_quoted_string, lesson_json_str)

            # 步骤2: 给对象的key添加引号（此时字符串已经是双引号，不会误匹配）
            lesson_json_str = re.sub(r'(\w+):', r'"\1":', lesson_json_str)

            try:
                lessons = json.loads(lesson_json_str)
            except json.JSONDecodeError as je:
                # 如果JSON解析失败，保存处理后的字符串用于调试
                with open("courses_processed.txt", "w", encoding="utf-8") as f:
                    f.write(lesson_json_str[:5000])  # 只保存前5000字符
                raise Exception(f"JSON解析失败: {str(je)}")

            # 解析课程信息，保存完整信息包括课程安排
            course_dict = {}
            for lesson in lessons:
                lesson_id = str(lesson.get('id', ''))
                course_name = lesson.get('name', '未知课程')
                teacher = lesson.get('teachers', '')
                credit = lesson.get('credits', '')
                course_type = lesson.get('courseTypeName', '')

                # 解析课程安排信息
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
                    'schedules': schedules  # 课程安排列表
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
            1: '周一',
            2: '周二',
            3: '周三',
            4: '周四',
            5: '周五',
            6: '周六',
            7: '周日'
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
        """搜索课程
        Args:
            query: 搜索关键词（可以是课程ID或课程名称）
        Returns:
            匹配的课程列表
        """
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


class CourseSelectorGUI:
    """选课系统GUI界面类"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("上财选课系统")
        self.root.geometry("1000x700")
        
        self.selector = CourseSelector()
        self.task_list = []  # [(elect_id, withdraw_id, status), ...]
        
        self.setup_ui()
        
    def setup_ui(self):
        """创建UI界面"""
        # 创建主容器
        main_container = ttk.Frame(self.root, padding="10")
        main_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_container.columnconfigure(0, weight=1)
        main_container.rowconfigure(2, weight=1)
        
        # 1. 设置模块
        self.create_settings_frame(main_container)
        
        # 2. 选课任务管理模块
        self.create_tasks_frame(main_container)
        
        # 3. 日志显示模块
        self.create_log_frame(main_container)
        
        # 4. 控制按钮
        self.create_control_frame(main_container)
    
    def create_settings_frame(self, parent):
        """创建设置模块"""
        frame = ttk.LabelFrame(parent, text="设置", padding="10")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Cookies输入
        ttk.Label(frame, text="Cookies:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.cookies_entry = ttk.Entry(frame, width=70)
        self.cookies_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5, padx=5)
        
        # Profile ID输入
        ttk.Label(frame, text="Profile ID:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.profile_id_entry = ttk.Entry(frame, width=20)
        self.profile_id_entry.grid(row=1, column=1, sticky=tk.W, pady=5, padx=5)
        self.profile_id_entry.insert(0, "11045")
        
        # 保存按钮和获取课程信息按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=1, sticky=tk.W, pady=5, padx=5)

        ttk.Button(btn_frame, text="保存设置", command=self.save_settings).pack(side=tk.LEFT, padx=5)
        # ttk.Button(btn_frame, text="获取课程列表", command=self.fetch_courses).pack(side=tk.LEFT, padx=5)
        # ttk.Button(btn_frame, text="查询课程", command=self.open_search_dialog).pack(side=tk.LEFT, padx=5)
        
        # 导出/导入按钮
        io_frame = ttk.Frame(frame)
        io_frame.grid(row=3, column=1, sticky=tk.W, pady=5, padx=5)
        
        ttk.Button(io_frame, text="导出配置", command=self.export_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(io_frame, text="导入配置", command=self.import_config).pack(side=tk.LEFT, padx=5)
        
        frame.columnconfigure(1, weight=1)
    
    def create_tasks_frame(self, parent):
        """创建选课任务管理模块"""
        frame = ttk.LabelFrame(parent, text="选课/换课任务列表", padding="10")
        frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        
        # 创建任务列表
        columns = ('elect_course', 'withdraw_course', 'status')
        self.task_tree = ttk.Treeview(frame, columns=columns, show='headings', height=8)
        
        self.task_tree.heading('elect_course', text='要选的课程')
        self.task_tree.heading('withdraw_course', text='要退的课程')
        self.task_tree.heading('status', text='状态')
        
        self.task_tree.column('elect_course', width=300)
        self.task_tree.column('withdraw_course', width=300)
        self.task_tree.column('status', width=100)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscroll=scrollbar.set)
        
        self.task_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 任务管理按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        ttk.Button(btn_frame, text="添加任务", command=self.add_task).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="删除选中", command=self.delete_task).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="清空列表", command=self.clear_tasks).pack(side=tk.LEFT, padx=5)
    
    def create_log_frame(self, parent):
        """创建日志显示模块"""
        frame = ttk.LabelFrame(parent, text="运行日志", padding="10")
        frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(frame, height=15, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 清空日志按钮
        ttk.Button(frame, text="清空日志", command=self.clear_log).grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
    
    def create_control_frame(self, parent):
        """创建控制按钮"""
        frame = ttk.Frame(parent)
        frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        
        self.start_btn = ttk.Button(frame, text="开始选课", command=self.start_election, style='Accent.TButton')
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(frame, text="停止选课", command=self.stop_election, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
    
    def log(self, message: str, level: str = "INFO"):
        """输出日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}\n"
        
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        
        # 写入日志文件
        with open("course_selector.log", "a", encoding="utf-8") as f:
            f.write(log_message)
    
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
            self.log("设置已保存")
            messagebox.showinfo("成功", "设置已保存")
        except Exception as e:
            self.log(f"保存设置失败: {str(e)}", "ERROR")
            messagebox.showerror("错误", f"保存设置失败: {str(e)}")
    
    def fetch_courses(self):
        """获取课程信息"""
        if not self.selector.cookies or not self.selector.profile_id:
            messagebox.showerror("错误", "请先保存设置")
            return
        
        self.log("正在获取课程列表...")
        
        def fetch():
            try:
                courses = self.selector.get_all_courses()
                self.log(f"成功获取 {len(courses)} 门课程信息")
                
                # 保存课程信息到文件
                with open("courses_cache.json", "w", encoding="utf-8") as f:
                    json.dump(courses, f, ensure_ascii=False, indent=4)
                
                messagebox.showinfo("成功", f"成功获取 {len(courses)} 门课程信息")
            except Exception as e:
                self.log(f"获取课程信息失败: {str(e)}", "ERROR")
                messagebox.showerror("错误", f"获取课程信息失败: {str(e)}")
        
        threading.Thread(target=fetch, daemon=True).start()
    
    def export_config(self):
        """导出配置"""
        try:
            # 收集配置数据
            config = {
                'cookies': self.cookies_entry.get().strip(),
                'profile_id': self.profile_id_entry.get().strip(),
                'task_list': self.task_list,
                'export_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # 打开保存文件对话框
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
                
                self.log(f"配置已导出到: {file_path}")
                messagebox.showinfo("成功", f"配置已成功导出到:\n{file_path}")
        except Exception as e:
            self.log(f"导出配置失败: {str(e)}", "ERROR")
            messagebox.showerror("错误", f"导出配置失败: {str(e)}")
    
    def import_config(self):
        """导入配置"""
        try:
            # 打开文件选择对话框
            file_path = filedialog.askopenfilename(
                filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
                title="导入配置"
            )

            if not file_path:
                return

            # 读取配置文件
            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 验证配置文件格式
            if 'cookies' not in config or 'profile_id' not in config:
                messagebox.showerror("错误", "配置文件格式不正确")
                return

            # 导入配置
            self.cookies_entry.delete(0, tk.END)
            self.cookies_entry.insert(0, config['cookies'])

            self.profile_id_entry.delete(0, tk.END)
            self.profile_id_entry.insert(0, config['profile_id'])

            # 导入任务列表
            if 'task_list' in config:
                self.task_list = config['task_list']
                self.refresh_task_list()

            export_time = config.get('export_time', '未知')
            self.log(f"配置已导入 (导出时间: {export_time})")

            # 提示是否保存设置
            if messagebox.askyesno("导入成功", "配置已导入，是否立即保存设置并获取课程列表？"):
                self.save_settings()
                # self.fetch_courses()
        except json.JSONDecodeError:
            messagebox.showerror("错误", "配置文件格式错误，无法解析JSON")
        except Exception as e:
            self.log(f"导入配置失败: {str(e)}", "ERROR")
            messagebox.showerror("错误", f"导入配置失败: {str(e)}")

    def open_search_dialog(self):
        """打开课程查询对话框"""
        if not self.selector.course_info_cache:
            messagebox.showwarning("提示", "请先点击\"获取课程列表\"按钮获取课程数据")
            return

        CourseSearchDialog(self.root, self.selector)
    
    def add_task(self):
        """添加选课任务"""
        dialog = TaskDialog(self.root, self.selector)
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
                    (f" / 退 {self.selector.get_course_full_info(withdraw_id)}" if withdraw_id else ""))
    
    def delete_task(self):
        """删除选中的任务"""
        selected = self.task_tree.selection()
        if not selected:
            messagebox.showwarning("警告", "请先选择要删除的任务")
            return
        
        for item in selected:
            index = self.task_tree.index(item)
            del self.task_list[index]
        
        self.refresh_task_list()
        self.log("已删除选中的任务")
    
    def clear_tasks(self):
        """清空任务列表"""
        if messagebox.askyesno("确认", "确定要清空所有任务吗？"):
            self.task_list.clear()
            self.refresh_task_list()
            self.log("已清空任务列表")
    
    def refresh_task_list(self):
        """刷新任务列表显示"""
        # 清空现有显示
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)

        # 添加任务
        for task in self.task_list:
            elect_info = self.selector.get_course_full_info(task['elect_id'])
            withdraw_info = self.selector.get_course_full_info(task['withdraw_id']) if task['withdraw_id'] else "无"
            self.task_tree.insert('', tk.END, values=(elect_info, withdraw_info, task['status']))
    
    def clear_log(self):
        """清空日志"""
        self.log_text.delete(1.0, tk.END)
    
    def start_election(self):
        """开始选课"""
        if not self.selector.cookies or not self.selector.profile_id:
            messagebox.showerror("错误", "请先保存设置")
            return
        
        if not self.task_list:
            messagebox.showerror("错误", "请先添加选课任务")
            return
        
        self.selector.is_running = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        
        self.log("=" * 50)
        self.log("开始选课")
        self.log("=" * 50)
        
        # 在新线程中运行选课
        self.selector.elect_thread = threading.Thread(target=self.run_election, daemon=True)
        self.selector.elect_thread.start()
    
    def stop_election(self):
        """停止选课"""
        self.selector.is_running = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.log("用户停止选课")
    
    def run_election(self):
        """执行选课循环"""
        try:
            while self.selector.is_running and self.task_list:
                # 获取课程限额信息
                self.log("正在获取课程限额信息...")
                lesson_limit = self.selector.get_lesson_limit()
                
                if not lesson_limit:
                    self.log("获取课程限额信息失败，5秒后重试...", "WARN")
                    time.sleep(5)
                    continue
                
                self.log(f"成功获取 {len(lesson_limit)} 门课程的限额信息")
                
                # 保存到调试文件
                with open("lesson_limit_debug.json", "w", encoding="utf-8") as f:
                    json.dump(lesson_limit, f, ensure_ascii=False, indent=4)
                
                # 检查每个任务
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
                    self.log(f"课程 {self.selector.get_course_full_info(elect_id)}: 当前人数 {sc}/{lc}")

                    if sc < lc:
                        self.log(f"课程 {self.selector.get_course_full_info(elect_id)} 有空位，开始选课...")

                        # 执行选课操作
                        response = self.selector.operate_lessons(elect_id, withdraw_id)

                        # 保存响应到调试文件
                        with open("operateLessons_debug.txt", "a", encoding="utf-8") as f:
                            f.write(f"\n\n=== {datetime.now()} ===\n")
                            f.write(f"选课ID: {elect_id}, 退课ID: {withdraw_id}\n")
                            f.write(f"响应: {response}\n")

                        self.log(f"选课响应: {response}")

                        # 更新任务状态
                        task['status'] = '已完成'
                        completed_tasks.append(i)
                        self.root.after(0, self.refresh_task_list)

                        self.log(f"✓ 成功处理: {self.selector.get_course_full_info(elect_id)}", "SUCCESS")
                    else:
                        task['status'] = '已满'
                        self.root.after(0, self.refresh_task_list)
                
                # 移除已完成的任务
                for i in reversed(completed_tasks):
                    del self.task_list[i]
                
                if not self.task_list:
                    self.log("所有任务已完成！", "SUCCESS")
                    break
                
                # 等待0.5秒后继续下一轮
                time.sleep(0.5)
            
            # 选课结束
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_btn.config(state=tk.DISABLED))
            
            if not self.task_list:
                self.log("=" * 50)
                self.log("选课任务全部完成！")
                self.log("=" * 50)
                self.root.after(0, lambda: messagebox.showinfo("完成", "选课任务全部完成！"))
            
        except Exception as e:
            self.log(f"选课过程中发生错误: {str(e)}", "ERROR")
            
            # 记录错误日志
            with open("error_log.txt", "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now()}] {str(e)}\n")
            
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_btn.config(state=tk.DISABLED))
            self.root.after(0, lambda: messagebox.showerror("错误", f"选课过程中发生错误: {str(e)}"))


class TaskDialog:
    """添加任务对话框"""

    def __init__(self, parent, selector):
        self.selector = selector
        self.result = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("添加选课任务")
        self.dialog.geometry("500x300")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # 任务类型选择
        ttk.Label(self.dialog, text="任务类型:").grid(row=0, column=0, sticky=tk.W, padx=10, pady=10)
        self.task_type = tk.StringVar(value="elect")
        ttk.Radiobutton(self.dialog, text="选课", variable=self.task_type, value="elect").grid(row=0, column=1, sticky=tk.W, pady=10)
        ttk.Radiobutton(self.dialog, text="换课", variable=self.task_type, value="exchange").grid(row=0, column=2, sticky=tk.W, pady=10)

        # 要选的课程
        ttk.Label(self.dialog, text="要选的课程ID:").grid(row=1, column=0, sticky=tk.W, padx=10, pady=10)
        self.elect_entry = ttk.Entry(self.dialog, width=30)
        self.elect_entry.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=10, pady=10)

        # 要退的课程
        ttk.Label(self.dialog, text="要退的课程ID:").grid(row=2, column=0, sticky=tk.W, padx=10, pady=10)
        self.withdraw_entry = ttk.Entry(self.dialog, width=30)
        self.withdraw_entry.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=10, pady=10)

        # 提示信息
        tip_text = "提示：\n- 选课：只需填写要选的课程ID\n- 换课：需要同时填写要选和要退的课程ID\n- 课程ID可以从课程列表中获取"
        tip_label = ttk.Label(self.dialog, text=tip_text, foreground="gray")
        tip_label.grid(row=3, column=0, columnspan=3, sticky=tk.W, padx=10, pady=10)

        # 按钮
        btn_frame = ttk.Frame(self.dialog)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=20)

        ttk.Button(btn_frame, text="确定", command=self.ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=self.cancel).pack(side=tk.LEFT, padx=5)

        self.dialog.columnconfigure(1, weight=1)

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


class CourseSearchDialog:
    """课程查询对话框"""

    def __init__(self, parent, selector):
        self.selector = selector

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("课程查询")
        self.dialog.geometry("1000x600")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # 搜索框架
        search_frame = ttk.Frame(self.dialog, padding="10")
        search_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=10, pady=10)

        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT, padx=5)
        self.search_entry = ttk.Entry(search_frame, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(search_frame, text="查询", command=self.search).pack(side=tk.LEFT, padx=5)
        ttk.Button(search_frame, text="显示全部", command=self.show_all).pack(side=tk.LEFT, padx=5)

        # 提示信息
        tip_text = "提示：输入课程ID或课程名称进行搜索"
        ttk.Label(search_frame, text=tip_text, foreground="gray").pack(side=tk.LEFT, padx=10)

        # 结果列表框架
        result_frame = ttk.Frame(self.dialog, padding="10")
        result_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=10)
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)

        # 创建结果列表
        columns = ('id', 'name', 'teacher', 'credit', 'type', 'schedule')
        self.result_tree = ttk.Treeview(result_frame, columns=columns, show='headings', height=20)

        self.result_tree.heading('id', text='课程ID')
        self.result_tree.heading('name', text='课程名称')
        self.result_tree.heading('teacher', text='教师')
        self.result_tree.heading('credit', text='学分')
        self.result_tree.heading('type', text='课程类型')
        self.result_tree.heading('schedule', text='课程安排')

        self.result_tree.column('id', width=80)
        self.result_tree.column('name', width=200)
        self.result_tree.column('teacher', width=100)
        self.result_tree.column('credit', width=60)
        self.result_tree.column('type', width=100)
        self.result_tree.column('schedule', width=300)

        # 添加滚动条
        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        self.result_tree.configure(yscroll=scrollbar.set)

        self.result_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # 状态栏
        self.status_label = ttk.Label(self.dialog, text="", foreground="blue")
        self.status_label.grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)

        # 关闭按钮
        btn_frame = ttk.Frame(self.dialog, padding="10")
        btn_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), padx=10, pady=10)
        ttk.Button(btn_frame, text="关闭", command=self.dialog.destroy).pack(side=tk.RIGHT, padx=5)

        # 配置权重
        self.dialog.columnconfigure(0, weight=1)
        self.dialog.rowconfigure(1, weight=1)

        # 绑定回车键到搜索
        self.search_entry.bind('<Return>', lambda e: self.search())

        # 自动聚焦到搜索框
        self.search_entry.focus()

    def search(self):
        """执行搜索"""
        query = self.search_entry.get().strip()

        if not query:
            messagebox.showwarning("提示", "请输入搜索关键词")
            return

        # 清空现有结果
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)

        # 执行搜索
        results = self.selector.search_courses(query)

        if not results:
            self.status_label.config(text="未找到匹配的课程")
            return

        # 显示结果
        for course in results:
            schedule_str = self.selector.format_schedule(course.get('schedules', []))
            self.result_tree.insert('', tk.END, values=(
                course['id'],
                course['name'],
                course['teacher'],
                course['credit'],
                course['type'],
                schedule_str
            ))

        self.status_label.config(text=f"找到 {len(results)} 门课程")

    def show_all(self):
        """显示所有课程"""
        # 清空现有结果
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)

        # 显示所有课程
        all_courses = list(self.selector.course_info_cache.values())

        if not all_courses:
            self.status_label.config(text="没有课程数据，请先获取课程列表")
            messagebox.showinfo("提示", "没有课程数据，请先点击\"获取课程列表\"按钮")
            return

        for course in all_courses:
            schedule_str = self.selector.format_schedule(course.get('schedules', []))
            self.result_tree.insert('', tk.END, values=(
                course['id'],
                course['name'],
                course['teacher'],
                course['credit'],
                course['type'],
                schedule_str
            ))

        self.status_label.config(text=f"共 {len(all_courses)} 门课程")


def main():
    """主函数"""
    root = tk.Tk()
    app = CourseSelectorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
