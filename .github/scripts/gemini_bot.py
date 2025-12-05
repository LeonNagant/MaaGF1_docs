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
# 增加默认值处理，防止本地测试报错
ISSUE_NUMBER = int(os.environ.get("ISSUE_NUMBER", "0")) 
PROMPT_CONTENT = os.environ.get("PROMPT_CONTENT", "")
RUN_ID = os.environ.get("RUN_ID", "N/A")
TRIGGERS = ["/gemini", "/丹德莱"]

# 模型配置
# 使用 Flash 模型以获得速度和上下文优势
MODEL_NAME = "gemini-2.0-flash-exp" 

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
        # 使用 GITHUB_TOKEN 进行认证
        self.auth = Auth.Token(GITHUB_TOKEN)
        self.g = Github(auth=self.auth)
        self.repo = self.g.get_repo(REPO_NAME)
        self.issue = self.repo.get_issue(ISSUE_NUMBER)
        # [FIX] 删除 self.user_login = self.g.get_user().login
        # GITHUB_TOKEN 没有权限访问 /user 接口，且此处逻辑并不依赖它

    def post_comment(self, body: str):
        """发布评论"""
        try:
            self.issue.create_comment(body)
            logger.info("Comment posted to GitHub.")
        except Exception as e:
            logger.error(f"Failed to post comment: {e}")

    def create_pr(self, branch_name: str, title: str, body: str) -> str:
        """创建 PR 并返回 URL"""
        try:
            pr = self.repo.create_pull(
                title=title,
                body=body,
                head=branch_name,
                base="main" # 请确认你的主分支是 main 还是 master
            )
            return pr.html_url
        except Exception as e:
            logger.error(f"Failed to create PR: {e}")
            raise

class GeminiAgent:
    def __init__(self):
        genai.configure(api_key=GEMINI_API_KEY)
        
        # CRITICAL: 针对游戏/军事文档，必须关闭安全拦截
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
        """调用 Gemini，支持重试"""
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
            raise RuntimeError("Gemini refused to generate content (Safety or Error).")
        except Exception as e:
            logger.error(f"Gemini API Call Failed: {e}")
            raise

