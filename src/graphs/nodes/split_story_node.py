# 智能语义分句节点
# 将完整故事文本拆分为独立的句子/台词，识别故事类型和标题

import os
import json
from typing import List
from jinja2 import Template
from langchain_core.runnables import RunnableConfig
from langgraph.runtime import Runtime
from coze_coding_utils.runtime_ctx.context import Context
from coze_coding_dev_sdk import LLMClient
from langchain_core.messages import HumanMessage, SystemMessage

from graphs.state import SplitStoryInput, SplitStoryOutput


def split_story_node(
    state: SplitStoryInput,
    config: RunnableConfig,
    runtime: Runtime[Context]
) -> SplitStoryOutput:
    """
    title: 智能语义分句
    desc: 使用LLM分析故事文本，智能拆分为独立画面台词，识别故事类型和标题
    integrations: 大语言模型
    """
    ctx = runtime.context
    
    # 读取LLM配置
    cfg_path = os.path.join(
        os.getenv("COZE_WORKSPACE_PATH", "/workspace/projects"),
        config.get("metadata", {}).get("llm_cfg", "config/split_story_llm_cfg.json")
    )
    
    with open(cfg_path, "r", encoding="utf-8") as f:
        llm_cfg = json.load(f)
    
    llm_config = llm_cfg.get("config", {})
    sp = llm_cfg.get("sp", "")
    up = llm_cfg.get("up", "")
    
    # 使用Jinja2渲染用户提示词
    up_template = Template(up)
    user_prompt = up_template.render({"story_text": state.story_text})
    
    # 初始化LLM客户端
    client = LLMClient(ctx=ctx)
    
    # 构建消息
    messages = [
        SystemMessage(content=sp),
        HumanMessage(content=user_prompt)
    ]
    
    # 调用LLM
    response = client.invoke(
        messages=messages,
        model=llm_config.get("model", "doubao-seed-1-8-251228"),
        temperature=llm_config.get("temperature", 0.3),
        max_completion_tokens=llm_config.get("max_completion_tokens", 4096)
    )
    
    # 解析响应内容
    response_content = response.content
    if isinstance(response_content, list):
        # 处理多内容响应
        text_parts = []
        for item in response_content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))
        response_content = " ".join(text_parts)
    
    # 提取JSON
    response_text = response_content.strip() if isinstance(response_content, str) else str(response_content)
    
    # 清理可能的Markdown代码块标记
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    if response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    response_text = response_text.strip()
    
    # 解析JSON结果
    try:
        result = json.loads(response_text)
        sentences: List[str] = result.get("sentences", [])
        story_type: str = result.get("story_type", "励志")
        story_title: str = result.get("story_title", "故事")
        
        # 验证数据有效性
        if not sentences:
            # 如果解析失败，使用简单分句作为后备
            sentences = _simple_split(state.story_text)
        
        if len(sentences) < 3:
            sentences = _simple_split(state.story_text)
            
    except json.JSONDecodeError:
        # JSON解析失败，使用简单分句
        sentences = _simple_split(state.story_text)
        story_type = "励志"
        story_title = "人生故事"
    
    return SplitStoryOutput(
        sentences=sentences,
        story_type=story_type,
        story_title=story_title
    )


def _simple_split(text: str) -> List[str]:
    """简单分句后备方案：按句号和逗号拆分"""
    # 先按句号拆分
    parts = text.replace("！", "。").replace("？", "。").split("。")
    sentences = []
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # 如果句子过长（超过50字），按逗号再拆分
        if len(part) > 50:
            sub_parts = part.split("，")
            for sub in sub_parts:
                sub = sub.strip()
                if sub:
                    sentences.append(sub)
        else:
            sentences.append(part)
    
    return sentences if sentences else [text]