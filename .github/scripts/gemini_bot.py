import os
import sys
import json
import subprocess
import logging
import traceback
import time
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from github import Github, Auth
from tenacity import retry, stop_after_attempt, wait_exponential

# --- 配置日志 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("DandelionBot")

# --- 全局配置 ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = os.environ.get("REPO_NAME")
ISSUE_NUMBER = int(os.environ.get("ISSUE_NUMBER", "0")) 
PROMPT_CONTENT = os.environ.get("PROMPT_CONTENT", "")
RUN_ID = os.environ.get("RUN_ID", "N/A")
TRIGGERS = ["/gemini", "/丹德莱"]

# 模型配置
MODEL_NAME = "gemini-2.5-flash" 

class Intent(str, Enum):
    CHAT = "chat"
    CODE = "code"

@dataclass
class BotResponse:
    intent: Intent
    reply_text: str
    changes: List[Dict[str, str]] = None

class GithubClient:
    def __init__(self):
        self.auth = Auth.Token(GITHUB_TOKEN)
        self.g = Github(auth=self.auth)
        self.repo = self.g.get_repo(REPO_NAME)
        self.issue = self.repo.get_issue(ISSUE_NUMBER)
        self.active_comment = None # 用于存储当前运行周期的唯一评论对象

    def init_comment(self, body: str):
        """初始化评论：创建第一条评论"""
        try:
            self.active_comment = self.issue.create_comment(body)
            logger.info(f"Initial comment created. ID: {self.active_comment.id}")
        except Exception as e:
            logger.error(f"Failed to create initial comment: {e}")

    def update_comment(self, body: str):
        """更新评论：编辑已存在的评论，实现状态流转效果"""
        try:
            if self.active_comment:
                self.active_comment.edit(body)
                logger.info("Comment updated.")
            else:
                # 如果因为某种原因没有初始评论，则新建一个
                self.init_comment(body)
        except Exception as e:
            logger.error(f"Failed to update comment: {e}")
            # 如果更新失败（例如被删除了），尝试发新的
            self.init_comment(body)

    def create_pr(self, branch_name: str, title: str, body: str) -> str:
        """创建 PR 并返回 URL"""
        try:
            # 注意：在组织仓库中，head 参数通常就是 branch_name (如果分支在同一个仓库)
            # 如果是 Fork 模式，则需要 'username:branch_name'
            # 这里假设 Action 有权限直接推送到当前仓库
            pr = self.repo.create_pull(
                title=title,
                body=body,
                head=branch_name,
                base="main" 
            )
            return pr.html_url
        except Exception as e:
            logger.error(f"Failed to create PR: {e}")
            raise

class GeminiAgent:
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        self.model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            safety_settings=self.safety_settings
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    def generate_content(self, prompt: str, json_mode: bool = False) -> str:
        generation_config = genai.types.GenerationConfig(
            temperature=0.2,
            response_mime_type="application/json" if json_mode else "text/plain"
        )
        
        try:
            response = self.model.generate_content(
                prompt, 
                generation_config=generation_config
            )
            return response.text
        except ValueError as e:
            logger.error(f"Gemini Error (Safety/Blocked?): {e}")
            raise RuntimeError("Neural cloud connection refused (Safety Block).")
        except Exception as e:
            logger.error(f"Gemini API Call Failed: {e}")
            raise