class ProjectManager:
    def __init__(self, root_dir="."):
        self.root_dir = root_dir
        # 排除目录和文件类型
        self.exclude_dirs = {'.git', '.github', '__pycache__', 'site', 'venv', 'node_modules', 'assets', 'pic', 'mk'}
        self.exclude_exts = ('.png', '.jpg', '.jpeg', '.gif', '.pdf', '.pyc', '.exe', '.zip')

    def get_file_tree(self) -> List[str]:
        """获取所有文件路径列表"""
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
        """读取指定文件内容"""
        content_block = ""
        for path in file_paths:
            # 简单的路径安全检查
            if ".." in path or path.startswith("/"):
                continue
                
            if not os.path.exists(path):
                continue
                
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 限制单个文件读取长度，防止 Token 溢出
                    if len(content) > 30000:
                        content = content[:30000] + "\n...(truncated)..."
                    content_block += f"--- FILE: {path} ---\n{content}\n--- END FILE ---\n\n"
            except Exception as e:
                logger.warning(f"Could not read {path}: {e}")
        return content_block

    def apply_changes(self, changes: List[Dict[str, str]]) -> List[str]:
        """应用文件修改"""
        modified_files = []
        for change in changes:
            path = change.get('path')
            content = change.get('content')
            if not path or content is None:
                continue
            
            # 路径清理
            if path.startswith("./"): path = path[2:]
            if path.startswith("/"): path = path[1:]
            
            # 确保目录存在
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
        logger.info("No prompt content found.")
        sys.exit(0)

    active_trigger = None
    for trigger in TRIGGERS:
        if trigger in PROMPT_CONTENT:
            active_trigger = trigger
            break
    
    if not active_trigger:
        logger.info("No trigger word found.")
        sys.exit(0)

    user_request = PROMPT_CONTENT.replace(active_trigger, "").strip()
    
    # 初始化各个组件
    # 注意：GithubClient 初始化可能会因为网络问题失败，放在 try 块外层以便快速失败，
    # 但由于我们移除了 get_user()，现在它应该很安全。
    try:
        gh_client = GithubClient()
        pm = ProjectManager()
        agent = GeminiAgent()
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        sys.exit(1)

    # 1. 第一级反馈：告知用户已开始处理
    # 使用 try-except 包裹，防止因为评论失败阻断后续流程（虽然不太可能）
    try:
        start_msg = f"🤖 **丹德莱系统启动**\n\n正在分析指令...\n> {user_request}\n\n*(Run ID: {RUN_ID})*"
        gh_client.post_comment(start_msg)
    except Exception as e:
        logger.warning(f"Initial comment failed: {e}")

    try:
        # 2. 阶段一：文件筛选 (Selector)
        logger.info("Step 1: Selecting relevant files...")
        all_files = pm.get_file_tree()
        file_tree_str = "\n".join(all_files)
        
        selector_prompt = f"""
        You are a file system analyzer for a documentation project.
        
        ## Project Files
        {file_tree_str}
        
        ## User Request
        {user_request}
        
        ## Task
        1. Identify if the user wants to modify files ('code') or just asking a question ('chat').
        2. Select the most relevant file paths from the list that are needed to answer the request or need to be modified.
        
        ## Output Format (JSON)
        {{
            "intent": "code" | "chat",
            "relevant_files": ["path/to/file1.md", "path/to/file2.md"]
        }}
        """
        
        selection_json = agent.generate_content(selector_prompt, json_mode=True)
        selection_data = json.loads(selection_json)
        
        intent = selection_data.get("intent", "chat")
        relevant_files = selection_data.get("relevant_files", [])
        
        logger.info(f"Intent: {intent}, Relevant Files: {len(relevant_files)}")

        # 3. 阶段二：执行任务 (Executor)
        file_contents = pm.read_files(relevant_files)
        
        if intent == "chat":
            # 聊天模式
            chat_prompt = f"""
            You are Dandelion (丹德莱), an AI assistant for the MaaGFL project.
            
            ## Context
            {file_contents}
            
            ## User Question
            {user_request}
            
            ## Instruction
            Answer the user's question based on the context provided. Be helpful and professional.
            """
            reply = agent.generate_content(chat_prompt, json_mode=False)
            final_response = BotResponse(intent=Intent.CHAT, reply_text=reply)
            
        else:
            # 代码模式
            coder_prompt = f"""
            You are Dandelion (丹德莱), a documentation engineer.
            
            ## Context Files
            {file_contents}
            
            ## User Request
            {user_request}
            
            ## Instruction
            Perform the requested changes. 
            RETURN ONLY A JSON OBJECT.
            
            ## JSON Structure
            {{
                "comment": "Description of what was done",
                "changes": [
                    {{
                        "path": "path/to/file.md",
                        "content": "FULL NEW CONTENT OF THE FILE"
                    }}
                ]
            }}
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
            gh_client.post_comment(f"**▌ 丹德莱回复**\n\n{final_response.reply_text}")
            
        elif final_response.intent == Intent.CODE:
            if not final_response.changes:
                gh_client.post_comment("🤔 丹德莱分析后认为无需修改任何文件。")
                sys.exit(0)
                
            # Git 操作
            # 使用 GitHub Actions 官方 Bot 身份，这样头像和名字显示更正规
            run_git_cmd('git config --global user.name "github-actions[bot]"')
            run_git_cmd('git config --global user.email "41898282+github-actions[bot]@users.noreply.github.com"')
            
            branch_name = f"ai/issue-{ISSUE_NUMBER}-{int(time.time())}"
            run_git_cmd(f"git checkout -b {branch_name}")
            
            modified_paths = pm.apply_changes(final_response.changes)
            
            if not modified_paths:
                logger.info("No files were actually modified.")
                sys.exit(0)

            for path in modified_paths:
                run_git_cmd(f'git add "{path}"')
                
            run_git_cmd(f'git commit -m "AI Update: {user_request}"')
            run_git_cmd(f"git push origin {branch_name}")
            
            # 创建 PR
            pr_body = f"""
            ## 🌸 Dandelion Auto-PR
            
            **Triggered by:** Issue #{ISSUE_NUMBER}
            **Request:** {user_request}
            
            ### 📝 Analysis
            {final_response.reply_text}
            """
            pr_url = gh_client.create_pr(branch_name, f"AI: Fix for Issue #{ISSUE_NUMBER}", pr_body)
            
            gh_client.post_comment(f"""
            **▌ 指令执行完毕**
            
            丹德莱已为您生成修改方案。
            
            **📄 分析报告**: {final_response.reply_text}
            **🚀 Pull Request**: {pr_url}
            """)

    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(error_trace)
        
        # 尝试在 Issue 中回复错误信息
        try:
            gh_client.post_comment(f"""
            **❌ 丹德莱遇到严重错误**
            
            <details>
            <summary>点击查看错误日志</summary>
            
            ```
            {error_trace[-1500:]}
            ```
            </details>
            
            请检查 Gemini API 配额或输入内容是否触发了安全限制。
            """)
        except Exception as post_error:
            logger.error(f"Failed to post error comment: {post_error}")
        
        sys.exit(1)

if __name__ == "__main__":
    main()