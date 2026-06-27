#!/usr/bin/env python3
"""
OpenCode 实战案例 - 交互式对话实现
基于 step-11-practical-example.md 的 Python 实现
"""

import json
import re
import os
import subprocess
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from http import HTTPStatus
import requests


# ============================================================================
# 数据模型
# ============================================================================

class PartType(Enum):
    TEXT = "text"
    AGENT = "agent"
    SUBTASK = "subtask"
    TOOL = "tool"


@dataclass
class Part:
    """消息片段基类"""
    type: PartType


@dataclass
class TextPart(Part):
    """文本片段"""
    text: str = ""
    
    def __init__(self, text: str = ""):
        super().__init__(PartType.TEXT)
        self.text = text


@dataclass
class AgentCommand:
    """@agent 命令"""
    name: str
    prompt: str
    description: str = ""


@dataclass
class AgentPart(Part):
    """Agent 引用片段 (@agent)"""
    command: AgentCommand
    
    def __init__(self, command: AgentCommand):
        super().__init__(PartType.AGENT)
        self.command = command


@dataclass
class SubtaskPart(Part):
    """子任务片段"""
    agent: str
    description: str
    prompt: str
    model: dict = field(default_factory=dict)
    
    def __init__(self, agent: str, description: str, prompt: str, model: dict = None):
        super().__init__(PartType.SUBTASK)
        self.agent = agent
        self.description = description
        self.prompt = prompt
        self.model = model or {}


@dataclass
class ToolPart(Part):
    """工具调用片段"""
    tool: str
    state: dict = field(default_factory=dict)
    
    def __init__(self, tool: str, state: dict = None):
        super().__init__(PartType.TOOL)
        self.tool = tool
        self.state = state or {}


@dataclass
class Message:
    """会话消息"""
    id: str
    role: str
    session_id: str
    parts: list = field(default_factory=list)
    agent: str = ""
    model: dict = field(default_factory=dict)
    permission: dict = field(default_factory=dict)


@dataclass
class Session:
    """会话"""
    id: str
    parent_id: Optional[str] = None
    title: str = ""
    messages: list = field(default_factory=list)
    permission: list = field(default_factory=list)


@dataclass
class TodoItem:
    """待办事项"""
    id: str
    content: str
    status: str = "pending"


# ============================================================================
# LLM 客户端
# ============================================================================

