"""
上财选课系统 - Studio UI
全新布局与视觉风格，保留选课核心功能。
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
import requests
import json
import re
import time
import threading
from datetime import datetime
from typing import Dict, List


ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class CourseSelector:
    """课程选择器核心类"""

    def __init__(self):
        self.cookies = None
        self.profile_id = None
        self.course_info_cache = {}
        self.is_running = False
        self.elect_thread = None

    def trans_cookies(self, cookies_str: str) -> dict:
        cookies_dict = {}
        for cookie in cookies_str.split(";"):
            if "=" in cookie:
                key, value = cookie.split("=", 1)
                cookies_dict[key.strip()] = value.strip()
        return cookies_dict

    def set_credentials(self, cookies_str: str, profile_id: str):
        self.cookies = self.trans_cookies(cookies_str)
        self.profile_id = profile_id
    def get_all_courses(self) -> dict:
        if not self.cookies or not self.profile_id:
            raise Exception("请先设置Cookies和Profile ID")

        url = f"https://eams.sufe.edu.cn/eams/stdElectCourse!data.action?profileId={self.profile_id}"
        try:
            req = requests.get(url, cookies=self.cookies, timeout=10)
            origin_text = req.text

            with open("courses_raw_response.txt", "w", encoding="utf-8") as f:
                f.write(origin_text)

            match = re.search(r"var\s+lessonJSONs\s*=\s*(\[.*\]);", origin_text, re.S)
            if not match:
                raise Exception("无法找到课程数据，可能是Cookies过期或Profile ID错误")

            lesson_json_str = match.group(1)

            def replace_single_quoted_string(match_group):
                content = match_group.group(1)
                return f"\"{content}\""

            string_pattern = r"'((?:[^'\\]|\\.)*)'"
            lesson_json_str = re.sub(string_pattern, replace_single_quoted_string, lesson_json_str)
            lesson_json_str = re.sub(r"(\w+):", r'"\1":', lesson_json_str)

            try:
                lessons = json.loads(lesson_json_str)
            except json.JSONDecodeError as json_error:
                with open("courses_processed.txt", "w", encoding="utf-8") as f:
                    f.write(lesson_json_str[:5000])
                raise Exception(f"JSON解析失败: {str(json_error)}")

            course_dict = {}
            for lesson in lessons:
                lesson_id = str(lesson.get("id", ""))
                course_name = lesson.get("name", "未知课程")
                teacher = lesson.get("teachers", "")
                credit = lesson.get("credits", "")
                course_type = lesson.get("courseTypeName", "")

                arrange_info = lesson.get("arrangeInfo", [])
                schedules = []
                for arrange in arrange_info:
                    schedules.append(
                        {
                            "weekday": arrange.get("weekDay", ""),
                            "start_unit": arrange.get("startUnit", ""),
                            "end_unit": arrange.get("endUnit", ""),
                            "rooms": arrange.get("rooms", ""),
                        }
                    )

                course_dict[lesson_id] = {
                    "id": lesson_id,
                    "name": course_name,
                    "teacher": teacher,
                    "credit": credit,
                    "type": course_type,
                    "schedules": schedules,
                }

            self.course_info_cache = course_dict
            return course_dict
        except Exception as exc:
            raise Exception(f"获取课程信息失败: {str(exc)}")
    def get_lesson_limit(self) -> dict:
        if not self.cookies or not self.profile_id:
            return {}

        url = f"https://eams.sufe.edu.cn/eams/stdElectCourse!queryStdCount.action?profileId={self.profile_id}"
        try:
            req = requests.get(url, cookies=self.cookies, timeout=10)
            origin_text = req.text

            match = re.search(r"=\s*({.*})", origin_text, re.S)
            if not match:
                return {}

            obj_text = match.group(1)
            obj_text = re.sub(r"(\W)(sc|lc):", r'\1"\2":', obj_text)
            obj_text = obj_text.replace("'", '"')
            data = json.loads(obj_text)
            return {k: (v["sc"], v["lc"]) for k, v in data.items()}
        except Exception as exc:
            print(f"获取课程限额失败: {str(exc)}")
            return {}

    def operate_lessons(self, elect_lesson_id: str, withdraw_lesson_id: str) -> str:
        if not self.cookies or not self.profile_id:
            raise Exception("请先设置Cookies和Profile ID")

        url = (
            "https://eams.sufe.edu.cn/eams/stdElectCourse!batchOperator.action"
            f"?profileId={self.profile_id}&electLessonIds={elect_lesson_id}"
            f"&withdrawLessonIds={withdraw_lesson_id}&v={int(time.time() * 1000)}"
            f"&_={int(time.time() * 1000)}"
        )

        try:
            req = requests.get(url, cookies=self.cookies, timeout=10)
            return req.text
        except Exception as exc:
            return f"请求失败: {str(exc)}"

    def format_weekday(self, weekday: int) -> str:
        weekday_map = {
            1: "周一",
            2: "周二",
            3: "周三",
            4: "周四",
            5: "周五",
            6: "周六",
            7: "周日",
        }
        return weekday_map.get(weekday, f"周{weekday}")

    def format_schedule(self, schedules: list) -> str:
        if not schedules:
            return "无安排信息"

        schedule_strs = []
        for schedule in schedules:
            weekday = self.format_weekday(schedule["weekday"])
            start_unit = schedule["start_unit"]
            end_unit = schedule["end_unit"]
            rooms = schedule.get("rooms", "")
            schedule_str = f"{weekday} {start_unit}-{end_unit}节"
            if rooms:
                schedule_str += f" ({rooms})"
            schedule_strs.append(schedule_str)

        return "; ".join(schedule_strs)
    def get_course_name(self, lesson_id: str) -> str:
        if not lesson_id:
            return "无"
        if lesson_id in self.course_info_cache:
            return self.course_info_cache[lesson_id]["name"]
        return f"课程ID: {lesson_id}"

    def get_course_full_info(self, lesson_id: str) -> str:
        if not lesson_id:
            return "无"
        if lesson_id in self.course_info_cache:
            course = self.course_info_cache[lesson_id]
            teacher_info = f" - {course['teacher']}" if course["teacher"] else ""
            schedule_info = self.format_schedule(course.get("schedules", []))
            return f"{course['name']}{teacher_info} ({schedule_info})"
        return f"课程ID: {lesson_id}"

    def search_courses(self, query: str) -> List[dict]:
        results = []
        query = query.strip()
        if not query:
            return results
        if query.isdigit():
            if query in self.course_info_cache:
                results.append(self.course_info_cache[query])
            return results
        for course in self.course_info_cache.values():
            if query.lower() in course["name"].lower():
                results.append(course)
        return results


class StudioCourseSelectorGUI:
    """Studio 视觉风格的选课系统界面"""

    def __init__(self):
        self.root = ctk.CTk()
        self.root.title("上财选课系统 - Studio UI")
        self.root.geometry("1280x860")
        self.root.minsize(1100, 720)

        self.palette = {
            "bg": "#F0FDFA",
            "surface": "#E6FFFB",
            "card": "#F8FFFE",
            "border": "#A7F3D0",
            "text": "#134E4A",
            "muted": "#2C7A7B",
            "primary": "#0D9488",
            "primary_hover": "#0F766E",
            "accent": "#EA580C",
            "accent_hover": "#C2410C",
            "warn": "#EA580C",
            "success": "#16A34A",
            "danger": "#DC2626",
        }

        self.root.configure(fg_color=self.palette["bg"])

        self.fonts = {
            "title": ctk.CTkFont(family="Fira Sans", size=20, weight="bold"),
            "section": ctk.CTkFont(family="Fira Sans", size=16, weight="bold"),
            "body": ctk.CTkFont(family="Fira Sans", size=13),
            "small": ctk.CTkFont(family="Fira Sans", size=12),
            "mono": ctk.CTkFont(family="Fira Code", size=11),
        }

        self.selector = CourseSelector()
        self.task_list = []

        self.setup_styles()
        self.build_layout()
    def setup_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Studio.Treeview",
            background=self.palette["card"],
            fieldbackground=self.palette["card"],
            foreground=self.palette["text"],
            rowheight=28,
            borderwidth=0,
        )
        style.configure(
            "Studio.Treeview.Heading",
            background=self.palette["surface"],
            foreground=self.palette["text"],
            relief="flat",
            padding=6,
        )
        style.map(
            "Studio.Treeview",
            background=[("selected", "#99F6E4")],
            foreground=[("selected", self.palette["text"])],
        )

    def build_layout(self):
        self.root.grid_columnconfigure(0, weight=0)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.build_sidebar()
        self.build_main()

    def build_sidebar(self):
        self.sidebar = ctk.CTkFrame(
            self.root,
            width=260,
            corner_radius=0,
            fg_color=self.palette["surface"],
            border_width=1,
            border_color=self.palette["border"],
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(6, weight=1)

        brand = ctk.CTkLabel(
            self.sidebar,
            text="选课工作台",
            font=self.fonts["title"],
            text_color=self.palette["text"],
        )
        brand.grid(row=0, column=0, padx=20, pady=(24, 4), sticky="w")

        subtitle = ctk.CTkLabel(
            self.sidebar,
            text="Studio UI Edition",
            font=self.fonts["small"],
            text_color=self.palette["muted"],
        )
        subtitle.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        status_frame = ctk.CTkFrame(
            self.sidebar,
            fg_color=self.palette["card"],
            corner_radius=12,
            border_width=1,
            border_color=self.palette["border"],
        )
        status_frame.grid(row=2, column=0, padx=20, pady=(0, 16), sticky="ew")

        status_title = ctk.CTkLabel(
            status_frame,
            text="状态",
            font=self.fonts["section"],
            text_color=self.palette["text"],
        )
        status_title.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="w")

        self.status_chip = ctk.CTkLabel(
            status_frame,
            text="就绪",
            font=self.fonts["body"],
            text_color="#FFFFFF",
            fg_color=self.palette["success"],
            corner_radius=8,
        )
        self.status_chip.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")

        stat_frame = ctk.CTkFrame(
            self.sidebar,
            fg_color=self.palette["card"],
            corner_radius=12,
            border_width=1,
            border_color=self.palette["border"],
        )
        stat_frame.grid(row=3, column=0, padx=20, pady=(0, 16), sticky="ew")

        stat_title = ctk.CTkLabel(
            stat_frame,
            text="任务概览",
            font=self.fonts["section"],
            text_color=self.palette["text"],
        )
        stat_title.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="w")

        self.pending_label = ctk.CTkLabel(
            stat_frame,
            text="待执行: 0",
            font=self.fonts["body"],
            text_color=self.palette["text"],
        )
        self.pending_label.grid(row=1, column=0, padx=16, pady=(0, 4), sticky="w")

        self.total_label = ctk.CTkLabel(
            stat_frame,
            text="已录入: 0",
            font=self.fonts["body"],
            text_color=self.palette["muted"],
        )
        self.total_label.grid(row=2, column=0, padx=16, pady=(0, 12), sticky="w")

        hint_frame = ctk.CTkFrame(
            self.sidebar,
            fg_color=self.palette["card"],
            corner_radius=12,
            border_width=1,
            border_color=self.palette["border"],
        )
        hint_frame.grid(row=4, column=0, padx=20, pady=(0, 16), sticky="ew")

        hint_title = ctk.CTkLabel(
            hint_frame,
            text="操作提示",
            font=self.fonts["section"],
            text_color=self.palette["text"],
        )
        hint_title.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="w")

        hint_text = ctk.CTkLabel(
            hint_frame,
            text="先保存Cookies与Profile ID，再添加任务并启动。",
            font=self.fonts["small"],
            text_color=self.palette["muted"],
            wraplength=200,
            justify="left",
        )
        hint_text.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")
    def build_main(self):
        self.main = ctk.CTkFrame(self.root, fg_color=self.palette["bg"])
        self.main.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)

        self.main.grid_columnconfigure(0, weight=1, uniform="col")
        self.main.grid_columnconfigure(1, weight=1, uniform="col")
        self.main.grid_rowconfigure(0, weight=0)
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_rowconfigure(2, weight=0)

        self.build_settings_card()
        self.build_tasks_card()
        self.build_log_card()
        self.build_control_card()

    def build_card(self, parent, title, subtitle=None):
        card = ctk.CTkFrame(
            parent,
            fg_color=self.palette["card"],
            corner_radius=16,
            border_width=1,
            border_color=self.palette["border"],
        )
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.grid(row=0, column=0, padx=20, pady=(16, 10), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            header,
            text=title,
            font=self.fonts["section"],
            text_color=self.palette["text"],
        )
        title_label.grid(row=0, column=0, sticky="w")

        if subtitle:
            subtitle_label = ctk.CTkLabel(
                header,
                text=subtitle,
                font=self.fonts["small"],
                text_color=self.palette["muted"],
            )
            subtitle_label.grid(row=1, column=0, sticky="w")

        return card, header

    def build_settings_card(self):
        card, _ = self.build_card(self.main, "账户设置", "填入认证信息后保存")
        card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))

        form_frame = ctk.CTkFrame(card, fg_color="transparent")
        form_frame.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="ew")
        form_frame.grid_columnconfigure(1, weight=1)

        cookies_label = ctk.CTkLabel(
            form_frame,
            text="Cookies",
            font=self.fonts["body"],
            text_color=self.palette["text"],
        )
        cookies_label.grid(row=0, column=0, padx=(0, 12), pady=8, sticky="w")

        self.cookies_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="粘贴Cookies...",
            height=36,
            fg_color="#FFFFFF",
            border_color=self.palette["border"],
            text_color=self.palette["text"],
        )
        self.cookies_entry.grid(row=0, column=1, padx=(0, 12), pady=8, sticky="ew")

        self.fetch_cookies_btn = ctk.CTkButton(
            form_frame,
            text="浏览器获取",
            command=self.fetch_cookies_via_browser,
            height=36,
            width=110,
            fg_color=self.palette["primary"],
            hover_color=self.palette["primary_hover"],
            text_color="#FFFFFF",
        )
        self.fetch_cookies_btn.grid(row=0, column=2, pady=8, sticky="w")

        profile_label = ctk.CTkLabel(
            form_frame,
            text="Profile ID",
            font=self.fonts["body"],
            text_color=self.palette["text"],
        )
        profile_label.grid(row=1, column=0, padx=(0, 12), pady=8, sticky="w")

        self.profile_id_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="例如: 11045",
            height=36,
            fg_color="#FFFFFF",
            border_color=self.palette["border"],
            text_color=self.palette["text"],
            width=200,
        )
        self.profile_id_entry.grid(row=1, column=1, padx=(0, 12), pady=8, sticky="w")

        open_time_label = ctk.CTkLabel(
            form_frame,
            text="开放时间",
            font=self.fonts["body"],
            text_color=self.palette["text"],
        )
        open_time_label.grid(row=2, column=0, padx=(0, 12), pady=8, sticky="w")

        self.open_time_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="格式: YYYY-MM-DD HH:MM",
            height=36,
            fg_color="#FFFFFF",
            border_color=self.palette["border"],
            text_color=self.palette["text"],
            width=200,
        )
        self.open_time_entry.grid(row=2, column=1, padx=(0, 12), pady=8, sticky="w")

        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=2, column=0, padx=20, pady=(0, 16), sticky="w")

        save_btn = ctk.CTkButton(
            actions,
            text="保存设置",
            command=self.save_settings,
            height=36,
            fg_color=self.palette["primary"],
            hover_color=self.palette["primary_hover"],
            text_color="#FFFFFF",
        )
        save_btn.pack(side="left", padx=(0, 10))

        export_btn = ctk.CTkButton(
            actions,
            text="导出配置",
            command=self.export_config,
            height=36,
            fg_color="transparent",
            text_color=self.palette["text"],
            border_width=1,
            border_color=self.palette["border"],
        )
        export_btn.pack(side="left", padx=(0, 10))

        import_btn = ctk.CTkButton(
            actions,
            text="导入配置",
            command=self.import_config,
            height=36,
            fg_color="transparent",
            text_color=self.palette["text"],
            border_width=1,
            border_color=self.palette["border"],
        )
        import_btn.pack(side="left")
    def build_tasks_card(self):
        card, header = self.build_card(self.main, "任务清单", "支持选课与换课任务")
        card.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")

        add_btn = ctk.CTkButton(
            btn_frame,
            text="新增任务",
            command=self.add_task,
            height=32,
            fg_color=self.palette["primary"],
            hover_color=self.palette["primary_hover"],
            text_color="#FFFFFF",
        )
        add_btn.pack(side="left", padx=6)

        delete_btn = ctk.CTkButton(
            btn_frame,
            text="删除",
            command=self.delete_task,
            height=32,
            fg_color="transparent",
            text_color=self.palette["text"],
            border_width=1,
            border_color=self.palette["border"],
        )
        delete_btn.pack(side="left", padx=6)

        clear_btn = ctk.CTkButton(
            btn_frame,
            text="清空",
            command=self.clear_tasks,
            height=32,
            fg_color="transparent",
            text_color=self.palette["text"],
            border_width=1,
            border_color=self.palette["border"],
        )
        clear_btn.pack(side="left", padx=6)

        tree_frame = ctk.CTkFrame(card, fg_color="transparent")
        tree_frame.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        columns = ("elect_course", "withdraw_course", "status")
        self.task_tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            height=8,
            selectmode="extended",
            style="Studio.Treeview",
        )
        self.task_tree.heading("elect_course", text="要选课程")
        self.task_tree.heading("withdraw_course", text="要退课程")
        self.task_tree.heading("status", text="状态")
        self.task_tree.column("elect_course", width=280)
        self.task_tree.column("withdraw_course", width=280)
        self.task_tree.column("status", width=80)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=scrollbar.set)

        self.task_tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

    def build_log_card(self):
        card, header = self.build_card(self.main, "运行日志", "实时记录执行过程")
        card.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)

        clear_btn = ctk.CTkButton(
            header,
            text="清空日志",
            command=self.clear_log,
            height=32,
            fg_color="transparent",
            text_color=self.palette["text"],
            border_width=1,
            border_color=self.palette["border"],
        )
        clear_btn.grid(row=0, column=1, sticky="e")

        self.log_textbox = ctk.CTkTextbox(
            card,
            font=self.fonts["mono"],
            fg_color="#FFFFFF",
            text_color=self.palette["text"],
            border_width=1,
            border_color=self.palette["border"],
            wrap="word",
        )
        self.log_textbox.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="nsew")
    def build_control_card(self):
        card, _ = self.build_card(self.main, "控制中心", "开始或停止任务执行")
        card.grid(row=2, column=0, columnspan=2, sticky="ew")

        action_frame = ctk.CTkFrame(card, fg_color="transparent")
        action_frame.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="ew")
        action_frame.grid_columnconfigure(3, weight=1)

        self.start_btn = ctk.CTkButton(
            action_frame,
            text="开始选课",
            command=self.start_election,
            height=44,
            fg_color=self.palette["accent"],
            hover_color=self.palette["accent_hover"],
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Fira Sans", size=15, weight="bold"),
        )
        self.start_btn.grid(row=0, column=0, padx=(0, 12), pady=6, sticky="w")

        self.rush_btn = ctk.CTkButton(
            action_frame,
            text="抢课模式",
            command=self.start_rush_mode,
            height=44,
            fg_color=self.palette["danger"],
            hover_color="#B91C1C",
            text_color="#FFFFFF",
            font=ctk.CTkFont(family="Fira Sans", size=15, weight="bold"),
        )
        self.rush_btn.grid(row=0, column=1, padx=(0, 12), pady=6, sticky="w")

        self.stop_btn = ctk.CTkButton(
            action_frame,
            text="停止选课",
            command=self.stop_election,
            height=44,
            fg_color="transparent",
            text_color=self.palette["text"],
            border_width=1,
            border_color=self.palette["border"],
            state="disabled",
            font=ctk.CTkFont(family="Fira Sans", size=15, weight="bold"),
        )
        self.stop_btn.grid(row=0, column=2, padx=(0, 12), pady=6, sticky="w")

        self.status_label = ctk.CTkLabel(
            action_frame,
            text="状态: 就绪",
            font=self.fonts["body"],
            text_color=self.palette["text"],
        )
        self.status_label.grid(row=0, column=3, padx=10, sticky="e")

    def update_task_stats(self):
        total = len(self.task_list)
        pending = len([task for task in self.task_list if task.get("status") != "已完成"])
        self.pending_label.configure(text=f"待执行: {pending}")
        self.total_label.configure(text=f"已录入: {total}")

    def set_status(self, text: str, color: str):
        self.status_chip.configure(text=text, fg_color=color)
        self.status_label.configure(text=f"状态: {text}")

    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] [{level}] {message}\n"
        self.log_textbox.insert("end", log_message)
        self.log_textbox.see("end")
        with open("course_selector.log", "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [{level}] {message}\n")

    def fetch_cookies_via_browser(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            messagebox.showerror(
                "缺少依赖",
                "未安装 playwright。\n请在命令行运行：\n  pip install playwright\n  playwright install chromium",
            )
            return

        btn = self.fetch_cookies_btn
        btn.configure(state="disabled", text="获取中...")
        self.log("启动浏览器以获取 Cookies...", "INFO")

        login_success_url = "portal.sufe.edu.cn"
        elect_url = "https://eams.sufe.edu.cn/eams/stdElectCourse.action"
        timeout_seconds = 300

        def worker():
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=False)
                    context = browser.new_context()
                    page = context.new_page()
                    page.goto("https://login.sufe.edu.cn")

                    deadline = time.time() + timeout_seconds
                    logged_in = False
                    while time.time() < deadline:
                        try:
                            if login_success_url in page.url:
                                logged_in = True
                                break
                        except Exception:
                            pass
                        page.wait_for_timeout(500)

                    if not logged_in:
                        browser.close()
                        self.root.after(0, lambda: self.log("获取 Cookies 超时（5分钟内未完成登录）", "WARN"))
                        self.root.after(0, lambda: messagebox.showwarning("超时", "5分钟内未检测到登录完成，请重试"))
                        return

                    self.root.after(0, lambda: self.log("检测到登录成功，跳转到选课页面...", "SUCCESS"))
                    page.goto(elect_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(1500)

                    cookies = context.cookies()
                    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

                    profile_id = page.evaluate(
                        "() => {"
                        "  const btn = document.getElementById('electCourseButton');"
                        "  if (!btn) return null;"
                        "  const m = btn.getAttribute('onclick').match(/toStdElectCourse\\((\\d+)\\)/);"
                        "  return m ? m[1] : null;"
                        "}"
                    )

                    browser.close()

                    self.root.after(0, lambda: self._fill_cookies(cookie_str, profile_id))
            except Exception as exc:
                err = str(exc)
                self.root.after(0, lambda: self.log(f"获取 Cookies 失败: {err}", "ERROR"))
                if "Executable doesn't exist" in err or "playwright install" in err.lower():
                    msg = "Playwright 浏览器未安装。\n请运行：\n  playwright install chromium"
                else:
                    msg = f"获取 Cookies 失败: {err}"
                self.root.after(0, lambda: messagebox.showerror("错误", msg))
            finally:
                self.root.after(0, lambda: btn.configure(state="normal", text="浏览器获取"))

        threading.Thread(target=worker, daemon=True).start()

    def _fill_cookies(self, cookie_str: str, profile_id: str | None = None):
        self.cookies_entry.delete(0, "end")
        self.cookies_entry.insert(0, cookie_str)
        self.log("Cookies 已自动获取并填入", "SUCCESS")

        if profile_id:
            self.profile_id_entry.delete(0, "end")
            self.profile_id_entry.insert(0, profile_id)
            self.log(f"Profile ID 已自动获取并填入: {profile_id}", "SUCCESS")
            messagebox.showinfo("成功", "Cookies 与 Profile ID 已自动获取并填入，请点击保存设置")
        else:
            self.log("未能从选课页面提取到 Profile ID，请手动填写", "WARN")
            messagebox.showinfo("成功", "Cookies 已自动获取并填入；Profile ID 未能获取，请手动填写后保存设置")

    def save_settings(self):
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
        except Exception as exc:
            self.log(f"保存设置失败: {str(exc)}", "ERROR")
            messagebox.showerror("错误", f"保存设置失败: {str(exc)}")

    def export_config(self):
        try:
            config = {
                "cookies": self.cookies_entry.get().strip(),
                "profile_id": self.profile_id_entry.get().strip(),
                "task_list": self.task_list,
                "export_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            default_filename = f"选课配置_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            file_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
                initialfile=default_filename,
                title="导出配置",
            )

            if file_path:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                self.log(f"配置已导出到: {file_path}", "SUCCESS")
                messagebox.showinfo("成功", "配置已导出")
        except Exception as exc:
            self.log(f"导出配置失败: {str(exc)}", "ERROR")
            messagebox.showerror("错误", f"导出配置失败: {str(exc)}")

    def import_config(self):
        try:
            file_path = filedialog.askopenfilename(
                filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
                title="导入配置",
            )
            if not file_path:
                return

            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            if "cookies" not in config or "profile_id" not in config:
                messagebox.showerror("错误", "配置文件格式不正确")
                return

            self.cookies_entry.delete(0, "end")
            self.cookies_entry.insert(0, config["cookies"])
            self.profile_id_entry.delete(0, "end")
            self.profile_id_entry.insert(0, config["profile_id"])

            if "task_list" in config:
                self.task_list = config["task_list"]
                self.refresh_task_list()

            export_time = config.get("export_time", "未知")
            self.log(f"配置已导入(导出时间: {export_time})", "SUCCESS")
            if messagebox.askyesno("导入成功", "配置已导入，是否立即保存设置？"):
                self.save_settings()
        except json.JSONDecodeError:
            messagebox.showerror("错误", "配置文件格式错误，无法解析JSON")
        except Exception as exc:
            self.log(f"导入配置失败: {str(exc)}", "ERROR")
            messagebox.showerror("错误", f"导入配置失败: {str(exc)}")
    def add_task(self):
        dialog = StudioTaskDialog(self.root, self.selector, self.palette, self.fonts)
        self.root.wait_window(dialog.dialog)
        if dialog.result:
            elect_id, withdraw_id = dialog.result
            self.task_list.append(
                {"elect_id": elect_id, "withdraw_id": withdraw_id, "status": "等待中"}
            )
            self.refresh_task_list()
            detail = self.selector.get_course_full_info(elect_id)
            withdraw_detail = self.selector.get_course_full_info(withdraw_id) if withdraw_id else ""
            message = f"添加任务: 选 {detail}"
            if withdraw_detail:
                message += f" / 退 {withdraw_detail}"
            self.log(message, "SUCCESS")

    def delete_task(self):
        selected = self.task_tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先选择要删除的任务")
            return

        if messagebox.askyesno("确认", f"确定要删除选中的 {len(selected)} 个任务吗？"):
            indices = [self.task_tree.index(item) for item in selected]
            for index in sorted(indices, reverse=True):
                del self.task_list[index]
            self.refresh_task_list()
            self.log(f"已删除 {len(selected)} 个任务", "SUCCESS")

    def clear_tasks(self):
        if messagebox.askyesno("确认", "确定要清空所有任务吗？"):
            self.task_list.clear()
            self.refresh_task_list()
            self.log("已清空任务列表", "SUCCESS")

    def refresh_task_list(self):
        for item in self.task_tree.get_children():
            self.task_tree.delete(item)

        for task in self.task_list:
            elect_info = self.selector.get_course_full_info(task["elect_id"])
            withdraw_info = (
                self.selector.get_course_full_info(task["withdraw_id"])
                if task["withdraw_id"]
                else "无"
            )
            status = task["status"]
            self.task_tree.insert("", tk.END, values=(elect_info, withdraw_info, status))

        self.update_task_stats()

    def clear_log(self):
        self.log_textbox.delete("0.0", "end")
        self.log("日志已清空", "INFO")

    def start_election(self):
        if not self.selector.cookies or not self.selector.profile_id:
            messagebox.showerror("错误", "请先保存设置")
            return

        if not self.task_list:
            messagebox.showerror("错误", "请先添加选课任务")
            return

        self.selector.is_running = True
        self.start_btn.configure(state="disabled")
        self.rush_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.set_status("运行中", self.palette["warn"])

        self.log("=" * 50)
        self.log("开始选课", "SUCCESS")
        self.log("=" * 50)

        self.selector.elect_thread = threading.Thread(target=self.run_election, daemon=True)
        self.selector.elect_thread.start()

    def stop_election(self):
        self.selector.is_running = False
        self.start_btn.configure(state="normal")
        self.rush_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.set_status("已停止", self.palette["danger"])
        self.log("用户停止选课", "WARN")

    def start_rush_mode(self):
        if not self.selector.cookies:
            messagebox.showerror("错误", "请先通过浏览器获取并保存 Cookies")
            return

        if not self.task_list:
            messagebox.showerror("错误", "请先添加选课任务")
            return

        open_time_str = self.open_time_entry.get().strip()
        if not open_time_str:
            messagebox.showerror("错误", "请输入系统开放时间")
            return

        try:
            open_dt = datetime.strptime(open_time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            messagebox.showerror("错误", "开放时间格式错误，请按 YYYY-MM-DD HH:MM 填写")
            return

        if open_dt <= datetime.now():
            messagebox.showerror("错误", "开放时间已过，请确认时间或直接点击开始选课")
            return

        self.selector.is_running = True
        self.start_btn.configure(state="disabled")
        self.rush_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.set_status("抢课中", self.palette["danger"])

        self.log("=" * 50)
        self.log(f"启动抢课模式，目标开放时间: {open_dt.strftime('%Y-%m-%d %H:%M')}", "SUCCESS")
        self.log("=" * 50)

        self.selector.elect_thread = threading.Thread(
            target=self.run_rush_mode, args=(open_dt,), daemon=True
        )
        self.selector.elect_thread.start()

    def run_rush_mode(self, open_dt):
        elect_url = "https://eams.sufe.edu.cn/eams/stdElectCourse.action"
        profile_pattern = re.compile(r"toStdElectCourse\((\d+)\)")

        try:
            last_warn_session = 0.0
            while self.selector.is_running:
                now = datetime.now()
                remain = (open_dt - now).total_seconds()

                if remain > 60:
                    interval = 30.0
                elif remain > 20:
                    interval = 5.0
                else:
                    interval = 0.8

                try:
                    req = requests.get(
                        elect_url, cookies=self.selector.cookies, timeout=10
                    )
                    text = req.text
                    match = profile_pattern.search(text)
                    if match:
                        profile_id = match.group(1)
                        self.root.after(0, lambda pid=profile_id: self._on_profile_acquired(pid))
                        return

                    if "login" in req.url.lower() or "login" in (req.text[:500]).lower():
                        if time.time() - last_warn_session > 60:
                            self.log("Cookies 可能已过期，建议重新获取", "WARN")
                            last_warn_session = time.time()
                except Exception as exc:
                    self.log(f"刷新请求异常: {str(exc)}", "WARN")

                if remain <= 0:
                    self.log("已到开放时间，持续刷新等待 Profile ID...", "INFO")
                else:
                    self.log(f"距开放 {int(remain)}s，刷新中（间隔 {interval}s）", "INFO")

                slept = 0.0
                while slept < interval and self.selector.is_running:
                    step = min(0.2, interval - slept)
                    time.sleep(step)
                    slept += step
        except Exception as exc:
            self.log(f"抢课模式异常: {str(exc)}", "ERROR")
            self.root.after(0, lambda: self.start_btn.configure(state="normal"))
            self.root.after(0, lambda: self.rush_btn.configure(state="normal"))
            self.root.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.root.after(0, lambda: self.set_status("错误", self.palette["danger"]))
            self.root.after(
                0, lambda: messagebox.showerror("错误", f"抢课模式异常: {str(exc)}")
            )

    def _on_profile_acquired(self, profile_id: str):
        self.profile_id_entry.delete(0, "end")
        self.profile_id_entry.insert(0, profile_id)
        self.selector.profile_id = profile_id
        self.log("=" * 50)
        self.log(f"已获取 Profile ID: {profile_id}，自动开始选课", "SUCCESS")
        self.log("=" * 50)
        self.start_election()
    def run_election(self):
        try:
            while self.selector.is_running and self.task_list:
                self.log("正在获取课程限额信息...")
                lesson_limit = self.selector.get_lesson_limit()
                if not lesson_limit:
                    self.log("获取课程限额失败，5秒后重试...", "WARN")
                    time.sleep(5)
                    continue

                self.log(f"成功获取 {len(lesson_limit)} 门课程的限额信息", "SUCCESS")
                with open("lesson_limit_debug.json", "w", encoding="utf-8") as f:
                    json.dump(lesson_limit, f, ensure_ascii=False, indent=4)

                completed_tasks = []
                for i, task in enumerate(self.task_list):
                    if not self.selector.is_running:
                        break

                    elect_id = task["elect_id"]
                    withdraw_id = task["withdraw_id"]

                    if elect_id not in lesson_limit:
                        self.log(
                            f"课程 {self.selector.get_course_full_info(elect_id)} 不在限额列表中",
                            "WARN",
                        )
                        continue

                    sc, lc = lesson_limit[elect_id]
                    self.log(f"课程 {self.selector.get_course_name(elect_id)}: {sc}/{lc}")

                    if sc < lc:
                        self.log(f"课程 {self.selector.get_course_name(elect_id)} 有空位，开始选课...")
                        response = self.selector.operate_lessons(elect_id, withdraw_id)

                        with open("operateLessons_debug.txt", "a", encoding="utf-8") as f:
                            f.write(f"\n\n=== {datetime.now()} ===\n")
                            f.write(f"选课ID: {elect_id}, 退课ID: {withdraw_id}\n")
                            f.write(f"响应: {response}\n")

                        self.log(f"选课响应: {response}")
                        task["status"] = "已完成"
                        completed_tasks.append(i)
                        self.root.after(0, self.refresh_task_list)
                        self.log(
                            f"成功处理: {self.selector.get_course_name(elect_id)}",
                            "SUCCESS",
                        )
                    else:
                        task["status"] = "已满"
                        self.root.after(0, self.refresh_task_list)

                for i in reversed(completed_tasks):
                    del self.task_list[i]

                if not self.task_list:
                    self.log("所有任务已完成", "SUCCESS")
                    break

                time.sleep(0.5)

            self.root.after(0, lambda: self.start_btn.configure(state="normal"))
            self.root.after(0, lambda: self.rush_btn.configure(state="normal"))
            self.root.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.root.after(0, lambda: self.set_status("就绪", self.palette["success"]))

            if not self.task_list:
                self.log("=" * 50)
                self.log("选课任务全部完成", "SUCCESS")
                self.log("=" * 50)
                self.root.after(0, lambda: messagebox.showinfo("完成", "选课任务全部完成"))
        except Exception as exc:
            self.log(f"选课过程中发生错误: {str(exc)}", "ERROR")
            with open("error_log.txt", "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now()}] {str(exc)}\n")
            self.root.after(0, lambda: self.start_btn.configure(state="normal"))
            self.root.after(0, lambda: self.rush_btn.configure(state="normal"))
            self.root.after(0, lambda: self.stop_btn.configure(state="disabled"))
            self.root.after(0, lambda: self.set_status("错误", self.palette["danger"]))
            self.root.after(
                0,
                lambda: messagebox.showerror("错误", f"选课过程中发生错误: {str(exc)}"),
            )

    def run(self):
        self.log("欢迎使用上财选课系统", "SUCCESS")
        self.log("请先在账户设置中输入Cookies和Profile ID")
        self.root.mainloop()


class StudioTaskDialog:
    """添加任务对话框"""

    def __init__(self, parent, selector, palette=None, fonts=None):
        self.selector = selector
        self.result = None

        self.palette = palette or {
            "bg": "#F0FDFA",
            "card": "#F8FFFE",
            "border": "#A7F3D0",
            "text": "#134E4A",
            "muted": "#2C7A7B",
            "primary": "#0D9488",
            "primary_hover": "#0F766E",
        }
        self.fonts = fonts or {
            "title": ctk.CTkFont(family="Fira Sans", size=20, weight="bold"),
            "section": ctk.CTkFont(family="Fira Sans", size=16, weight="bold"),
            "body": ctk.CTkFont(family="Fira Sans", size=13),
            "small": ctk.CTkFont(family="Fira Sans", size=12),
        }

        dialog_w, dialog_h = 640, 520
        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title("添加选课任务")
        self.dialog.geometry(f"{dialog_w}x{dialog_h}")
        self.dialog.minsize(560, 480)
        self.dialog.configure(fg_color=self.palette["bg"])
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (dialog_w // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (dialog_h // 2)
        self.dialog.geometry(f"+{x}+{y}")

        header = ctk.CTkFrame(self.dialog, fg_color="transparent")
        header.pack(fill="x", padx=30, pady=(24, 12))

        title = ctk.CTkLabel(
            header,
            text="添加选课任务",
            font=self.fonts["title"],
            text_color=self.palette["text"],
        )
        title.pack(anchor="w")

        subtitle = ctk.CTkLabel(
            header,
            text="填写课程 ID 后点击确定加入任务清单",
            font=self.fonts["small"],
            text_color=self.palette["muted"],
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        # 按钮行先以 side="bottom" 占位，保证无论内容多高都始终可见
        btn_frame = ctk.CTkFrame(self.dialog, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=30, pady=(0, 20))

        content_frame = ctk.CTkFrame(
            self.dialog,
            fg_color=self.palette["card"],
            corner_radius=16,
            border_width=1,
            border_color=self.palette["border"],
        )
        content_frame.pack(padx=30, pady=(0, 16), fill="both", expand=True)

        type_label = ctk.CTkLabel(
            content_frame,
            text="任务类型",
            font=self.fonts["section"],
            text_color=self.palette["text"],
        )
        type_label.pack(anchor="w", padx=20, pady=(20, 8))

        self.task_type = tk.StringVar(value="elect")
        type_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        type_frame.pack(anchor="w", padx=20)

        elect_radio = ctk.CTkRadioButton(
            type_frame,
            text="选课",
            variable=self.task_type,
            value="elect",
            font=self.fonts["body"],
            text_color=self.palette["text"],
            fg_color=self.palette["primary"],
            hover_color=self.palette["primary_hover"],
            border_color=self.palette["border"],
        )
        elect_radio.pack(side="left", padx=(0, 20))

        exchange_radio = ctk.CTkRadioButton(
            type_frame,
            text="换课",
            variable=self.task_type,
            value="exchange",
            font=self.fonts["body"],
            text_color=self.palette["text"],
            fg_color=self.palette["primary"],
            hover_color=self.palette["primary_hover"],
            border_color=self.palette["border"],
        )
        exchange_radio.pack(side="left")

        elect_label = ctk.CTkLabel(
            content_frame,
            text="要选的课程ID",
            font=self.fonts["body"],
            text_color=self.palette["text"],
        )
        elect_label.pack(anchor="w", padx=20, pady=(20, 6))

        self.elect_entry = ctk.CTkEntry(
            content_frame,
            placeholder_text="输入课程ID",
            height=40,
            fg_color="#FFFFFF",
            border_color=self.palette["border"],
            text_color=self.palette["text"],
        )
        self.elect_entry.pack(fill="x", padx=20, pady=(0, 10))

        withdraw_label = ctk.CTkLabel(
            content_frame,
            text="要退的课程ID (换课时必填)",
            font=self.fonts["body"],
            text_color=self.palette["text"],
        )
        withdraw_label.pack(anchor="w", padx=20, pady=(10, 6))

        self.withdraw_entry = ctk.CTkEntry(
            content_frame,
            placeholder_text="输入要退的课程ID",
            height=40,
            fg_color="#FFFFFF",
            border_color=self.palette["border"],
            text_color=self.palette["text"],
        )
        self.withdraw_entry.pack(fill="x", padx=20, pady=(0, 10))

        hint_label = ctk.CTkLabel(
            content_frame,
            text="提示: 选课只需填写要选课程ID，换课需要同时填写要选和要退课程ID。",
            font=self.fonts["small"],
            text_color=self.palette["muted"],
            wraplength=520,
            justify="left",
        )
        hint_label.pack(anchor="w", padx=20, pady=(10, 16))

        ok_btn = ctk.CTkButton(
            btn_frame,
            text="确定",
            command=self.ok,
            width=140,
            height=40,
            fg_color=self.palette["primary"],
            hover_color=self.palette["primary_hover"],
            text_color="#FFFFFF",
            font=self.fonts["body"],
        )
        ok_btn.pack(side="right", padx=(10, 0))

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="取消",
            command=self.cancel,
            width=140,
            height=40,
            fg_color="transparent",
            border_width=1,
            border_color=self.palette["border"],
            text_color=self.palette["text"],
            font=self.fonts["body"],
        )
        cancel_btn.pack(side="right", padx=(0, 0))

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
    app = StudioCourseSelectorGUI()
    app.run()


if __name__ == "__main__":
    main()