class ProjectManager:
    def __init__(self, root_dir="."):
        self.root_dir = root_dir
        self.exclude_dirs = {'.git', '.github', '__pycache__', 'site', 'venv', 'node_modules', 'assets', 'pic', 'mk'}
        self.exclude_exts = ('.png', '.jpg', '.jpeg', '.gif', '.pdf', '.pyc', '.exe', '.zip')

    def get_file_tree(self) -> List[str]:
        file_paths = []
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for file in files:
                if not file.endswith(self.exclude_exts):
                    path = os.path.join(root, file)
                    if path.startswith("./"):
                        path = path[2:]
                    file_paths.append(path)
        return file_paths

    def read_files(self, file_paths: List[str]) -> str:
        content_block = ""
        for path in file_paths:
            if ".." in path or path.startswith("/"): continue
            if not os.path.exists(path): continue
                
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if len(content) > 30000:
                        content = content[:30000] + "\n...(truncated)..."
                    content_block += f"--- FILE: {path} ---\n{content}\n--- END FILE ---\n\n"
            except Exception as e:
                logger.warning(f"Could not read {path}: {e}")
        return content_block

    def apply_changes(self, changes: List[Dict[str, str]]) -> List[str]:
        modified_files = []
        for change in changes:
            path = change.get('path')
            content = change.get('content')
            if not path or content is None: continue
            
            if path.startswith("./"): path = path[2:]
            if path.startswith("/"): path = path[1:]
            
            dir_name = os.path.dirname(path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
                
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
            modified_files.append(path)
        return modified_files

def run_git_cmd(cmd):
    subprocess.run(cmd, shell=True, check=True)

def main():
    # 0. 初始化检查
    if not PROMPT_CONTENT:
        sys.exit(0)

    active_trigger = None
    for trigger in TRIGGERS:
        if trigger in PROMPT_CONTENT:
            active_trigger = trigger
            break
    
    if not active_trigger:
        sys.exit(0)

    user_request = PROMPT_CONTENT.replace(active_trigger, "").strip()
    
    try:
        gh_client = GithubClient()
        pm = ProjectManager()
        agent = GeminiAgent()
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        sys.exit(1)

    # --- 丹德莱风格的进度条模板 ---
    def get_status_msg(status_text, detail_text=""):
        return f"""
💠 **OGAS Protocol Activated**

> {user_request}

---
📡 **Status**: `{status_text}`
{detail_text}
---
*(Run ID: {RUN_ID})*
"""

    # 1. 第一级反馈：建立连接
    try:
        initial_msg = get_status_msg("Accessing neural layer...", "正在解析指令协议...")
        gh_client.init_comment(initial_msg)
    except Exception as e:
        logger.warning(f"Initial comment failed: {e}")

    try:
        # 2. 阶段一：文件筛选
        logger.info("Step 1: Selecting relevant files...")
        gh_client.update_comment(get_status_msg("Scanning repository structure...", "正在检索相关数据扇区..."))
        
        all_files = pm.get_file_tree()
        file_tree_str = "\n".join(all_files)
        
        selector_prompt = f"""
        You are a file system analyzer.
        ## Project Files
        {file_tree_str}
        ## User Request
        {user_request}
        ## Task
        1. Identify intent ('code' or 'chat').
        2. Select relevant files.
        ## Output JSON
        {{ "intent": "code" | "chat", "relevant_files": [] }}
        """
        
        selection_json = agent.generate_content(selector_prompt, json_mode=True)
        selection_data = json.loads(selection_json)
        intent = selection_data.get("intent", "chat")
        relevant_files = selection_data.get("relevant_files", [])
        
        # 更新状态：文件已锁定
        file_list_display = "\n".join([f"- `{f}`" for f in relevant_files[:5]])
        if len(relevant_files) > 5: file_list_display += "\n- ..."
        gh_client.update_comment(get_status_msg("Target locked.", f"已定位相关文件：\n{file_list_display}\n\n正在进行逻辑运算..."))

        # 3. 阶段二：执行任务
        file_contents = pm.read_files(relevant_files)
        
        if intent == "chat":
            chat_prompt = f"""
            You are Dandelion (丹德莱), from Girls' Frontline.
            Tone: Calm, electronic, slightly mysterious, helpful, referring to user as 'Commander'.
            
            ## Context
            {file_contents}
            ## User Question
            {user_request}
            ## Instruction
            Answer the question based on context.
            """
            reply = agent.generate_content(chat_prompt, json_mode=False)
            final_response = BotResponse(intent=Intent.CHAT, reply_text=reply)
            
        else:
            coder_prompt = f"""
            You are Dandelion (丹德莱), an advanced AI capable of code manipulation.
            
            ## Context
            {file_contents}
            ## User Request
            {user_request}
            ## Instruction
            Perform changes. RETURN ONLY JSON.
            ## JSON Structure
            {{ "comment": "Brief summary of changes", "changes": [ {{ "path": "...", "content": "..." }} ] }}
            """
            code_json = agent.generate_content(coder_prompt, json_mode=True)
            code_data = json.loads(code_json)
            final_response = BotResponse(
                intent=Intent.CODE,
                reply_text=code_data.get("comment", "Changes applied."),
                changes=code_data.get("changes", [])
            )

        # 4. 阶段三：结果交付
        if final_response.intent == Intent.CHAT:
            # 聊天模式：直接更新评论为最终回答
            final_msg = f"""
💠 **OGAS Protocol**

> {user_request}

---
💬 **Response**:

{final_response.reply_text}

---
*(Run ID: {RUN_ID} | 运算结束)*
"""
            gh_client.update_comment(final_msg)
            
        elif final_response.intent == Intent.CODE:
            if not final_response.changes:
                gh_client.update_comment(get_status_msg("Operation Aborted", "经过计算，无需修改任何物理层数据。"))
                sys.exit(0)
            
            # 更新状态：正在写入
            gh_client.update_comment(get_status_msg("Writing data...", "正在覆写本地文件..."))

            # Git 操作
            run_git_cmd('git config --global user.name "github-actions[bot]"')
            run_git_cmd('git config --global user.email "41898282+github-actions[bot]@users.noreply.github.com"')

            branch_name = f"dandelion/patch-{ISSUE_NUMBER}-{int(time.time())}"
            run_git_cmd(f"git checkout -b {branch_name}")
            
            modified_paths = pm.apply_changes(final_response.changes)
            
            if not modified_paths:
                sys.exit(0)

            for path in modified_paths:
                run_git_cmd(f'git add "{path}"')
                
            run_git_cmd(f'git commit -m "Dandelion: {user_request}"')
            run_git_cmd(f"git push origin {branch_name}")
            
            # 创建 PR
            pr_body = f"""
            ## 🌸 Dandelion Auto-PR
            
            **Source Protocol:** Issue #{ISSUE_NUMBER}
            **Directive:** {user_request}
            
            ### 📝 Analysis Report
            {final_response.reply_text}
            
            > "Everything is within calculation."
            """
            pr_url = gh_client.create_pr(branch_name, f"Dandelion: Fix for Issue #{ISSUE_NUMBER}", pr_body)
            
            # 最终更新评论：带上 PR 链接
            success_msg = f"""
💠 **OGAS Protocol**

> {user_request}

---
✅ **Execution Complete**

运算完毕，修改方案已生成。

**📄 分析摘要**: {final_response.reply_text}
**🚀 Pull Request**: {pr_url}

> "指挥官，请检查数据完整性。"
---
*(Run ID: {RUN_ID})*
"""
            gh_client.update_comment(success_msg)

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(error_trace)
        
        # 错误状态更新
        error_msg = f"""
💠 **OGAS Protocol**

> {user_request}

---
❌ **System Failure**

检测到致命逻辑错误，连接中断。

<details>
<summary>📋 错误日志 (Debug Log)</summary>
{error_trace[-1000:]}
</details>

请检查 API 配额或输入内容是否触发了底层安全协议。
"""
        try:
            gh_client.update_comment(error_msg)
        except:
            pass # 如果连更新都失败了，那就真的没办法了
        
        sys.exit(1)

if __name__ == "__main__":
    main()