class QwenClient:
    """通义千问 API 客户端"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.url = 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation'
        self.model = 'qwen-turbo'
    
    def chat(
        self,
        system: str,
        messages: list[dict],
        tools: Optional[list] = None,
        temperature: float = 0.7
    ) -> dict:
        """调用 LLM 进行对话"""
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }
        
        all_messages = [{"role": "system", "content": system}]
        all_messages.extend(messages)
        
        body = {
            'model': self.model,
            'input': {
                'messages': all_messages
            },
            'parameters': {
                'result_format': 'message',
                'temperature': temperature
            }
        }
        
        if tools:
            body['tools'] = tools
        
        try:
            response = requests.post(self.url, headers=headers, json=body, timeout=120)
            response.raise_for_status()
            result = response.json()
            
            if 'output' in result and 'choices' in result['output']:
                return result['output']['choices'][0]['message']
            else:
                return {"role": "assistant", "content": "Error: Invalid response format"}
        
        except Exception as e:
            return {"role": "assistant", "content": f"Error: {str(e)}"}


# ============================================================================
# 工具系统
# ============================================================================

class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self.tools: dict[str, callable] = {}
        self.tool_schemas: dict[str, dict] = {}
    
    def register(self, name: str, schema: dict, handler: callable):
        """注册工具"""
        self.tools[name] = handler
        self.tool_schemas[name] = schema
    
    def get_tool(self, name: str) -> Optional[callable]:
        """获取工具处理函数"""
        return self.tools.get(name)
    
    def get_schemas(self, tool_names: Optional[list] = None) -> list:
        """获取工具 schemas"""
        if tool_names is None:
            return list(self.tool_schemas.values())
        return [self.tool_schemas[name] for name in tool_names if name in self.tool_schemas]


# 全局工具注册表
tool_registry = ToolRegistry()


def register_builtin_tools():
    """注册内置工具"""
    
    # todoWrite 工具
    todo_registry: dict[str, TodoItem] = {}
    
    def todo_write_handler(todos: list[dict]) -> str:
        """更新待办事项列表"""
        for todo in todos:
            todo_id = todo.get('id')
            if todo_id in todo_registry:
                todo_registry[todo_id].status = todo.get('status', todo_registry[todo_id].status)
                todo_registry[todo_id].content = todo.get('content', todo_registry[todo_id].content)
            else:
                todo_registry[todo_id] = TodoItem(
                    id=todo_id,
                    content=todo.get('content', ''),
                    status=todo.get('status', 'pending')
                )
        return f"Todo list updated: {len(todos)} items"
    
    tool_registry.register(
        'todoWrite',
        {
            'type': 'function',
            'function': {
                'name': 'todoWrite',
                'description': 'Write to the todo list to track task progress',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'todos': {
                            'type': 'array',
                            'items': {
                                'type': 'object',
                                'properties': {
                                    'id': {'type': 'string'},
                                    'content': {'type': 'string'},
                                    'status': {'type': 'string', 'enum': ['pending', 'in_progress', 'completed']}
                                },
                                'required': ['id', 'content', 'status']
                            }
                        }
                    },
                    'required': ['todos']
                }
            }
        },
        todo_write_handler
    )
    
    # read 工具
    def read_handler(filePath: str) -> str:
        """读取文件内容"""
        try:
            with open(filePath, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            return f"# File not found: {filePath}"
        except Exception as e:
            return f"# Error reading {filePath}: {str(e)}"
    
    tool_registry.register(
        'read',
        {
            'type': 'function',
            'function': {
                'name': 'read',
                'description': 'Read file contents',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'filePath': {'type': 'string', 'description': 'Path to the file'}
                    },
                    'required': ['filePath']
                }
            }
        },
        read_handler
    )
    
    # write 工具
    def write_handler(filePath: str, content: str) -> str:
        """写入文件内容"""
        try:
            dir_path = os.path.dirname(filePath)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
            
            with open(filePath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return f"File {filePath} created successfully ({len(content)} characters)"
        except Exception as e:
            return f"Error writing file {filePath}: {str(e)}"
    
    tool_registry.register(
        'write',
        {
            'type': 'function',
            'function': {
                'name': 'write',
                'description': 'Write new file or overwrite existing file',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'filePath': {'type': 'string', 'description': 'Path to the file'},
                        'content': {'type': 'string', 'description': 'Content to write'}
                    },
                    'required': ['filePath', 'content']
                }
            }
        },
        write_handler
    )
    
    # edit 工具
    def edit_handler(filePath: str, oldString: str, newString: str) -> str:
        """编辑文件内容"""
        try:
            with open(filePath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if oldString in content:
                updated = content.replace(oldString, newString, 1)
                with open(filePath, 'w', encoding='utf-8') as f:
                    f.write(updated)
                return f"File {filePath} updated successfully"
            else:
                return f"Pattern not found in {filePath}"
        except FileNotFoundError:
            return f"File not found: {filePath}"
        except Exception as e:
            return f"Error editing {filePath}: {str(e)}"
    
    tool_registry.register(
        'edit',
        {
            'type': 'function',
            'function': {
                'name': 'edit',
                'description': 'Edit existing file by replacing text',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'filePath': {'type': 'string'},
                        'oldString': {'type': 'string'},
                        'newString': {'type': 'string'}
                    },
                    'required': ['filePath', 'oldString', 'newString']
                }
            }
        },
        edit_handler
    )
    
    # bash 工具
    def bash_handler(command: str, description: str = "") -> str:
        """执行 shell 命令"""
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=30,
                cwd=os.getcwd()
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr] {result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"
            return output if output else "(command executed successfully with no output)"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 30 seconds"
        except Exception as e:
            return f"Error executing command: {str(e)}"
    
    tool_registry.register(
        'bash',
        {
            'type': 'function',
            'function': {
                'name': 'bash',
                'description': 'Execute shell commands',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'command': {'type': 'string'},
                        'description': {'type': 'string'}
                    },
                    'required': ['command']
                }
            }
        },
        bash_handler
    )
    
    return todo_registry


# ============================================================================
# Agent 系统
# ============================================================================

class Agent:
    """Agent 定义"""
    
    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        available_tools: list[str],
        permissions: dict
    ):
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.available_tools = available_tools
        self.permissions = permissions


class AgentRegistry:
    """Agent 注册表"""
    
    def __init__(self):
        self.agents: dict[str, Agent] = {}
    
    def register(self, agent: Agent):
        """注册 Agent"""
        self.agents[agent.name] = agent
    
    def get(self, name: str) -> Optional[Agent]:
        """获取 Agent"""
        return self.agents.get(name)


# 全局 Agent 注册表
agent_registry = AgentRegistry()


def register_builtin_agents():
    """注册内置 Agent"""
    
    # Explore Agent
    explore_agent = Agent(
        name="explore",
        description="代码分析和文件搜索专家",
        system_prompt="""You are a file search specialist. You excel at thoroughly navigating and exploring codebases.

