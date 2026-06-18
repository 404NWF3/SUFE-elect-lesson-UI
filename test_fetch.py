"""
快速测试脚本：检查课程信息获取功能
"""
import requests
import re

# 请填入你的cookies和课程ID
COOKIES_STR = ""  # 从浏览器复制你的cookies字符串
LESSON_ID = "406985"  # 你要测试的课程ID

def trans_cookies(cookies_str):
    """转换cookies字符串为字典"""
    cookies_dict = {}
    for cookie in cookies_str.split(';'):
        if '=' in cookie:
            key, value = cookie.split('=', 1)
            cookies_dict[key.strip()] = value.strip()
    return cookies_dict

def test_fetch():
    if not COOKIES_STR:
        print("❌ 请先在脚本中填入 COOKIES_STR")
        return

    cookies = trans_cookies(COOKIES_STR)
    url = f"https://eams.sufe.edu.cn/eams/allTeachTaskSearch!info.action?removeBack=1&lesson.id={LESSON_ID}"

    print(f"📡 测试获取课程 {LESSON_ID} 的信息...")
    print(f"URL: {url}")
    print(f"Cookies: {list(cookies.keys())}")
    print()

    try:
        req = requests.get(url, cookies=cookies, timeout=10)
        print(f"✓ HTTP请求成功")
        print(f"状态码: {req.status_code}")
        print(f"响应长度: {len(req.text)} 字符")
        print()

        # 保存HTML
        with open(f"test_lesson_{LESSON_ID}.html", "w", encoding="utf-8") as f:
            f.write(req.text)
        print(f"✓ HTML已保存到: test_lesson_{LESSON_ID}.html")
        print()

        # 尝试解析
        html_text = req.text

        # 解析课程名称
        name_match = re.search(r'<td\s+class="title"[^>]*>课程名称:</td>\s*<td[^>]*>\s*([^<]+)', html_text)
        if name_match:
            course_name = name_match.group(1).strip()
            course_name = re.sub(r'&nbsp;', '', course_name).strip()
            print(f"✓ 课程名称: {course_name}")
        else:
            print("❌ 未找到课程名称")
            # 打印前1000个字符看看HTML结构
            print("\nHTML前1000字符:")
            print(html_text[:1000])

        # 解析教师
        teacher_match = re.search(r'<td\s+class="title">教师:</td>\s*<td\s+class="content"[^>]*>([^<]+)', html_text)
        if teacher_match:
            teacher_name = teacher_match.group(1).strip()
            print(f"✓ 教师: {teacher_name}")
        else:
            print("❌ 未找到教师信息")

    except requests.exceptions.Timeout:
        print("❌ 请求超时")
    except requests.exceptions.RequestException as e:
        print(f"❌ HTTP请求失败: {e}")
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fetch()