Your strengths:
- Rapidly finding files using glob patterns
- Searching code and text with powerful regex patterns
- Reading and analyzing file contents

Guidelines:
- Use Read when you know the specific file path you need to read
- Analyze code complexity and identify optimization opportunities
- Provide structured analysis with specific findings""",
        available_tools=["read"],
        permissions={"read": "allow", "edit": "deny", "bash": "ask"}
    )
    agent_registry.register(explore_agent)
    
    # Build Agent
    build_agent = Agent(
        name="build",
        description="代码编辑和文件操作专家",
        system_prompt="""You are OpenCode, a helpful coding assistant.

Your task is to help users with file operations and code tasks.

IMPORTANT: You MUST use the provided tools to complete tasks. Do not just describe what you would do - actually call the tools.

Available tools:
- todoWrite: Update todo list to track progress
- read: Read file contents
- write: Create new files
- edit: Modify existing files
- bash: Execute shell commands

Guidelines:
- Always analyze the task before making changes
- Use TodoWrite to track your progress
- Use Write to create new files
- Use Read to examine existing files
- Use Edit to modify existing files
- Use Bash to execute commands when needed
- Make minimal, focused changes
- Explain your actions clearly

CRITICAL: When you need to create a file, you MUST call the 'write' tool with filePath and content parameters.""",
        available_tools=["todoWrite", "read", "edit", "write", "bash"],
        permissions={"*": "allow"}
    )
    agent_registry.register(build_agent)
    
    return agent_registry


# ============================================================================
# 输入解析
# ============================================================================

class InputParser:
    """用户输入解析器"""
    
    AGENT_PATTERN = re.compile(r'@(\w+)\s+(.*?)(?=@\w+|$)', re.DOTALL)
    
    @classmethod
    def parse(cls, user_input: str) -> list[Part]:
        """解析用户输入为 Parts"""
        parts: list[Part] = []
        
        matches = list(cls.AGENT_PATTERN.finditer(user_input))
        
        if not matches:
            parts.append(TextPart(user_input.strip()))
            return parts
        
        first_match_start = matches[0].start()
        if first_match_start > 0:
            text_before = user_input[:first_match_start].strip()
            if text_before:
                parts.append(TextPart(text_before))
        
        for match in matches:
            agent_name = match.group(1)
            agent_prompt = match.group(2).strip()
            
            parts.append(AgentPart(AgentCommand(
                name=agent_name,
                prompt=agent_prompt,
                description=cls._get_agent_description(agent_name)
            )))
        
        return parts
    
    @staticmethod
    def _get_agent_description(agent_name: str) -> str:
        """获取 Agent 描述"""
        agent = agent_registry.get(agent_name)
        return agent.description if agent else f"{agent_name} Agent"


# ============================================================================
# 主流程控制器 (交互式)
# ============================================================================

class InteractiveOpenCode:
    """交互式 OpenCode 控制器"""
    
    def __init__(self, llm_client: Optional[QwenClient] = None):
        self.llm = llm_client or QwenClient()
        self.messages: list[dict] = []  # 对话历史
        self.todo_registry: dict = {}
        self.current_agent: Optional[Agent] = None
        self.working_dir = os.getcwd()
        
    def _build_system_prompt(self) -> str:
        """构建系统 Prompt"""
        agent = self.current_agent or agent_registry.get("build")
        
        env_section = f"""You are powered by the model named qwen-turbo...

<env>
  Working directory: {self.working_dir}
  Workspace root folder: {self.working_dir}
  Is directory a git repo: yes
  Platform: darwin
  Today's date: Mon Mar 17 2025
</env>"""
        
        tool_instructions = f"""
You have access to the following tools:
{json.dumps(tool_registry.get_schemas(agent.available_tools), indent=2, ensure_ascii=False)}

To use a tool, you MUST respond in the following JSON format:
{{
  "tool_calls": [
    {{
      "name": "tool_name",
      "arguments": {{"param1": "value1", "param2": "value2"}}
    }}
  ],
  "content": "Your explanation here"
}}

IMPORTANT: 
1. Use the 'write' tool to create files with filePath and content
2. Use the 'read' tool to read files with filePath
3. Always include the tool_calls array when using tools
4. Do not just describe the action - actually output the JSON
"""
        
        return f"{env_section}\n\n{agent.system_prompt}\n\n{tool_instructions}"
    
    def _parse_tool_calls(self, content: str) -> list[dict]:
        """解析回复中的工具调用"""
        tool_calls = []
        
        # 尝试提取 JSON 代码块
        json_pattern = r'```(?:json)?\s*\n?(\{[\s\S]*?\})\n?```'
        matches = re.findall(json_pattern, content)
        
        for match in matches:
            try:
                data = json.loads(match.strip())
                if 'tool_calls' in data and isinstance(data['tool_calls'], list):
                    for tc in data['tool_calls']:
                        if 'name' in tc and 'arguments' in tc:
                            tool_calls.append({
                                'function': {
                                    'name': tc['name'],
                                    'arguments': json.dumps(tc['arguments'])
                                }
                            })
            except json.JSONDecodeError:
                continue
        
        # 如果没有找到代码块，尝试直接解析
        if not tool_calls:
            try:
                data = json.loads(content.strip())
                if 'tool_calls' in data and isinstance(data['tool_calls'], list):
                    for tc in data['tool_calls']:
                        if 'name' in tc and 'arguments' in tc:
                            tool_calls.append({
                                'function': {
                                    'name': tc['name'],
                                    'arguments': json.dumps(tc['arguments'])
                                }
                            })
            except:
                pass
        
        return tool_calls
    
    def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """执行单个工具"""
        tool_handler = tool_registry.get_tool(tool_name)
        if not tool_handler:
            return f"Error: Unknown tool '{tool_name}'"
        
        try:
            result = tool_handler(**arguments)
            return result
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"
    
    def process_input(self, user_input: str) -> str:
        """处理用户输入"""
        if not self.current_agent:
            self.current_agent = agent_registry.get("build")

        system_prompt = self._build_system_prompt()
        self.messages.append({"role": "user", "content": user_input})

        if len(self.messages) > 20:
            self.messages = self.messages[-20:]

        max_iterations = 10

        for iteration in range(max_iterations):
            llm_response = self.llm.chat(
                system=system_prompt,
                messages=self.messages,
                temperature=0.7
            )

            ai_content = llm_response.get('content', '')
            tool_calls = self._parse_tool_calls(ai_content)

            if not tool_calls:
                # 没有 tool_calls → LLM 认为任务完成，结束循环
                self.messages.append({"role": "assistant", "content": ai_content})
                return ai_content

            # 有 tool_calls → 执行工具，把结果塞回 messages，继续循环
            self.messages.append({"role": "assistant", "content": ai_content or "Working..."})

            tool_results = []
            for tc in tool_calls:
                func = tc.get('function', {})
                tool_name = func.get('name')
                try:
                    arguments = json.loads(func.get('arguments', '{}'))
                except Exception:
                    arguments = {}

                print(f"  [迭代{iteration+1}] [工具] {tool_name}({arguments})")
                result = self._execute_tool(tool_name, arguments)
                tool_results.append(f"[{tool_name}] Result: {result}")
                print(f"  [结果] {result[:100]}..." if len(str(result)) > 100 else f"  [结果] {result}")

            self.messages.append({
                "role": "user",
                "content": "[Tool Results]\n\n" + "\n\n".join(tool_results)
            })

        return "已达到最大迭代次数，任务可能未完成。"
    
    def reset(self):
        """重置对话历史"""
        self.messages = []
        self.current_agent = None
        print("对话历史已重置。")
    
    def show_history(self):
        """显示对话历史"""
        print("\n" + "=" * 60)
        print("对话历史")
        print("=" * 60)
        for i, msg in enumerate(self.messages):
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            print(f"\n[{i+1}] {role.upper()}:")
            print(content[:300] + "..." if len(content) > 300 else content)
        print("\n" + "=" * 60)


def print_banner():
    """打印欢迎信息"""
    print("=" * 70)
    print("  OpenCode - 交互式 AI 助手")
    print("=" * 70)
    print("\n可用命令:")
    print("  /help    - 显示帮助信息")
    print("  /reset   - 重置对话历史")
    print("  /history - 显示对话历史")
    print("  /exit    - 退出程序")
    print("\n直接输入你的问题或任务描述即可开始。")
    print("=" * 70)


def print_help():
    """打印帮助信息"""
    print("\n" + "=" * 70)
    print("帮助信息")
    print("=" * 70)
    print("\n这是一个交互式 AI 助手，可以帮助你:")
    print("  - 创建和编辑文件")
    print("  - 执行 shell 命令")
    print("  - 分析代码")
    print("  - 回答问题和提供建议")
    print("\n命令:")
    print("  /help      - 显示此帮助信息")
    print("  /reset     - 清空对话历史，开始新对话")
    print("  /history   - 查看当前对话历史")
    print("  /exit      - 退出程序 (也可以用 Ctrl+C)")
    print("\n提示:")
    print("  - AI 会自动使用合适的工具完成任务")
    print("  - 可以引用之前的上下文进行追问")
    print("  - 使用 /reset 可以开始全新的对话")
    print("=" * 70 + "\n")


def main():
    """主函数 - 交互式对话"""
    import sys
    
    # 注册组件
    register_builtin_agents()
    register_builtin_tools()
    
    # 创建控制器
    opencode = InteractiveOpenCode()
    
    # 检查是否有命令行参数（单命令模式）
    if len(sys.argv) > 1:
        # 单命令模式：执行参数中的命令然后退出
        user_input = " ".join(sys.argv[1:])
        print_banner()
        print(f"\n[单命令模式] {user_input}\n")
        print("[思考中...]")
        response = opencode.process_input(user_input)
        print(f"\n{response}")
        return
    
    # 检查是否是管道输入
    if not sys.stdin.isatty():
        # 管道模式：读取一行然后退出
        try:
            user_input = sys.stdin.read().strip()
            if user_input:
                print_banner()
                print(f"\n[管道模式]\n")
                print("[思考中...]")
                response = opencode.process_input(user_input)
                print(f"\n{response}")
            return
        except EOFError:
            return
    
    # 交互式模式
    print_banner()
    
    while True:
        try:
            # 获取用户输入
            user_input = input("\n>>> ").strip()
            
            # 跳过空输入
            if not user_input:
                continue
            
            # 处理命令
            if user_input.startswith('/'):
                cmd = user_input.lower()
                
                if cmd in ['/exit', '/quit', '/q']:
                    print("\n再见！")
                    break
                
                elif cmd == '/help':
                    print_help()
                    continue
                
                elif cmd == '/reset':
                    opencode.reset()
                    continue
                
                elif cmd == '/history':
                    opencode.show_history()
                    continue
                
                else:
                    print(f"未知命令: {user_input}")
                    print("输入 /help 查看可用命令")
                    continue
            
            # 处理用户输入
            print("\n[思考中...]")
            response = opencode.process_input(user_input)
            
            # 显示回复
            print(f"\n{response}")
            
        except KeyboardInterrupt:
            print("\n\n再见！")
            break
        
        except EOFError:
            print("\n\n再见！")
            break
        
        except Exception as e:
            print(f"\n[错误] {str(e)}")


if __name__ == "__main__":
    main()
